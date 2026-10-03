import io
import json
import shutil
import tempfile
from datetime import timedelta

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from bookings.models import Booking
from core.demo_seed import seed
from inventory.models import Departure
from operators.models import Operator


TEST_MEDIA = tempfile.mkdtemp(prefix="pakkatrip-test-media-")


@override_settings(MEDIA_ROOT=TEST_MEDIA)   # never touch real uploads (seed() wipes the media folder)
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

    def test_package_needs_four_to_eight_photos(self):
        self.login("himalayan@pakkatrip.com", "operator123")
        r = self.client.post("/api/operator/packages/", self._package_form(3), format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertIn("between 4 and 8", r.data["detail"])

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
    def _book(self, dep, seats, **extra):
        body = {"departure_id": dep.id, "seats": seats, "name": "Guest Traveller", "phone": "9123456780", "email": "guest@example.com",
                "co_travellers": ["Friend One"], "payment_method": "upi", "payment_detail": "GPay", **extra}
        return self.client.post("/api/public/bookings/", body, format="json")

    def test_guest_booking_reaches_operator_and_updates_seats(self):
        dep = Departure.objects.get(package__title="Dharamshala & McLeodganj", departure_date=self.today + timedelta(days=10))
        r = self._book(dep, 2)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data["amount"], r.data["fee"], r.data["total"]), (10998, 275, 11273))   # 2.5% of 10,998
        dep.refresh_from_db()
        self.assertEqual(dep.booked_seats, 2)
        code, key = r.data["code"], r.data["key"]
        # the operator and the admin both see it
        self.login("himalayan@pakkatrip.com", "operator123")
        self.assertTrue(any(b["id"] == code for b in self.client.get("/api/operator/bookings/").data))
        self.login("admin@pakkatrip.com", "admin123")
        self.assertTrue(any(b["id"] == code for b in self.client.get("/api/admin/bookings/").data))
        # ticket needs the key
        self.client.credentials()
        self.assertEqual(self.client.get(f"/api/public/bookings/{code}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/public/bookings/{code}/?key={key}").status_code, 200)

    def test_public_booking_cannot_overbook_or_use_blocked_date(self):
        self.assertIn("Only 2 seats", self._book(self.two_left, 3).data["detail"])
        self.assertEqual(self._book(self.blocked, 1).status_code, 400)
        self.assertEqual(self._book(self.sold_out, 1).status_code, 400)

    def test_minimum_fee_and_card_number_guard(self):
        dep = Departure.objects.filter(package__title="Rishikesh Rafting & Camping", departure_date__gt=self.today,
                                       status="open").order_by("departure_date").first()
        r = self.client.post("/api/public/quote/", {"departure_id": dep.id, "seats": 1}, format="json")
        self.assertEqual(r.data["fee"], 82)    # 2.5% of 3,299 = 82
        r = self._book(dep, 1, payment_method="card", payment_detail="4111 1111 1111 1111")
        self.assertEqual(r.status_code, 400)

    def test_customer_cancellation_follows_policy(self):
        dep = Departure.objects.get(package__title="Dharamshala & McLeodganj", departure_date=self.today + timedelta(days=10))
        r = self._book(dep, 1)
        self.assertEqual(r.data["refund_quote"]["pct"], 100)    # 10 days before → full refund of package amount
        r = self.client.post(f"/api/public/bookings/{r.data['code']}/cancel/", {"key": r.data["key"]}, format="json")
        self.assertEqual(r.data["display"], "cancelled")
        self.assertEqual(r.data["refund"], 5499)                  # fee kept
        dep.refresh_from_db()
        self.assertEqual(dep.booked_seats, 0)

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
