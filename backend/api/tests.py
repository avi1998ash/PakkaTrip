import hashlib
import hmac
import io
import json
import shutil
import tempfile
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from bookings.models import Booking
from core.crypto import decrypt
from core.models import PlatformSetting
from operators.models import OperatorBankAccount
from payments.models import Payment, Payout, Refund, Transfer
from payments.payouts import due_bookings, release_completed_transfers
from core.demo_seed import seed
from inventory.models import Departure
from operators.models import Operator


TEST_MEDIA = tempfile.mkdtemp(prefix="pakkatrip-test-media-")


@override_settings(MEDIA_ROOT=TEST_MEDIA, PRIVATE_MEDIA_ROOT=f"{TEST_MEDIA}/private",   # never touch real uploads (seed() wipes them)
                   RAZORPAY_KEY_ID="rzp_test_unit", RAZORPAY_KEY_SECRET="unit-secret", RAZORPAY_WEBHOOK_SECRET="hook-secret",
                   RAZORPAYX_ACCOUNT_NUMBER="2323230000000000")
class PortalTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        seed(reset=True)
        cls.today = timezone.localdate()
        # Scenario departures from the demo data (Himalayan Rides)
        cls.two_left = Departure.objects.get(package__title="Manali Weekend Escape", departure_date=cls.today + timedelta(days=7))
        cls.sold_out = Departure.objects.get(package__title="Jim Corbett Jungle Stay", departure_date=cls.today + timedelta(days=5))
        cls.blocked = Departure.objects.get(package__title="Manali Weekend Escape", departure_date=cls.today + timedelta(days=21))

    def setUp(self):
        cache.clear()   # login/find rate limits are per-minute; don't let earlier tests trip them
        # Fake Razorpay: orders, payments and refunds live in memory; nothing goes over the network.
        self.rzp_payments, self.rzp_refunds, self.rzp_calls = {}, [], []
        self.payout_state = {"status": "processing"}
        call = lambda name, ret: lambda *a, **k: self.rzp_calls.append((name, a, k)) or ret  # noqa: E731
        fakes = {
            "ifsc_lookup": lambda code: None if code == "ABCD0123456" else {"bank": "HDFC Bank", "branch": "Worli", "city": "Mumbai", "imps": True, "neft": True},
            "create_contact": call("contact", {"id": "cont_1"}),
            "create_fund_account": call("fund_account", {"id": "fa_1"}),
            "create_payout": lambda *a, **k: self.rzp_calls.append(("payout", a, k)) or {"id": "pout_1", **self.payout_state},
            "fetch_payout": lambda pid: {"id": pid, **self.payout_state},
            "create_linked_account": call("linked_account", {"id": "acc_1"}),
            "create_stakeholder": call("stakeholder", {"id": "sth_1"}),
            "request_route_product": call("route_product", {"id": "acc_prd_1"}),
            "set_route_settlement": call("route_settlement", {"id": "acc_prd_1"}),
            "create_transfer": lambda *a, **k: self.rzp_calls.append(("transfer", a, k)) or {"id": f"trf_{len(self.rzp_calls)}"},
            "release_transfer": call("release", {}),
            "reverse_transfer": call("reverse", {}),
            "create_order": lambda amount, receipt, notes=None: {"id": f"order_{receipt}", "amount": int(amount * 100), "currency": "INR"},
            "fetch_payment": lambda pid: dict(self.rzp_payments[pid]),
            "capture_payment": lambda pid, amount: {**self.rzp_payments[pid], "status": "captured"},
            "refund_payment": lambda pid, amount, notes=None: self.rzp_refunds.append((pid, amount)) or {"id": f"rfnd_{len(self.rzp_refunds)}", "status": "processed"},
        }
        for name, fn in fakes.items():
            patcher = mock.patch(f"payments.razorpay.{name}", side_effect=fn)
            patcher.start()
            self.addCleanup(patcher.stop)

    def login(self, email, password):
        r = self.client.post("/api/auth/login/", {"email": email, "password": password}, format="json")
        if r.status_code == 200:
            self.client.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])
        return r

    # ---- login & roles
    def test_login_detects_role_from_email(self):
        self.assertEqual(self.login("admin@pakkatrip.com", "admin123").data["user"]["role"], "admin")
        r = self.login("himalayan@pakkatrip.com", "operator123")
        self.assertEqual(r.data["user"]["role"], "operator")
        self.assertEqual(r.data["user"]["operator"]["name"], "Himalayan Rides")

    def test_invalid_credentials(self):
        for email, pw in (("himalayan@pakkatrip.com", "wrong"), ("nobody@x.com", "x")):
            r = self.login(email, pw)
            self.assertEqual(r.status_code, 401)
            self.assertEqual(r.data["detail"], "Invalid credentials")

    def test_operator_cannot_use_admin_api(self):
        self.login("himalayan@pakkatrip.com", "operator123")
        self.assertEqual(self.client.get("/api/admin/bookings/").status_code, 403)

    def test_admin_cannot_use_operator_api(self):
        self.login("admin@pakkatrip.com", "admin123")
        self.assertEqual(self.client.get("/api/operator/bookings/").status_code, 403)

    def test_operator_sees_only_own_bookings(self):
        self.login("himalayan@pakkatrip.com", "operator123")
        names = {b["operator_name"] for b in self.client.get("/api/operator/bookings/").data}
        self.assertEqual(names, {"Himalayan Rides"})
        other = Booking.objects.exclude(operator__business_name="Himalayan Rides").first()
        self.assertEqual(self.client.get(f"/api/operator/bookings/{other.booking_code}/").status_code, 404)

    # ---- seat inventory
    def test_scenarios_match_prototype(self):
        self.login("himalayan@pakkatrip.com", "operator123")
        deps = {d["id"]: d for d in self.client.get("/api/operator/departures/").data}
        self.assertEqual((deps[self.two_left.id]["booked"], deps[self.two_left.id]["pending"], deps[self.two_left.id]["available"]), (15, 3, 2))
        self.assertEqual(deps[self.sold_out.id]["state"], "soldout")
        self.assertEqual(deps[self.blocked.id]["state"], "blocked")

    def test_overbooking_is_refused(self):
        self.login("himalayan@pakkatrip.com", "operator123")
        body = {"customer": "Test", "phone": "9876543210", "travellers": 3, "status": "confirmed"}
        r = self.client.post(f"/api/operator/departures/{self.two_left.id}/bookings/", body, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Only 2 seats available", r.data["detail"])
        body["travellers"] = 2
        self.assertEqual(self.client.post(f"/api/operator/departures/{self.two_left.id}/bookings/", body, format="json").status_code, 201)
        self.two_left.refresh_from_db()
        self.assertEqual(self.two_left.available_seats, 0)

    def test_blocked_date_refuses_bookings(self):
        self.login("himalayan@pakkatrip.com", "operator123")
        body = {"customer": "Test", "phone": "9876543210", "travellers": 1, "status": "confirmed"}
        r = self.client.post(f"/api/operator/departures/{self.blocked.id}/bookings/", body, format="json")
        self.assertEqual(r.status_code, 400)

    def test_confirm_and_cancel_move_seat_counters(self):
        self.login("himalayan@pakkatrip.com", "operator123")
        pending = Booking.objects.filter(departure=self.two_left, status=Booking.Status.PENDING_CONFIRMATION).first()
        self.client.post(f"/api/operator/bookings/{pending.booking_code}/confirm/")
        self.two_left.refresh_from_db()
        self.assertEqual((self.two_left.booked_seats, self.two_left.held_seats), (15 + pending.seats, 3 - pending.seats))
        self.client.post(f"/api/operator/bookings/{pending.booking_code}/cancel/")
        self.two_left.refresh_from_db()
        self.assertEqual(self.two_left.booked_seats, 15)

    def test_total_seats_cannot_drop_below_sold(self):
        self.login("himalayan@pakkatrip.com", "operator123")
        r = self.client.patch(f"/api/operator/departures/{self.two_left.id}/", {"total_seats": 10}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("can't go below 18", r.data["detail"])

    # ---- admin rules
    def test_unverified_operator_package_cannot_be_approved(self):
        self.login("admin@pakkatrip.com", "admin123")
        pkg = Operator.objects.get(business_name="Kasol Adventures").packages.first()
        r = self.client.post(f"/api/admin/packages/{pkg.id}/approve/")
        self.assertEqual(r.status_code, 400)

    def test_admin_cancel_refunds_fee(self):
        self.login("admin@pakkatrip.com", "admin123")
        b = Booking.objects.filter(status=Booking.Status.CONFIRMED, source="online").first()
        r = self.client.post(f"/api/admin/bookings/{b.booking_code}/cancel/")
        self.assertEqual(r.data["status"], "cancelled")
        self.assertEqual(r.data["refund"], b.total_amount)

    # ---- photos & facilities
    def _jpeg(self, name="p.jpg", size=(800, 600)):
        buf = io.BytesIO()
        Image.new("RGB", size, (200, 120, 40)).save(buf, "JPEG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")

    def _package_form(self, n_images, **extra):
        return {"title": "Test Trip", "from_city": "Delhi", "to_city": "Agra", "nights": 1, "price": 2500, "default_seats": 20,
                "images": json.dumps([f"n:{i}" for i in range(n_images)]), "cover": "n:1",
                "new_images": [self._jpeg(f"p{i}.jpg") for i in range(n_images)],
                "facilities": json.dumps({"meals": ["Breakfast", "breakfast"], "places": ["Taj Mahal", "Agra Fort"], "bogus": ["x"]}), **extra}

    def test_package_needs_one_to_eight_photos(self):
        self.login("himalayan@pakkatrip.com", "operator123")
        r = self.client.post("/api/operator/packages/", self._package_form(0), format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertIn("between 1 and 8", r.data["detail"])
        r = self.client.post("/api/operator/packages/", self._package_form(9), format="multipart")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/operator/packages/", self._package_form(1, cover="n:0"), format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(len(r.data["images"]), 1)
        self.assertTrue(r.data["images"][0]["is_cover"])

    def test_package_saves_photos_cover_and_facilities(self):
        self.login("himalayan@pakkatrip.com", "operator123")
        r = self.client.post("/api/operator/packages/", self._package_form(4), format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(len(r.data["images"]), 4)
        self.assertEqual([i["is_cover"] for i in r.data["images"]], [False, True, False, False])
        self.assertEqual(r.data["facilities"]["meals"], ["Breakfast"])            # de-duplicated
        self.assertEqual(r.data["facilities"]["places"], ["Taj Mahal", "Agra Fort"])
        self.assertEqual(r.data["status"], "pending")
        # Reorder + remove one + add one on edit
        ids = [f"e:{i['id']}" for i in r.data["images"]]
        form = self._package_form(1)
        form["images"] = json.dumps([ids[3], "n:0", ids[0], ids[1]])
        form["cover"] = "n:0"
        r2 = self.client.patch(f"/api/operator/packages/{r.data['id']}/", form, format="multipart")
        self.assertEqual(r2.status_code, 200, r2.data)
        self.assertEqual(r2.data["images"][0]["id"], int(ids[3][2:]))
        self.assertTrue(r2.data["images"][1]["is_cover"])

    def test_non_image_upload_rejected(self):
        self.login("himalayan@pakkatrip.com", "operator123")
        form = self._package_form(4)
        form["new_images"][2] = SimpleUploadedFile("evil.jpg", b"not really an image", content_type="image/jpeg")
        r = self.client.post("/api/operator/packages/", form, format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertIn("not a valid image", r.data["detail"])

    def test_public_page_shows_only_approved_packages(self):
        approved = Operator.objects.get(business_name="Himalayan Rides").packages.filter(status="approved").first()
        r = self.client.get(f"/api/public/packages/{approved.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["images"]), 4)
        self.assertTrue(r.data["facilities"]["places"])
        pending = Operator.objects.get(business_name="Kasol Adventures").packages.first()
        self.assertEqual(self.client.get(f"/api/public/packages/{pending.id}/").status_code, 404)

    def test_admin_review_shows_facilities(self):
        self.login("admin@pakkatrip.com", "admin123")
        pkg = Operator.objects.get(business_name="Kasol Adventures").packages.first()
        r = self.client.get(f"/api/admin/packages/{pkg.id}/")
        self.assertEqual(r.data["facilities"]["activities"], ["Trekking", "Camping"])
        self.assertEqual(len(r.data["images"]), 4)

    # ---- traveller site
    def _checkout(self, dep, seats):
        body = {"departure_id": dep.id, "seats": seats, "name": "Guest Traveller", "phone": "9123456780", "email": "guest@example.com",
                "co_travellers": ["Friend One"]}
        return self.client.post("/api/public/bookings/", body, format="json")

    def _pay(self, checkout, status="captured", signature=None):
        """What Razorpay checkout's success handler sends back, signed with the (test) key secret."""
        order_id, pid = checkout["razorpay"]["order_id"], f"pay_{checkout['code']}"
        self.rzp_payments[pid] = {"id": pid, "order_id": order_id, "amount": checkout["razorpay"]["amount"], "status": status,
                                  "method": "upi", "vpa": "guest@okhdfc"}
        sig = signature or hmac.new(b"unit-secret", f"{order_id}|{pid}".encode(), hashlib.sha256).hexdigest()
        return self.client.post(f"/api/public/bookings/{checkout['code']}/pay/verify/",
                                {"key": checkout["key"], "razorpay_order_id": order_id, "razorpay_payment_id": pid,
                                 "razorpay_signature": sig}, format="json")

    def _book(self, dep, seats):
        r = self._checkout(dep, seats)
        self.assertEqual(r.status_code, 201, r.data)
        return self._pay(r.data)

    def dharamshala(self):
        return Departure.objects.get(package__title="Dharamshala & McLeodganj", departure_date=self.today + timedelta(days=10))

    def test_checkout_holds_seats_until_paid(self):
        dep = self.dharamshala()
        r = self._checkout(dep, 2)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["razorpay"]["amount"], 1127300)     # Rs 11,273 in paise
        dep.refresh_from_db()
        self.assertEqual((dep.booked_seats, dep.held_seats), (0, 2))
        # an unpaid checkout isn't a booking yet: no ticket, not in the operator's list
        self.assertEqual(self.client.get(f"/api/public/bookings/{r.data['code']}/?key={r.data['key']}").status_code, 404)
        self.login("himalayan@pakkatrip.com", "operator123")
        self.assertFalse(any(b["id"] == r.data["code"] for b in self.client.get("/api/operator/bookings/").data))

    def test_guest_booking_reaches_operator_and_updates_seats(self):
        dep = self.dharamshala()
        r = self._book(dep, 2)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data["amount"], r.data["fee"], r.data["total"]), (10998, 275, 11273))   # 2.5% of 10,998
        self.assertEqual(r.data["payment"], "UPI · guest@okhdfc")
        dep.refresh_from_db()
        self.assertEqual((dep.booked_seats, dep.held_seats), (2, 0))
        code, key = r.data["code"], r.data["key"]
        self.assertEqual(Payment.objects.get(booking__booking_code=code).status, "captured")
        # verifying twice (checkout callback + webhook) doesn't double-count seats
        again = self._pay({"code": code, "key": key, "razorpay": {"order_id": f"order_{code}", "amount": 1127300}})
        self.assertEqual(again.status_code, 200)
        dep.refresh_from_db()
        self.assertEqual(dep.booked_seats, 2)
        # the operator and the admin both see it
        self.login("himalayan@pakkatrip.com", "operator123")
        self.assertTrue(any(b["id"] == code for b in self.client.get("/api/operator/bookings/").data))
        self.login("admin@pakkatrip.com", "admin123")
        self.assertTrue(any(b["id"] == code for b in self.client.get("/api/admin/bookings/").data))
        # ticket needs the key
        self.client.credentials()
        self.assertEqual(self.client.get(f"/api/public/bookings/{code}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/public/bookings/{code}/?key={key}").status_code, 200)

    def test_forged_or_failed_payment_is_rejected(self):
        r = self._checkout(self.dharamshala(), 1)
        self.assertEqual(self._pay(r.data, signature="0" * 64).status_code, 400)
        self.assertEqual(self._pay(r.data, status="failed").status_code, 400)
        self.assertEqual(Booking.objects.get(booking_code=r.data["code"]).status, "pending_payment")

    def test_abandoned_and_expired_holds_release_seats(self):
        dep = self.dharamshala()
        r = self._checkout(dep, 3)
        self.client.post(f"/api/public/bookings/{r.data['code']}/pay/abandon/", {"key": r.data["key"]}, format="json")
        dep.refresh_from_db()
        self.assertEqual(dep.held_seats, 0)
        self.assertEqual(Booking.objects.get(booking_code=r.data["code"]).status, "expired")
        r = self._checkout(dep, 2)
        Booking.objects.filter(booking_code=r.data["code"]).update(created_at=timezone.now() - timedelta(minutes=16))
        self.client.post("/api/public/quote/", {"departure_id": dep.id, "seats": 1}, format="json")   # page loads sweep old holds
        dep.refresh_from_db()
        self.assertEqual(dep.held_seats, 0)

    def test_late_payment_after_seats_gone_is_refunded(self):
        r = self._checkout(self.two_left, 2)
        b = Booking.objects.get(booking_code=r.data["code"])
        Booking.objects.filter(pk=b.pk).update(created_at=timezone.now() - timedelta(minutes=16))
        self.assertEqual(self._book(self.two_left, 2).status_code, 200)   # hold lapses; someone else takes the last 2 seats
        with self.captureOnCommitCallbacks(execute=True):
            late = self._pay(r.data)
        self.assertEqual(late.status_code, 409)
        refund = Refund.objects.get(booking=b)
        self.assertEqual((refund.amount, refund.status), (b.total_amount, "processed"))
        self.assertIn((f"pay_{b.booking_code}", b.total_amount), self.rzp_refunds)

    def test_public_booking_cannot_overbook_or_use_blocked_date(self):
        self.assertIn("Only 2 seats", self._checkout(self.two_left, 3).data["detail"])
        self.assertEqual(self._checkout(self.blocked, 1).status_code, 400)
        self.assertEqual(self._checkout(self.sold_out, 1).status_code, 400)

    def test_minimum_fee(self):
        dep = Departure.objects.filter(package__title="Rishikesh Rafting & Camping", departure_date__gt=self.today,
                                       status="open").order_by("departure_date").first()
        r = self.client.post("/api/public/quote/", {"departure_id": dep.id, "seats": 1}, format="json")
        self.assertEqual(r.data["fee"], 82)    # 2.5% of 3,299 = 82

    def test_customer_cancellation_follows_policy_and_refunds_via_razorpay(self):
        dep = self.dharamshala()
        r = self._book(dep, 1)
        self.assertEqual(r.data["refund_quote"]["pct"], 100)    # 10 days before -> full refund of package amount
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(f"/api/public/bookings/{r.data['code']}/cancel/", {"key": r.data["key"]}, format="json")
        self.assertEqual(r.data["display"], "cancelled")
        self.assertEqual(r.data["refund"], 5499)                  # fee kept
        self.assertEqual(self.rzp_refunds, [(f"pay_{r.data['code']}", 5499)])
        self.assertEqual(Refund.objects.get(booking__booking_code=r.data["code"]).gateway_refund_id, "rfnd_1")
        dep.refresh_from_db()
        self.assertEqual(dep.booked_seats, 0)

    def test_webhook_confirms_payment_when_browser_closed(self):
        r = self._checkout(self.dharamshala(), 1)
        order_id, pid = r.data["razorpay"]["order_id"], "pay_webhook"
        self.rzp_payments[pid] = {"id": pid, "order_id": order_id, "amount": r.data["razorpay"]["amount"], "status": "captured",
                                  "method": "card", "card": {"network": "Visa", "last4": "1111"}}
        body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": pid, "order_id": order_id}}}}).encode()
        url = "/api/payments/razorpay/webhook/"
        self.assertEqual(self.client.generic("POST", url, body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE="x").status_code, 400)
        sig = hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
        self.assertEqual(self.client.generic("POST", url, body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=sig).status_code, 200)
        b = Booking.objects.get(booking_code=r.data["code"])
        self.assertEqual(b.status, "confirmed")
        self.assertEqual(b.payments.get().method_detail, "Visa ending 1111")

    # ---- operator bank details & settlements
    BANK = {"holder_name": "Himalayan Rides", "account_number": "50100111122223333", "confirm_account_number": "50100111122223333",
            "ifsc": "hdfc0000001", "account_type": "current", "pan": "abcpt1234k", "business_type": "proprietorship",
            "address_line": "12 Main Market", "address_city": "Delhi", "address_state": "Delhi", "pincode": "110001"}

    def test_operator_bank_details_are_encrypted_and_masked(self):
        self.login("himalayan@pakkatrip.com", "operator123")
        self.assertEqual(self.client.put("/api/operator/bank-account/", {**self.BANK, "confirm_account_number": "1"}, format="json").status_code, 400)
        self.assertEqual(self.client.put("/api/operator/bank-account/", {**self.BANK, "ifsc": "ABCD0123456"}, format="json").status_code, 400)
        r = self.client.put("/api/operator/bank-account/", self.BANK, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data["bank"]["account"], r.data["bank"]["pan"], r.data["bank"]["status"]), ("XXXX XXXX 3333", "XXXXXX234K", "pending"))
        self.assertNotIn("50100111122223333", json.dumps(r.data, default=str))
        acct = OperatorBankAccount.objects.get(operator__business_name="Himalayan Rides")
        self.assertNotIn("50100111122223333", acct.account_number_enc)
        self.assertEqual((decrypt(acct.account_number_enc), decrypt(acct.pan_enc)), ("50100111122223333", "ABCPT1234K"))

    def test_admin_verifies_bank_and_pays_out_completed_trips(self):
        op = Operator.objects.get(business_name="Himalayan Rides")
        due = sum(share for _, share in due_bookings(op))
        self.assertGreater(due, 0)
        self.login("admin@pakkatrip.com", "admin123")
        self.assertEqual(self.client.post("/api/admin/payouts/", {"operator_id": op.id}, format="json").status_code, 400)  # not verified yet
        r = self.client.post(f"/api/admin/bank-accounts/{op.id}/verify/", format="json")
        self.assertEqual((r.status_code, r.data["status"], r.data["payouts_ready"]), (200, "verified", True))
        row = next(o for o in self.client.get("/api/admin/payouts/").data["operators"] if o["id"] == op.id)
        self.assertEqual(row["due"], due)
        r = self.client.post("/api/admin/payouts/", {"operator_id": op.id}, format="json")
        self.assertEqual((r.status_code, r.data["status"]), (201, "processing"), r.data)
        payout = Payout.objects.get(pk=r.data["id"])
        self.assertEqual((payout.amount, payout.bookings.count() > 0), (due, True))
        self.assertEqual(self.rzp_calls[-1][2]["idempotency_key"], payout.idempotency_key)
        self.assertEqual(self.client.post("/api/admin/payouts/", {"operator_id": op.id}, format="json").status_code, 400)   # nothing left
        # the bank bounces it: the bookings become due again
        self.payout_state = {"status": "reversed", "status_details": {"description": "Beneficiary account closed"}}
        r = self.client.post(f"/api/admin/payouts/{payout.id}/refresh/", format="json")
        self.assertEqual((r.data["status"], r.data["failure_reason"]), ("reversed", "Beneficiary account closed"))
        self.assertEqual(sum(share for _, share in due_bookings(op)), due)

    def test_changing_bank_details_pauses_payouts(self):
        op = Operator.objects.get(business_name="Himalayan Rides")
        self.login("admin@pakkatrip.com", "admin123")
        self.client.post(f"/api/admin/bank-accounts/{op.id}/verify/", format="json")
        self.login("himalayan@pakkatrip.com", "operator123")
        self.assertEqual(self.client.put("/api/operator/bank-account/", self.BANK, format="json").data["bank"]["status"], "pending")
        self.login("admin@pakkatrip.com", "admin123")
        r = self.client.post("/api/admin/payouts/", {"operator_id": op.id}, format="json")
        self.assertIn("no verified bank account", r.data["detail"])

    def test_route_mode_transfers_on_hold_reverses_and_releases(self):
        PlatformSetting.put("payout_mode", "route")
        op = Operator.objects.get(business_name="Himalayan Rides")
        self.login("admin@pakkatrip.com", "admin123")
        self.assertTrue(self.client.post(f"/api/admin/bank-accounts/{op.id}/verify/", format="json").data["route_ready"])
        self.client.credentials()
        dep = self.dharamshala()
        with self.captureOnCommitCallbacks(execute=True):
            kept = self._book(dep, 1).data
        with self.captureOnCommitCallbacks(execute=True):
            cancelled = self._book(dep, 1).data
        t = Transfer.objects.get(booking__booking_code=kept["code"])
        self.assertEqual((t.status, t.amount, t.gateway_transfer_id.startswith("trf_")), ("on_hold", 5499, True))
        self.assertFalse(any(b.booking_code == kept["code"] for b, _ in due_bookings(op)))   # settled by Route, not payouts
        # traveller cancels 10 days out: 100% of the package amount comes back from the operator's transfer, then is refunded
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/api/public/bookings/{cancelled['code']}/cancel/", {"key": cancelled["key"]}, format="json")
        names = [c[0] for c in self.rzp_calls]
        self.assertEqual(Transfer.objects.get(booking__booking_code=cancelled["code"]).status, "reversed")
        self.assertIn("reverse", names)
        self.assertEqual(self.rzp_refunds[-1], (f"pay_{cancelled['code']}", 5499))
        # the kept trip runs: its transfer is released to the operator
        Booking.objects.filter(booking_code=kept["code"]).update(status="completed")
        self.assertEqual(release_completed_transfers(), 1)
        self.assertEqual(Transfer.objects.get(booking__booking_code=kept["code"]).status, "released")

    def test_traveller_accounts(self):
        r = self.client.post("/api/public/auth/login/", {"email": "himalayan@pakkatrip.com", "password": "operator123"}, format="json")
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/api/public/auth/signup/", {"name": "New Person", "phone": "9000000001", "email": "new@example.com",
                                                          "password": "secret12"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.client.post("/api/auth/login/", {"email": "new@example.com", "password": "secret12"}, format="json").status_code, 401)
        r = self.client.post("/api/public/auth/login/", {"email": "priya@example.com", "password": "travel123"}, format="json")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])
        mine = self.client.post("/api/public/bookings/lookup/", {"items": []}, format="json").data
        self.assertEqual(sorted(b["display"] for b in mine), ["cancelled", "completed", "upcoming"])
        done = next(b for b in mine if b["display"] == "completed")
        self.assertTrue(done["can_review"])
        r = self.client.post(f"/api/public/bookings/{done['code']}/review/", {"rating": 5, "text": "Lovely trip, very well organised."}, format="json")
        self.assertTrue(r.data["reviewed"])
        self.assertEqual(self.client.post(f"/api/public/bookings/{done['code']}/review/", {"rating": 4, "text": "Second review attempt"},
                                          format="json").status_code, 400)

    def test_operator_and_admin_cannot_portal_login_as_traveller_and_vice_versa(self):
        self.assertEqual(self.login("priya@example.com", "travel123").status_code, 401)

    # ---- pre-launch: itinerary + pickup, booking email, password reset
    def test_package_saves_itinerary_and_pickup_point(self):
        self.login("himalayan@pakkatrip.com", "operator123")
        days = [{"title": "Delhi → Agra", "text": "Leave at 6 am."}, {"title": "Taj Mahal at sunrise", "text": ""}, {"title": "Extra day", "text": "dropped"}]
        r = self.client.post("/api/operator/packages/", self._package_form(4, pickup_point=" Kashmere Gate, Delhi · 6:00 AM ",
                                                                           itinerary=json.dumps(days)), format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["pickup_point"], "Kashmere Gate, Delhi · 6:00 AM")
        self.assertEqual([d["title"] for d in r.data["itinerary"]], ["Delhi → Agra", "Taj Mahal at sunrise"])   # 1 night = 2 days
        self.assertEqual(r.data["itinerary"][0]["text"], "Leave at 6 am.")

    @override_settings(EMAIL_HOST_USER="pakkatrip@gmail.com", EMAIL_HOST_PASSWORD="apppassword", SITE_URL="https://pakkatrip.online")
    def test_paid_booking_emails_the_ticket_once(self):
        from django.core import mail
        r = self._checkout(self.dharamshala(), 2)
        with self.captureOnCommitCallbacks(execute=True):
            paid = self._pay(r.data)
        self.assertEqual(paid.status_code, 200, paid.data)
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        code, key = r.data["code"], r.data["key"]
        self.assertEqual(m.to, ["guest@example.com"])
        self.assertIn(code, m.subject)
        self.assertIn(f"https://pakkatrip.online/ticket/{code}?key={key}", m.body)
        self.assertIn("Dharamshala & McLeodganj", m.body)
        self.assertIn("Guest Traveller, Friend One", m.body)
        self.assertIn("₹11,273", m.body)
        self.assertIn(f"/ticket/{code}?key={key}", m.alternatives[0][0])   # HTML version
        with self.captureOnCommitCallbacks(execute=True):   # the webhook confirming it again doesn't send a second email
            self._pay({"code": code, "key": key, "razorpay": {"order_id": r.data["razorpay"]["order_id"], "amount": r.data["razorpay"]["amount"]}})
        self.assertEqual(len(mail.outbox), 1)

    def test_booking_email_failure_does_not_break_payment(self):
        r = self._checkout(self.dharamshala(), 1)   # no SMTP login and DEBUG off: the email can't be sent
        with self.captureOnCommitCallbacks(execute=True):
            paid = self._pay(r.data)
        self.assertEqual(paid.status_code, 200)
        self.assertEqual(Booking.objects.get(booking_code=r.data["code"]).status, "confirmed")

    def _reset_link(self, email):
        from django.core import mail
        r = self.client.post("/api/public/auth/password/forgot/", {"email": email}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        link = next(line for line in mail.outbox[-1].body.splitlines() if "/reset-password?" in line)
        q = dict(p.split("=", 1) for p in link.split("?", 1)[1].split("&"))
        return q["uid"], q["token"]

    @override_settings(EMAIL_HOST_USER="pakkatrip@gmail.com", EMAIL_HOST_PASSWORD="apppassword")
    def test_password_reset_for_traveller_and_operator(self):
        from django.core import mail
        uid, token = self._reset_link("Priya@Example.com")
        url = "/api/public/auth/password/reset/"
        self.assertEqual(self.client.post(url, {"uid": uid, "token": token, "password": "abc"}, format="json").status_code, 400)
        r = self.client.post(url, {"uid": uid, "token": token, "password": "newpass1"}, format="json")
        self.assertEqual((r.status_code, r.data["role"]), (200, "traveller"))
        self.assertEqual(self.client.post("/api/public/auth/login/", {"email": "priya@example.com", "password": "newpass1"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(url, {"uid": uid, "token": token, "password": "another1"}, format="json").status_code, 400)   # used once
        # operators need 8 characters, then log in on the partner portal
        uid, token = self._reset_link("himalayan@pakkatrip.com")
        self.assertEqual(self.client.post(url, {"uid": uid, "token": token, "password": "short12"}, format="json").status_code, 400)
        r = self.client.post(url, {"uid": uid, "token": token, "password": "operator456"}, format="json")
        self.assertEqual(r.data["role"], "operator")
        self.assertEqual(self.login("himalayan@pakkatrip.com", "operator456").status_code, 200)
        # unknown emails get the same answer and no email; a forged token is refused
        sent = len(mail.outbox)
        r = self.client.post("/api/public/auth/password/forgot/", {"email": "nobody@example.com"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), sent)
        self.assertEqual(self.client.post(url, {"uid": uid, "token": "bad-token", "password": "whatever123"}, format="json").status_code, 400)

    @override_settings(EMAIL_HOST_USER="pakkatrip@gmail.com", EMAIL_HOST_PASSWORD="apppassword")
    def test_password_reset_email_is_rate_limited_per_address(self):
        from django.core import mail
        for _ in range(3):
            self.client.post("/api/public/auth/password/forgot/", {"email": "priya@example.com"}, format="json")
        self.assertEqual(len(mail.outbox), 1)
