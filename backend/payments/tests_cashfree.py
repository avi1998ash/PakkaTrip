from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from bookings.models import Booking
from bookings.services import (create_online_booking, process_refund,
                               settle_cashfree_payment)
from catalog.models import City, Package
from core.models import PlatformSetting
from inventory.models import Departure
from operators.models import Operator
from payments import cashfree
from payments.models import Payment, Refund


class CashfreeUnitTests(TestCase):
    def test_enabled(self):
        self.assertTrue(cashfree.enabled())

    def test_method_label(self):
        upi_pay = {"payment_method": {"upi": {"upi_id": "success@cashfree"}}, "payment_group": "upi"}
        m, lbl = cashfree.method_label(upi_pay)
        self.assertEqual(m, "upi")
        self.assertIn("success@cashfree", lbl)

        card_pay = {"payment_method": {"card": {"card_number": "4111111111111234", "card_network": "VISA"}}, "payment_group": "card"}
        m, lbl = cashfree.method_label(card_pay)
        self.assertEqual(m, "card")
        self.assertIn("VISA", lbl)
        self.assertIn("1234", lbl)

    def test_webhook_signature_verification(self):
        timestamp = "1728512345"
        raw_body = b'{"data":{"order":{"order_id":"test_1"}},"type":"PAYMENT_SUCCESS_WEBHOOK"}'
        import base64, hashlib, hmac
        from django.conf import settings
        expected_sig = base64.b64encode(
            hmac.new(settings.CASHFREE_SECRET_KEY.encode(), f"{timestamp}{raw_body.decode()}".encode(), hashlib.sha256).digest()
        ).decode()

        self.assertTrue(cashfree.verify_webhook_signature(timestamp, raw_body, expected_sig))
        self.assertFalse(cashfree.verify_webhook_signature(timestamp, raw_body, "invalid_sig"))


class CashfreeIntegrationTests(TestCase):
    def setUp(self):
        self.city_del = City.by_name("Delhi")
        self.city_man = City.by_name("Manali")
        self.op_user = User.objects.create_user(email="testop@pakkatrip.com", password="password123", role="operator")
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

    @patch("payments.cashfree.fetch_order")
    @patch("payments.cashfree.fetch_order_payments")
    def test_settle_cashfree_payment_success(self, mock_fetch_payments, mock_fetch_order):
        booking = create_online_booking(
            departure_id=self.departure.id, seats=2, lead_name="Priya Sharma",
            lead_phone="9876543210", lead_email="priya@example.com", co_travellers=["Rahul"]
        )
        cf_order_id = f"{booking.booking_code}_test"
        Payment.objects.create(
            booking=booking, gateway="cashfree", gateway_order_id=cf_order_id, amount=booking.total_amount
        )

        self.departure.refresh_from_db()
        self.assertEqual(self.departure.held_seats, 2)
        self.assertEqual(self.departure.booked_seats, 0)

        mock_fetch_order.return_value = {
            "order_id": cf_order_id,
            "order_amount": float(booking.total_amount),
            "order_status": "PAID"
        }
        mock_fetch_payments.return_value = [{
            "cf_payment_id": 99887766,
            "payment_status": "SUCCESS",
            "payment_amount": float(booking.total_amount),
            "payment_group": "upi",
            "payment_method": {"upi": {"upi_id": "success@cashfree"}}
        }]

        settle_cashfree_payment(booking.pk, order_id=cf_order_id, cf_payment_id="99887766", signature="test_sig_123")

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.departure.refresh_from_db()
        self.assertEqual(self.departure.held_seats, 0)
        self.assertEqual(self.departure.booked_seats, 2)

        payment = booking.payments.get(gateway_order_id=cf_order_id)
        self.assertEqual(payment.status, Payment.Status.CAPTURED)
        self.assertEqual(payment.gateway_payment_id, "99887766")
        self.assertEqual(payment.gateway_signature, "test_sig_123")
        self.assertEqual(payment.method, "upi")

    @patch("payments.cashfree.create_refund")
    def test_cashfree_refund_process(self, mock_create_refund):
        booking = create_online_booking(
            departure_id=self.departure.id, seats=1, lead_name="Test User",
            lead_phone="9876543210", lead_email="user@test.com", co_travellers=[]
        )
        cf_order_id = f"{booking.booking_code}_ref_test"
        payment = Payment.objects.create(
            booking=booking, gateway="cashfree", gateway_order_id=cf_order_id,
            amount=booking.total_amount, status=Payment.Status.CAPTURED
        )
        refund = Refund.objects.create(
            booking=booking, payment=payment, amount=booking.total_amount,
            refund_pct=Decimal("100.00"), initiated_by="admin", status=Refund.Status.PENDING
        )

        mock_create_refund.return_value = {
            "cf_refund_id": "cf_ref_12345",
            "refund_id": f"rf_{booking.booking_code}_{refund.pk}",
            "refund_status": "SUCCESS"
        }

        process_refund(refund.pk)
        refund.refresh_from_db()
        self.assertEqual(refund.status, Refund.Status.PROCESSED)
        self.assertEqual(refund.gateway_refund_id, "cf_ref_12345")
