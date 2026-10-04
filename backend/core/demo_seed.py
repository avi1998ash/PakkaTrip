"""Demo data — the same operators, packages and test scenarios as the HTML prototype.

Deterministic (fixed random seed) so every reset looks the same. Dates are relative to today.
"""
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from decimal import Decimal

from django.db import connection, transaction
from django.utils import timezone

from accounts.models import User
from bookings.models import Booking, BookingTraveller, next_booking_code
from catalog.models import City, Package, PackageFacility, PackageImage, PackageItineraryDay, unique_slug
from core.crypto import encrypt
from core.demo_media import add_demo_media, wipe_media
from core.models import DEFAULT_SETTINGS, AuditLog, CancellationRule, PlatformSetting, fee_for
from inventory.models import Departure
from operators.models import Operator, OperatorBankAccount, OperatorMember
from payments.models import Payment, Payout, Refund, Transfer
from reviews.models import Review, refresh_ratings

ADMIN_EMAIL, ADMIN_PASSWORD = "admin@pakkatrip.com", "admin123"
OPERATOR_PASSWORD = "operator123"
TRAVELLER_EMAIL, TRAVELLER_PASSWORD = "priya@example.com", "travel123"
ITINERARIES = json.loads((Path(__file__).parent / "demo_itineraries.json").read_text(encoding="utf-8"))

OPERATORS = [  # id, name, owner, city, phone, login handle, verified, joined (days ago), trips run before joining
    ("OP101", "Himalayan Rides", "Rakesh Thakur", "Delhi", "9810012345", "himalayan", True, 240, 312),
    ("OP102", "Ganga Travels", "Pooja Negi", "Rishikesh", "9837011122", "ganga", True, 200, 268),
    ("OP103", "Rajputana Journeys", "Vikram Singh Rathore", "Jaipur", "9829033344", "rajputana", True, 180, 190),
    ("OP104", "Shimla Tours", "Anil Chauhan", "Chandigarh", "9876055566", "shimla", True, 150, 154),
    ("OP105", "Kasol Adventures", "Aman Sharma", "Delhi", "9811077788", "kasol", False, 40, 18),
    ("OP106", "Awadh Travels", "Faizan Ahmed", "Lucknow", "9415099900", "awadh", True, 120, 96),
    ("OP107", "Konkan Explorers", "Sneha Naik", "Mumbai", "9820011223", "konkan", True, 90, 141),
    ("OP108", "Chardham Yatra", "Mahesh Rawat", "Dehradun", "9412044556", "chardham", False, 12, 9),
    ("OP109", "Manali Express", "Tenzin Dorje", "Delhi", "9818066778", "manali", True, 100, 205),
]

PACKAGES = [  # id, operator, title, from, to, nights, price, seats, status
    ("PK201", "OP101", "Manali Weekend Escape", "Delhi", "Manali", 2, 6499, 20, "approved"),
    ("PK202", "OP102", "Rishikesh Rafting & Camping", "Delhi", "Rishikesh", 1, 3299, 40, "approved"),
    ("PK203", "OP105", "Kasol & Kheerganga Trek", "Delhi", "Kasol", 2, 5999, 30, "pending_review"),
    ("PK204", "OP103", "Royal Udaipur Getaway", "Delhi", "Udaipur", 2, 7499, 35, "approved"),
    ("PK205", "OP104", "Shimla–Kufri Quick Trip", "Delhi", "Shimla", 1, 4199, 40, "approved"),
    ("PK206", "OP106", "Kashi Darshan", "Lucknow", "Varanasi", 1, 3499, 50, "approved"),
    ("PK207", "OP101", "Jim Corbett Jungle Stay", "Delhi", "Jim Corbett", 1, 4999, 20, "approved"),
    ("PK208", "OP107", "Goa Beach Long Weekend", "Mumbai", "Goa", 3, 11999, 40, "approved"),
    ("PK209", "OP102", "Mussoorie Hill Retreat", "Delhi", "Mussoorie", 1, 3999, 45, "approved"),
    ("PK210", "OP108", "Kedarnath Yatra Package", "Delhi", "Kedarnath", 3, 12499, 40, "pending_review"),
    ("PK211", "OP104", "Kinnaur & Sangla Valley", "Delhi", "Sangla", 3, 14999, 20, "pending_review"),
    ("PK212", "OP103", "Pink City Jaipur Weekend", "Delhi", "Jaipur", 1, 3799, 45, "approved"),
    ("PK213", "OP101", "Dharamshala & McLeodganj", "Delhi", "Dharamshala", 2, 5499, 20, "approved"),
    ("PK214", "OP109", "Manali Volvo Package", "Delhi", "Manali", 2, 5799, 40, "approved"),
    ("PK215", "OP109", "Manali–Kasol Combo", "Delhi", "Manali", 3, 8999, 30, "approved"),
    ("PK216", "OP103", "Pushkar Camel Fair Special", "Delhi", "Pushkar", 1, 2999, 50, "rejected"),
    ("PK217", "OP107", "South Goa & Dudhsagar", "Mumbai", "Goa", 2, 8499, 30, "approved"),
]

