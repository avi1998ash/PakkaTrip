"""Operator self-signup, phone OTP, verification documents and tiers."""
import io
import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from accounts.models import User
from catalog.models import City, Package
from core.models import PlatformSetting
from operators.models import Operator, OperatorDocument, PhoneOtp
from operators.verification import gstin_check_char, read_document_file

TEST_PRIVATE = tempfile.mkdtemp(prefix="pakkatrip-test-private-")
PAN = "ABCPS1234K"
BANK = {"holder_name": "Spiti Trails", "account_number": "50100111122223333", "confirm_account_number": "50100111122223333",
        "ifsc": "HDFC0000001", "account_type": "current", "pan": PAN, "business_type": "proprietorship",
        "address_line": "Main Bazaar", "address_city": "Kaza", "address_state": "Himachal Pradesh", "pincode": "172114"}
SIGNUP = {"business_name": "Spiti Valley Trails", "owner_name": "Kunzang Negi", "city": "Kaza", "phone": "9418012233",
          "email": "spiti@example.com", "password": "trails2026"}


def gstin(pan=PAN, state="02"):
    first14 = f"{state}{pan}1Z"
    return first14 + gstin_check_char(first14)


def jpeg(size=(600, 400)):
    out = io.BytesIO()
    Image.new("RGB", size, "#123456").save(out, "JPEG")
    return SimpleUploadedFile("aadhaar.jpg", out.getvalue(), content_type="image/jpeg")


