import base64
import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from bookings.models import Booking
from catalog.models import City, Package
from core.models import PlatformSetting
from inventory.models import Departure
from operators.models import Operator
from payments.models import Payment, Refund


class CashfreeAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email="admin@pakkatrip.com", password="adminpassword", role="admin")
        self.city_del = City.by_name("Delhi")
        self.city_man = City.by_name("Manali")
        self.op_user = User.objects.create_user(email="operator@pakkatrip.com", password="oppassword", role="operator")
        self.operator = Operator.objects.create(
            business_name="Himalayan Rides", slug="himalayan-rides", owner_name="Owner",
            contact_phone="9876543210", contact_email="himalayan@pakkatrip.com",
            city=self.city_del, status=Operator.Status.VERIFIED, tier=Operator.Tier.GOLD
        )
        self.package = Package.objects.create(
            operator=self.operator, title="Manali Adventure", from_city=self.city_del, to_city=self.city_man,
            nights=3, price_per_person=Decimal("2000.00"), status=Package.Status.APPROVED
        )
        self.departure = Departure.objects.create(
            package=self.package,
            departure_date=timezone.localdate() + timezone.timedelta(days=10),
            total_seats=20, booked_seats=0, held_seats=0
        )

    def test_admin_settings_can_toggle_payment_gateway(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        token = str(RefreshToken.for_user(self.admin).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        res = self.client.get("/api/admin/settings/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("active_payment_gateway", res.data)
        self.assertIn("cashfree_configured", res.data)

        # Set to cashfree
        put_res = self.client.put("/api/admin/settings/", {
            "fee_rate": 2.5,
            "fee_min": 49,
            "require_verified": True,
            "active_payment_gateway": "cashfree",
        }, format="json")
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.data["active_payment_gateway"], "cashfree")

        # Verify public config returns cashfree
        cfg_res = self.client.get("/api/public/config/")
        self.assertEqual(cfg_res.status_code, 200)
        self.assertEqual(cfg_res.data["active_payment_gateway"], "cashfree")

    @patch("payments.cashfree.create_order")
    def test_create_booking_with_cashfree(self, mock_create_order):
        mock_create_order.return_value = {
            "cf_order_id": "146216000000",
            "order_id": "PTTEST_123",
            "payment_session_id": "session_test_xyz123",
            "order_status": "ACTIVE",
        }

        # Set active gateway to cashfree
        PlatformSetting.put("active_payment_gateway", "cashfree")

        res = self.client.post("/api/public/bookings/", {
            "departure_id": self.departure.id,
            "seats": 2,
            "name": "Arun Kumar",
            "phone": "9876543210",
            "email": "arun@example.com",
            "co_travellers": ["Pooja"],
        }, format="json")

        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["gateway"], "cashfree")
        self.assertIn("cashfree", res.data)
        self.assertEqual(res.data["cashfree"]["payment_session_id"], "session_test_xyz123")

        # Check payment record
        booking = Booking.objects.get(booking_code=res.data["code"])
        pay = booking.payments.first()
        self.assertEqual(pay.gateway, "cashfree")
        self.assertEqual(pay.status, Payment.Status.CREATED)

    @patch("payments.cashfree.fetch_order")
    @patch("payments.cashfree.fetch_order_payments")
    def test_verify_cashfree_payment(self, mock_fetch_payments, mock_fetch_order):
        PlatformSetting.put("active_payment_gateway", "cashfree")
        booking = Booking.objects.create(
            booking_code="PT24999", departure=self.departure, package=self.package,
            operator=self.operator, source=Booking.Source.ONLINE, lead_name="Arun",
            lead_phone="9876543210", lead_email="arun@example.com", seats=2,
            price_per_person=Decimal("2000.00"), base_amount=Decimal("4000.00"),
            fee_rate=Decimal("2.5"), convenience_fee=Decimal("100.00"), total_amount=Decimal("4100.00"),
            status=Booking.Status.PENDING_PAYMENT, guest_token="guest_secret_token"
        )
        self.departure.held_seats = 2
        self.departure.save()

        cf_order_id = "PT24999_12345"
        Payment.objects.create(booking=booking, gateway="cashfree", gateway_order_id=cf_order_id, amount=Decimal("4100.00"))

        mock_fetch_order.return_value = {"order_id": cf_order_id, "order_amount": 4100.0, "order_status": "PAID"}
        mock_fetch_payments.return_value = [{
            "cf_payment_id": 11223344,
            "payment_status": "SUCCESS",
            "payment_amount": 4100.0,
            "payment_group": "upi",
            "payment_method": {"upi": {"upi_id": "success@cashfree"}},
        }]

        res = self.client.post(f"/api/public/bookings/{booking.booking_code}/pay/verify/", {
            "key": "guest_secret_token",
            "gateway": "cashfree",
            "order_id": cf_order_id,
            "signature": "mock_cf_signature",
        }, format="json")

        self.assertEqual(res.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.departure.refresh_from_db()
        self.assertEqual(self.departure.booked_seats, 2)
        self.assertEqual(self.departure.held_seats, 0)

    @patch("payments.cashfree.fetch_order")
    @patch("payments.cashfree.fetch_order_payments")
    def test_cashfree_webhook_success(self, mock_fetch_payments, mock_fetch_order):
        booking = Booking.objects.create(
            booking_code="PT24888", departure=self.departure, package=self.package,
            operator=self.operator, source=Booking.Source.ONLINE, lead_name="Karan",
            lead_phone="9876543210", lead_email="karan@example.com", seats=1,
            price_per_person=Decimal("2000.00"), base_amount=Decimal("2000.00"),
            fee_rate=Decimal("2.5"), convenience_fee=Decimal("50.00"), total_amount=Decimal("2050.00"),
            status=Booking.Status.PENDING_PAYMENT, guest_token="guest_secret_karan"
        )
        self.departure.held_seats = 1
        self.departure.save()

        cf_order_id = "PT24888_67890"
        Payment.objects.create(booking=booking, gateway="cashfree", gateway_order_id=cf_order_id, amount=Decimal("2050.00"))

        mock_fetch_order.return_value = {"order_id": cf_order_id, "order_amount": 2050.0, "order_status": "PAID"}
        mock_fetch_payments.return_value = [{
            "cf_payment_id": 55667788,
            "payment_status": "SUCCESS",
            "payment_amount": 2050.0,
            "payment_group": "card",
            "payment_method": {"card": {"card_number": "4111111111111111", "card_network": "VISA"}},
        }]

        webhook_body = json.dumps({
            "type": "PAYMENT_SUCCESS_WEBHOOK",
            "data": {
                "order": {"order_id": cf_order_id},
                "payment": {"cf_payment_id": 55667788, "payment_status": "SUCCESS"},
            }
        })
        timestamp = "1728512999"
        sig = base64.b64encode(
            hmac.new(settings.CASHFREE_SECRET_KEY.encode(), f"{timestamp}{webhook_body}".encode(), hashlib.sha256).digest()
        ).decode()

        res = self.client.post(
            "/api/payments/cashfree/webhook/",
            data=webhook_body,
            content_type="application/json",
            HTTP_X_WEBHOOK_TIMESTAMP=timestamp,
            HTTP_X_WEBHOOK_SIGNATURE=sig,
        )

        self.assertEqual(res.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.departure.refresh_from_db()
        self.assertEqual(self.departure.booked_seats, 1)
        self.assertEqual(self.departure.held_seats, 0)