NAMES = ["Rohit Verma", "Aditya Mishra", "Neha Yadav", "Saurabh Pandey", "Anjali Tiwari", "Karan Malhotra",
         "Sakshi Jain", "Mohit Saini", "Ritika Agarwal", "Deepak Chauhan", "Shruti Srivastava", "Arjun Bhatt", "Kavya Reddy",
         "Manish Kumar", "Pallavi Joshi", "Harsh Vardhan", "Simran Kaur", "Nikhil Dubey", "Tanya Saxena", "Imran Qureshi"]

REVIEW_TEXTS = {
    5: ["Everything was exactly as promised. Driver was polite and the hotel was clean.",
        "Best weekend trip! Booking on PakkaTrip was so much easier than WhatsApp.",
        "Seat was confirmed instantly, no last-minute surprises. Will book again.",
        "Great trip captain, on-time departure and good food.",
        "Pehli baar bina tension ke trip book ki. Bus time pe aayi, hotel bhi accha tha.",
        "Loved the itinerary — not rushed, and the group was fun."],
    4: ["Good trip overall, bus left 30 minutes late though.", "Hotel was nice, sightseeing felt a bit rushed.",
        "Value for money. Would like more time at the main spot."],
    3: ["Average experience. AC in the bus was not working properly.", "Okay trip, but the itinerary changed without telling us."],
}

CITY_STATES = {"Delhi": "Delhi", "Manali": "Himachal Pradesh", "Rishikesh": "Uttarakhand", "Kasol": "Himachal Pradesh",
               "Udaipur": "Rajasthan", "Shimla": "Himachal Pradesh", "Lucknow": "Uttar Pradesh", "Varanasi": "Uttar Pradesh",
               "Jim Corbett": "Uttarakhand", "Mumbai": "Maharashtra", "Goa": "Goa", "Mussoorie": "Uttarakhand",
               "Kedarnath": "Uttarakhand", "Sangla": "Himachal Pradesh", "Jaipur": "Rajasthan", "Dharamshala": "Himachal Pradesh",
               "Pushkar": "Rajasthan", "Chandigarh": "Chandigarh", "Dehradun": "Uttarakhand"}


class Rnd:
    """Same tiny LCG as the prototype, so the demo matches it."""
    def __init__(self, seed=42):
        self.s = seed

    def __call__(self):
        self.s = (self.s * 9301 + 49297) % 233280
        return self.s / 233280

    def int(self, a, b):
        return a + int(self() * (b - a + 1))

    def pick(self, items):
        return items[int(self() * len(items))]