@override_settings(PRIVATE_MEDIA_ROOT=TEST_PRIVATE, MSG91_AUTH_KEY="", MSG91_OTP_TEMPLATE_ID="", DEBUG=False)
class OperatorSignupTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_PRIVATE, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        User.objects.create_superuser("admin@pakkatrip.com", "admin123")

    def setUp(self):
        cache.clear()
        PlatformSetting.put("sms_otp_enabled", True)   # most tests cover the SMS flow; SmsOffTests covers it switched off
        self.sms = []   # (phone, code) — stands in for MSG91
        patcher = mock.patch("operators.verification.send_otp_sms", side_effect=lambda phone, code: self.sms.append((phone, code)))
        patcher.start()
        self.addCleanup(patcher.stop)
        bank = {"ifsc_lookup": lambda code: {"bank": "HDFC Bank", "branch": "Kaza", "city": "Kaza", "imps": True, "neft": True},
                "create_contact": lambda *a, **k: {"id": "cont_1"}, "create_fund_account": lambda *a, **k: {"id": "fa_1"}}
        for name, fn in bank.items():
            p = mock.patch(f"payments.razorpay.{name}", side_effect=fn)
            p.start()
            self.addCleanup(p.stop)

    def as_admin(self):
        r = self.client.post("/api/auth/login/", {"email": "admin@pakkatrip.com", "password": "admin123"}, format="json")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])

    def as_token(self, access):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + access)

    def sign_up(self, **extra):
        self.client.credentials()
        self.assertEqual(self.client.post("/api/public/partner/otp/", {"phone": SIGNUP["phone"]}, format="json").status_code, 200)
        r = self.client.post("/api/public/partner/signup/", {**SIGNUP, "otp": self.sms[-1][1], **extra}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.op_token = r.data["access"]
        self.as_token(self.op_token)
        return Operator.objects.get(contact_phone=SIGNUP["phone"])

    def add_verified_bank(self, op):
        self.as_token(self.op_token)
        self.assertEqual(self.client.put("/api/operator/bank-account/", BANK, format="json").status_code, 200)
        self.as_admin()
        self.assertEqual(self.client.post(f"/api/admin/bank-accounts/{op.id}/verify/", format="json").status_code, 200)

    # ---- signup

    def test_signup_needs_the_sms_code_and_creates_a_pending_operator(self):
        self.client.post("/api/public/partner/otp/", {"phone": SIGNUP["phone"]}, format="json")
        wrong = "000000" if self.sms[-1][1] != "000000" else "111111"
        r = self.client.post("/api/public/partner/signup/", {**SIGNUP, "otp": wrong}, format="json")
        self.assertEqual((r.status_code, "otp" in r.data), (400, True))
        self.assertFalse(Operator.objects.filter(contact_phone=SIGNUP["phone"]).exists())
        r = self.client.post("/api/public/partner/signup/", {**SIGNUP, "otp": self.sms[-1][1]}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data["user"]["role"], r.data["user"]["operator"]["status"]), ("operator", "pending"))
        op = Operator.objects.get(contact_phone=SIGNUP["phone"])
        self.assertEqual((op.source, op.status, bool(op.phone_verified_at), op.tier), ("signup", "pending", True, ""))
        self.assertFalse(PhoneOtp.objects.filter(code_hash__contains=self.sms[-1][1]).exists())   # only a hash is stored
        # the code can't be used twice, and the number can't sign up again
        self.assertEqual(self.client.post("/api/public/partner/otp/", {"phone": SIGNUP["phone"]}, format="json").status_code, 400)
        # they can sign in on the partner portal
        r = self.client.post("/api/auth/login/", {"email": SIGNUP["email"], "password": SIGNUP["password"]}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_otp_limits(self):
        self.client.post("/api/public/partner/otp/", {"phone": SIGNUP["phone"]}, format="json")
        r = self.client.post("/api/public/partner/otp/", {"phone": SIGNUP["phone"]}, format="json")
        self.assertIn("wait", r.data["detail"])   # 30 seconds between codes
        for _ in range(5):
            self.client.post("/api/public/partner/signup/", {**SIGNUP, "otp": "999999" if self.sms[-1][1] != "999999" else "888888"}, format="json")
        r = self.client.post("/api/public/partner/signup/", {**SIGNUP, "otp": self.sms[-1][1]}, format="json")
        self.assertIn("Too many wrong tries", str(r.data), r.data)

    @override_settings(MSG91_AUTH_KEY="auth-key", MSG91_OTP_TEMPLATE_ID="tmpl_1")
    def test_msg91_request(self):
        from core.sms import send_otp_sms
        resp = mock.MagicMock()
        resp.__enter__.return_value = io.BytesIO(json.dumps({"type": "success", "request_id": "r1"}).encode())
        with mock.patch("core.sms.urllib.request.urlopen", return_value=resp) as urlopen:
            send_otp_sms("9418012233", "123456")
        req = urlopen.call_args[0][0]
        self.assertIn("template_id=tmpl_1", req.full_url)
        self.assertIn("mobile=919418012233", req.full_url)
        self.assertIn("otp=123456", req.full_url)
        self.assertEqual(req.get_header("Authkey"), "auth-key")

    # ---- pending operators

    def test_pending_operator_can_work_but_stays_hidden(self):
        op = self.sign_up()
        self.assertEqual(self.client.get("/api/operator/packages/").status_code, 200)
        delhi, kaza = City.by_name("Delhi"), City.by_name("Kaza")
        Package.objects.create(operator=op, title="Spiti Circuit", slug="spiti-circuit", from_city=delhi, to_city=kaza, nights=5,
                               price_per_person=18999, status=Package.Status.APPROVED)
        self.client.credentials()
        self.assertNotIn("Spiti Circuit", [p["title"] for p in self.client.get("/api/public/packages/").data])
        self.as_admin()
        self.assertEqual(self.client.get("/api/admin/nav-counts/").data["applications"], 1)

    def test_approval_needs_bronze(self):
        op = self.sign_up()
        self.as_admin()
        r = self.client.post(f"/api/admin/operators/{op.id}/verify/", {"verified": True}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Bronze", r.data["detail"])
        self.add_verified_bank(op)                                  # PAN + bank + phone OTP (at signup)
        op.refresh_from_db()
        self.assertEqual(op.tier, "bronze")
        r = self.client.post(f"/api/admin/operators/{op.id}/verify/", {"verified": True}, format="json")
        self.assertEqual((r.status_code, r.data["status"], r.data["tier"]), (200, "verified", "bronze"))
        self.assertEqual(self.client.get("/api/admin/nav-counts/").data["applications"], 0)

    def test_reject_and_resubmit(self):
        op = self.sign_up()
        self.as_admin()
        self.assertEqual(self.client.post(f"/api/admin/operators/{op.id}/reject/", {"reason": "x"}, format="json").status_code, 400)
        r = self.client.post(f"/api/admin/operators/{op.id}/reject/", {"reason": "Business name doesn't match the GST certificate"}, format="json")
        self.assertEqual(r.data["status"], "rejected")
        self.as_token(self.op_token)
        self.assertEqual(self.client.get("/api/auth/me/").data["operator"]["rejection_reason"], "Business name doesn't match the GST certificate")
        self.assertEqual(self.client.post("/api/operator/verification/resubmit/", format="json").data["status"], "pending")

    # ---- documents and tiers

    def test_gold_with_gst_and_udyam(self):
        op = self.sign_up()
        bad = gstin()[:14] + ("A" if gstin()[14] != "A" else "B")
        self.assertEqual(self.client.put("/api/operator/verification/documents/gst/", {"number": bad}, format="json").status_code, 400)
        self.assertEqual(self.client.put("/api/operator/verification/documents/udyam/", {"number": "UDYAM-12"}, format="json").status_code, 400)
        self.client.put("/api/operator/verification/documents/gst/", {"number": gstin().lower()}, format="json")
        self.client.put("/api/operator/verification/documents/udyam/", {"number": "UDYAM-HP-04-0012345"}, format="json")
        self.add_verified_bank(op)
        for kind in ("gst", "udyam"):
            r = self.client.post(f"/api/admin/operators/{op.id}/documents/{kind}/verify/", format="json")
        self.assertEqual((r.data["tier"], r.data["gst_pan_match"]), ("gold", True))
        # a rejected document drops the tier back
        r = self.client.post(f"/api/admin/operators/{op.id}/documents/udyam/reject/", {"reason": "Certificate has expired"}, format="json")
        self.assertEqual(r.data["tier"], "bronze")

    def test_aadhaar_keeps_last4_and_an_encrypted_copy(self):
        op = self.sign_up()
        r = self.client.put("/api/operator/verification/documents/aadhaar/", {"number": "1234 5678 9012", "file": jpeg()}, format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertIn("last 4", r.data["detail"])
        r = self.client.put("/api/operator/verification/documents/aadhaar/", {"number": "9012", "file": jpeg()}, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["documents"]["aadhaar"]["number"], "XXXX XXXX 9012")
        doc = OperatorDocument.objects.get(operator=op, kind="aadhaar")
        self.assertEqual(doc.number, "9012")
        raw = Path(doc.file.path).read_bytes()
        self.assertFalse(raw.startswith(b"\xff\xd8"))                     # not a readable JPEG on disk
        self.assertTrue(read_document_file(doc).startswith(b"\xff\xd8"))  # decrypts back to the image
        self.assertEqual(self.client.get(f"/api/admin/operators/{op.id}/documents/aadhaar/file/").status_code, 403)   # operator
        self.as_admin()
        r = self.client.get(f"/api/admin/operators/{op.id}/documents/aadhaar/file/")
        self.assertEqual((r.status_code, r["Content-Type"], r.content[:2]), (200, "image/jpeg", b"\xff\xd8"))
        self.add_verified_bank(op)
        op.phone_verified_at = None   # without the phone, Aadhaar alone gives Silver
        op.save()
        r = self.client.post(f"/api/admin/operators/{op.id}/documents/aadhaar/verify/", format="json")
        self.assertEqual(r.data["tier"], "silver")

    def test_tier_badge_on_traveller_site(self):
        op = self.sign_up()
        self.add_verified_bank(op)
        self.client.post(f"/api/admin/operators/{op.id}/verify/", {"verified": True}, format="json")
        Package.objects.create(operator=op, title="Spiti Circuit", slug="spiti-circuit", from_city=City.by_name("Delhi"),
                               to_city=City.by_name("Kaza"), nights=5, price_per_person=18999, status=Package.Status.APPROVED)
        self.client.credentials()
        card = next(p for p in self.client.get("/api/public/packages/").data if p["title"] == "Spiti Circuit")
        self.assertEqual(card["tier"], "bronze")
        self.assertEqual(self.client.get(f"/api/public/packages/{card['id']}/").data["operator"]["tier"], "bronze")

    def test_admin_phone_change_needs_new_otp(self):
        op = self.sign_up()
        self.add_verified_bank(op)
        r = self.client.patch(f"/api/admin/operators/{op.id}/", {"name": op.business_name, "owner": op.owner_name, "city": "Kaza",
                                                                 "phone": "9418099999", "email": SIGNUP["email"]}, format="json")
        self.assertEqual((r.data["phone_verified"], r.data["tier"]), (False, None))
        self.as_token(self.op_token)
        self.client.post("/api/operator/verification/phone/otp/", format="json")
        self.assertEqual(self.sms[-1][0], "9418099999")
        r = self.client.post("/api/operator/verification/phone/verify/", {"code": self.sms[-1][1]}, format="json")
        self.assertEqual((r.data["phone"]["verified"], r.data["tier"]), (True, "bronze"))


@override_settings(PRIVATE_MEDIA_ROOT=TEST_PRIVATE, MSG91_AUTH_KEY="", MSG91_OTP_TEMPLATE_ID="", DEBUG=False)
class SmsOffTests(APITestCase):
    """SMS codes switched off (the launch default, until DLT approval): direct signup, admin confirms the number by call."""

    @classmethod
    def setUpTestData(cls):
        User.objects.create_superuser("admin@pakkatrip.com", "admin123")

    def setUp(self):
        cache.clear()
        bank = {"ifsc_lookup": lambda code: {"bank": "HDFC Bank", "branch": "Kaza", "city": "Kaza", "imps": True, "neft": True},
                "create_contact": lambda *a, **k: {"id": "cont_1"}, "create_fund_account": lambda *a, **k: {"id": "fa_1"}}
        for name, fn in bank.items():
            p = mock.patch(f"payments.razorpay.{name}", side_effect=fn)
            p.start()
            self.addCleanup(p.stop)

    def as_admin(self):
        r = self.client.post("/api/auth/login/", {"email": "admin@pakkatrip.com", "password": "admin123"}, format="json")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])

    def test_off_by_default_and_signup_needs_no_code(self):
        self.assertFalse(self.client.get("/api/public/config/").data["sms_otp_enabled"])
        self.assertEqual(self.client.post("/api/public/partner/otp/", {"phone": SIGNUP["phone"]}, format="json").status_code, 400)
        r = self.client.post("/api/public/partner/signup/", SIGNUP, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        op = Operator.objects.get(contact_phone=SIGNUP["phone"])
        self.assertEqual((op.status, op.phone_verified_at), ("pending", None))
        self.assertIsNone(User.objects.get(email=SIGNUP["email"]).phone_verified_at)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])
        v = self.client.get("/api/operator/verification/").data
        self.assertEqual((v["sms_otp"], v["phone"]["verified"]), (False, False))
        self.assertEqual(self.client.post("/api/operator/verification/phone/otp/", format="json").status_code, 400)
        # an operator can't confirm their own number
        self.assertEqual(self.client.post(f"/api/admin/operators/{op.id}/phone/confirm/", format="json").status_code, 403)

    def test_admin_confirms_the_number_by_call_and_operator_reaches_bronze(self):
        r = self.client.post("/api/public/partner/signup/", SIGNUP, format="json")
        op = Operator.objects.get(contact_phone=SIGNUP["phone"])
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])
        self.assertEqual(self.client.put("/api/operator/bank-account/", BANK, format="json").status_code, 200)
        self.as_admin()
        self.client.post(f"/api/admin/bank-accounts/{op.id}/verify/", format="json")
        r = self.client.post(f"/api/admin/operators/{op.id}/phone/confirm/", format="json")
        self.assertEqual((r.status_code, r.data["phone"]["verified"], r.data["tier"]), (200, True, "bronze"))
        self.assertEqual(self.client.post(f"/api/admin/operators/{op.id}/phone/confirm/", format="json").status_code, 400)

    def test_admin_switch_needs_msg91_keys(self):
        self.as_admin()
        body = {"fee_rate": 2.5, "fee_min": 49, "require_verified": True, "sms_otp_enabled": True}
        r = self.client.put("/api/admin/settings/", body, format="json")
        self.assertEqual(r.status_code, 400)
        with override_settings(MSG91_AUTH_KEY="key", MSG91_OTP_TEMPLATE_ID="tpl"):
            r = self.client.put("/api/admin/settings/", body, format="json")
        self.assertEqual((r.status_code, r.data["sms_otp_enabled"]), (200, True))
        self.assertTrue(self.client.get("/api/public/config/").data["sms_otp_enabled"])