def wipe():
    """Delete all marketplace data (keeps admin users)."""
    for model in (Review, Transfer, Refund, Payout, Payment, BookingTraveller, Booking, Departure, PackageImage, PackageFacility, PackageItineraryDay):
        model.objects.all().delete()
    wipe_media()
    Package.all_objects.all().delete()
    OperatorMember.objects.all().delete()
    Operator.objects.all().delete()
    User.objects.filter(role__in=[User.Role.OPERATOR, User.Role.TRAVELLER]).delete()
    for model in (City, PlatformSetting, CancellationRule, AuditLog):
        model.objects.all().delete()
    with connection.cursor() as cur:
        cur.execute("ALTER SEQUENCE booking_code_seq RESTART WITH 24001")


@transaction.atomic
def seed(reset=False):
    if reset:
        wipe()
    elif Operator.objects.exists():
        return "Demo data already present (use --reset to replace it)."

    rnd = Rnd()
    today = timezone.localdate()
    now = timezone.now()
    day = lambda n: today + timedelta(days=n)  # noqa: E731
    at = lambda d, minute=0: timezone.make_aware(datetime.combine(d, time(10, 0)) + timedelta(minutes=minute))  # noqa: E731

    admin = User.objects.filter(email=ADMIN_EMAIL).first() or User.objects.create_superuser(ADMIN_EMAIL, ADMIN_PASSWORD)

    for key, value in DEFAULT_SETTINGS.items():
        PlatformSetting.put(key, value)
    for days, pct, label in ((8, 100, "More than 7 days before departure"), (3, 50, "3 to 7 days before departure"),
                             (0, 0, "Less than 3 days before departure")):
        CancellationRule.objects.create(min_days_before=days, refund_pct=pct, label=label, effective_from=day(-365))

    cities = {}
    def city(name):
        if name not in cities:
            cities[name] = City.objects.create(name=name, state=CITY_STATES.get(name, ""), slug=unique_slug(City, name),
                                               is_popular=name in ("Manali", "Rishikesh", "Goa", "Jaipur", "Udaipur"))
        return cities[name]

    ops = {}
    for key, name, owner, cname, phone, handle, verified, joined, trips in OPERATORS:
        user = User.objects.create_user(f"{handle}@pakkatrip.com", OPERATOR_PASSWORD, full_name=owner, role=User.Role.OPERATOR, phone=phone)
        op = Operator.objects.create(
            business_name=name, slug=unique_slug(Operator, name), owner_name=owner, contact_phone=phone,
            contact_email=user.email, city=city(cname), trips_run_offline=trips, created_at=at(day(-joined)),
            status=Operator.Status.VERIFIED if verified else Operator.Status.PENDING,
            verified_at=at(day(-joined + 2)) if verified else None, verified_by=admin if verified else None)
        OperatorMember.objects.create(operator=op, user=user, member_role=OperatorMember.Role.OWNER)
        ops[key] = op

    # Bank details waiting for admin verification (test values; RazorpayX test mode accepts any valid IFSC).
    for key, holder, number, pan in (("OP101", "Himalayan Rides", "50100123456789", "ABCPT1234K"),
                                     ("OP102", "Ganga Travels", "50100987654321", "ABCPN5678L")):
        OperatorBankAccount.objects.create(
            operator=ops[key], holder_name=holder, account_number_enc=encrypt(number), account_last4=number[-4:], ifsc="HDFC0000001",
            bank_name="HDFC Bank", branch="Sandoz House, Worli", account_type="current", pan_enc=encrypt(pan), pan_last4=pan[-4:],
            business_type="proprietorship", address_line="12 Main Market", address_city=ops[key].city.name,
            address_state="Delhi" if key == "OP101" else "Uttarakhand", pincode="110001" if key == "OP101" else "249201")

    pkgs = {}
    for key, opk, title, frm, to, nights, price, seats, status in PACKAGES:
        pkgs[key] = Package.objects.create(
            operator=ops[opk], title=title, slug=unique_slug(Package, title), from_city=city(frm), to_city=city(to),
            nights=nights, price_per_person=Decimal(price), default_seats=seats, status=status,
            approved_by=admin if status == "approved" else None, approved_at=now if status == "approved" else None,
            rejection_reason="Duplicate of an existing listing." if status == "rejected" else "",
            created_at=ops[opk].created_at + timedelta(days=3))

    add_demo_media(pkgs)
    for key, pkg in pkgs.items():
        demo = ITINERARIES[key]
        pkg.pickup_point = demo["pickup"]
        pkg.save(update_fields=["pickup_point"])
        PackageItineraryDay.objects.bulk_create([PackageItineraryDay(package=pkg, day_number=i + 1, title=t, description=x)
                                                 for i, (t, x) in enumerate(demo["itinerary"])])

    conf = PlatformSetting.get_all()
    seq = {"minute": 0}

    def add_dep(pk, offset, total, blocked=False):
        return Departure.objects.create(package=pkgs[pk], departure_date=day(offset), total_seats=total,
                                        status=Departure.Status.BLOCKED if blocked else Departure.Status.OPEN)

    completed = []

    def add_bk(dep, seats, status, source="online"):
        p = dep.package
        booked_on = day(-rnd.int(0, 14)) if dep.departure_date >= today else dep.departure_date - timedelta(days=rnd.int(3, 20))
        base = p.price_per_person * seats
        fee = fee_for(base, conf) if source == "online" else Decimal(0)
        seq["minute"] += 1
        created = at(booked_on, seq["minute"] % 600)
        name, phone = rnd.pick(NAMES), "9" + str(rnd.int(100000000, 999999999))
        st = {"confirmed": Booking.Status.CONFIRMED, "pending": Booking.Status.PENDING_CONFIRMATION,
              "completed": Booking.Status.COMPLETED, "cancelled": Booking.Status.CANCELLED}[status]
        b = Booking.objects.create(
            booking_code=next_booking_code(), departure=dep, package=p, operator=p.operator, source=source,
            lead_name=name, lead_phone=phone, lead_email=f"{name.split()[0].lower()}@example.com" if source == "online" else "",
            seats=seats, price_per_person=p.price_per_person, base_amount=base, fee_rate=Decimal(str(conf["fee_rate_pct"])) if source == "online" else 0,
            convenience_fee=fee, total_amount=base + fee, status=st, created_at=created,
            confirmed_at=created if st in (Booking.Status.CONFIRMED, Booking.Status.COMPLETED) else None,
            cancelled_at=created if st == Booking.Status.CANCELLED else None,
            cancelled_by=Booking.Actor.CUSTOMER if st == Booking.Status.CANCELLED else "")
        BookingTraveller.objects.create(booking=b, full_name=name, is_lead=True)
        if source == "online" and st != Booking.Status.PENDING_CONFIRMATION:
            pay = Payment.objects.create(
                booking=b, gateway_order_id=f"order_demo_{b.booking_code}", gateway_payment_id=f"pay_demo_{b.booking_code}",
                method=Payment.Method.UPI, method_detail="GPay", amount=b.total_amount, created_at=created, paid_at=created,
                status=Payment.Status.PARTIALLY_REFUNDED if st == Booking.Status.CANCELLED else Payment.Status.CAPTURED)
            if st == Booking.Status.CANCELLED:   # customer cancelled early: package amount back, fee kept
                Refund.objects.create(booking=b, payment=pay, amount=base, refund_pct=100, initiated_by="customer",
                                      status=Refund.Status.PROCESSED, processed_at=created, created_at=created)
        if st in (Booking.Status.CONFIRMED, Booking.Status.COMPLETED):
            dep.booked_seats += seats
        elif st == Booking.Status.PENDING_CONFIRMATION:
            dep.held_seats += seats
        dep.save(update_fields=["booked_seats", "held_seats"])
        if st == Booking.Status.COMPLETED:
            completed.append(b)
        return b

    # --- Test scenarios (Himalayan Rides — the demo operator login) ---
    d1 = add_dep("PK201", 7, 20)                       # 15 booked + 3 pending = 2 left
    priya_bookings = []
    for i, t in enumerate((4, 3, 2, 2, 4)):
        b = add_bk(d1, t, "confirmed")
        if i == 0:
            priya_bookings.append(b)
    for t in (2, 1):
        add_bk(d1, t, "pending")
    add_dep("PK201", 21, 20, blocked=True)             # blocked date
    add_dep("PK201", 28, 20)
    d2 = add_dep("PK207", 5, 20)                       # sold out
    for t in (4, 4, 3, 3, 2, 2):
        add_bk(d2, t, "confirmed")
    add_bk(d2, 2, "confirmed", "offline")
    add_bk(add_dep("PK207", 19, 20), 3, "confirmed")
    add_dep("PK213", 10, 20)                           # all 20 available
    add_dep("PK213", 24, 20)
    p1 = add_dep("PK201", -10, 20)                     # past trips, for earnings and reviews
    for i, t in enumerate((3, 2, 4, 2)):
        b = add_bk(p1, t, "completed")
        if i == 3:
            priya_bookings.append(b)
    priya_bookings.append(add_bk(p1, 2, "cancelled"))
    p2 = add_dep("PK207", -18, 20)
    for t in (2, 2, 3):
        add_bk(p2, t, "completed")

    # --- Everyone else: one past and three upcoming departures per live package ---
    for key, opk, *_rest, status in PACKAGES:
        if status != "approved" or opk == "OP101":
            continue
        p = pkgs[key]
        for i, offset in enumerate((-rnd.int(9, 20), rnd.int(3, 9), rnd.int(12, 20), rnd.int(25, 34))):
            dep = add_dep(key, offset, p.default_seats)
            past = offset < 0
            frac = 0.5 + rnd() * 0.45 if past else (rnd() * 0.25 if i == 3 else 0.15 + rnd() * 0.8)
            target, filled = int(p.default_seats * frac), 0
            while filled < target:
                t, r = min(rnd.int(1, 4), target - filled), rnd()
                st = ("cancelled" if r < 0.08 else "completed") if past else ("pending" if r < 0.1 else "cancelled" if r < 0.18 else "confirmed")
                add_bk(dep, t, st, "offline" if rnd() < 0.15 else "online")
                if st != "cancelled":
                    filled += t

    # --- Demo traveller account owns a few bookings, so My Bookings isn't empty ---
    priya = User.objects.create_user(TRAVELLER_EMAIL, TRAVELLER_PASSWORD, full_name="Priya Gupta", phone="9876501234",
                                     role=User.Role.TRAVELLER, created_at=at(day(-60)))
    for b in priya_bookings:
        b.user, b.lead_name, b.lead_phone, b.lead_email, b.source = priya, priya.full_name, priya.phone, priya.email, "online"
        b.save(update_fields=["user", "lead_name", "lead_phone", "lead_email", "source"])
        b.travellers.filter(is_lead=True).update(full_name=priya.full_name)

    # --- Reviews from completed trips (Priya's is left unreviewed so "Rate your trip" can be tried) ---
    for b in completed:
        if b in priya_bookings or rnd() > 0.55:
            continue
        rating = 5 if rnd() < 0.62 else (4 if rnd() < 0.75 else 3)
        reply = "Sorry about that — we have fixed this for upcoming departures. Thank you for the feedback!" if rating == 3 and rnd() < 0.7 else ""
        created = at(b.departure.departure_date + timedelta(days=rnd.int(1, 3)))
        Review.objects.create(booking=b, package=b.package, operator=b.operator, reviewer_name=b.lead_name, rating=rating,
                              comment=rnd.pick(REVIEW_TEXTS[rating]), operator_reply=reply, replied_at=created if reply else None,
                              created_at=created)
    for p in pkgs.values():
        refresh_ratings(p, p.operator)

    return (f"Seeded {Operator.objects.count()} operators, {Package.objects.count()} packages, "
            f"{Departure.objects.count()} departures, {Booking.objects.count()} bookings, {Review.objects.count()} reviews.")

