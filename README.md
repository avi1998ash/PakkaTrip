# PakkaTrip — traveller site + Admin & Operator Portal

Django + Django REST Framework API, React + Vite + Tailwind frontend, PostgreSQL database, JWT login.
Same screens and rules as the prototypes in `../demo site/` (`pakkatrip.html` and `pakkatrip-admin.html`).

| URL (http://localhost:5173) | What |
|---|---|
| `/` | Traveller site: home, `/search`, `/trips/<id>`, `/book/<id>`, `/ticket/<code>`, `/my-bookings`, `/account` |
| `/partner/login` | Admin + operator portal |

```
pakkatrip-platform/
├── database/setup_db.sql   creates the `pakkatrip` database and app user (run once)
├── backend/                Django project (config/) + apps
│   ├── accounts/           User (email login, role: admin / operator / traveller)
│   ├── operators/          Operator, OperatorMember (which login belongs to which business)
│   ├── catalog/            City, Package
│   ├── inventory/          Departure (seat counters + no-overbooking CHECK)
│   ├── bookings/           Booking, BookingTraveller, services.py (all seat changes)
│   ├── payments/           Payment, Refund
│   ├── reviews/            Review
│   ├── core/               PlatformSetting, CancellationRule, AuditLog, demo seed
│   └── api/                REST endpoints, permissions, tests
└── frontend/               React app (src/pages/admin, src/pages/operator)
```

## First-time setup (Windows)

0. **Config files**: copy `backend\.env.example` to `backend\.env` and `database\setup_db.example.sql` to
   `database\setup_db.sql`, then put the same new password in both (and a long random `DJANGO_SECRET_KEY`).
1. **Create the database** (asks for your `postgres` password once):
   ```
   "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -f database\setup_db.sql
   ```
2. **Backend** — from `backend\`:
   ```
   .venv\Scripts\python.exe manage.py migrate
   .venv\Scripts\python.exe manage.py seed_demo
   .venv\Scripts\python.exe manage.py runserver
   ```
   (If `.venv` is missing: `py -m venv .venv` then `.venv\Scripts\pip install -r requirements.txt`.)
3. **Frontend** — from `frontend\`, in a second terminal:
   ```
   npm install
   npm run dev
   ```
4. Open http://localhost:5173

## Logins (demo data)

| Role | Where | Email | Password |
|---|---|---|---|
| Traveller | `/account` | priya@example.com | travel123 |
| Admin | `/partner/login` | admin@pakkatrip.com | admin123 |
| Operator | `/partner/login` | himalayan@pakkatrip.com (also ganga@, rajputana@, shimla@, kasol@, awadh@, konkan@, chardham@, manali@) | operator123 |

The partner login decides where you land from the email: admin → Admin Dashboard, operator → that operator's dashboard.
Travellers can also book as guests; a guest's ticket opens with a private key saved on their device
(or recovered with booking ID + mobile number via "Find a booking").

Payments go through **Razorpay** (see "Payments" below). Only a label like "Visa ending 1111" or a UPI ID is stored, never card numbers.

## Useful commands (from `backend\`)

| Command | What it does |
|---|---|
| `manage.py seed_demo --reset` | Wipe and reload the demo data (also: Admin → Settings → Reset demo data, development only) |
| `manage.py complete_trips` | Mark finished trips' bookings as completed — schedule nightly |
| `manage.py payment_jobs` | Release seats from unpaid checkouts and retry failed refunds — schedule every 5 minutes |
| `manage.py test api` | Run the API tests (login, role access, overbooking, seat counters) |
| `manage.py createsuperuser` | Create another admin login |

## Payments (Razorpay)

1. Put the keys in `backend/.env`: `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` (Dashboard → Account & Settings → API keys; use `rzp_test_` keys until launch).
2. Checkout: `POST /api/public/bookings/` holds the seats (`pending_payment`, counted in `held_seats`) and creates a Razorpay order.
   The traveller pays in Razorpay Checkout; `POST /api/public/bookings/<code>/pay/verify/` checks the signature, fetches the payment
   from Razorpay (capturing it if only authorised) and confirms the booking. Closing checkout calls `/pay/abandon/` to release the seats.
3. Unpaid holds expire after `PAYMENT_HOLD_MINUTES` (default 15). If money arrives after the seats were resold, it is refunded in full automatically.
4. Cancellations send the refund to Razorpay (policy amount for travellers, everything for operator/admin cancellations).
5. Webhook (needs a public HTTPS URL, so production/staging only): add `https://<your-domain>/api/payments/razorpay/webhook/`
   on the Razorpay dashboard with events `payment.captured`, `payment.authorized`, `order.paid`, `refund.processed`, `refund.failed`,
   and put its secret in `RAZORPAY_WEBHOOK_SECRET`. It confirms bookings even if the traveller closes the tab right after paying.
6. Test mode: UPI ID `success@razorpay` (or `failure@razorpay`), or any card from Razorpay's test-card list. Unpaid checkouts never show
   up for operators, admins or in My Bookings.

## Operator bank details & payouts

- Operators add bank details at **Operator → Bank & Payouts** (owner login only). Account number and PAN are encrypted
  with `FIELD_ENCRYPTION_KEY` (core/crypto.py); screens and the API only ever show the last 4 characters. The IFSC is checked
  against Razorpay's IFSC directory. Changing verified details puts the account back to "awaiting verification" and pauses payouts.
- Admins verify or send back details at **Admin → Payouts**. Verifying creates the Razorpay objects for the current payout mode.
- **Operator share** = base fare of each online booking (the convenience fee stays with PakkaTrip). Traveller cancellation: the
  operator keeps the part not refunded. Operator/admin cancellation: nothing. Offline bookings are paid to the operator directly.
- **Payout mode** (Admin → Settings):
  - `payouts` (default) — RazorpayX. A booking's share becomes due when the trip completes (traveller cancellations: once the
    date has passed). Admin clicks **Pay** to send everything due to an operator in one IMPS transfer (idempotency key, so retries
    never pay twice). Failed/reversed payouts put their bookings back in the due list. Needs `RAZORPAYX_ACCOUNT_NUMBER`.
  - `route` — Razorpay Route. When a payment is captured, the operator's share is transferred to their linked account **on hold**;
    `complete_trips` releases it after the trip; cancellations reverse the refunded part before refunding. Route must be enabled
    on the Razorpay account by Razorpay (not available on this account yet), and the linked-account category values in
    payments/razorpay.py should be re-checked against Razorpay's docs at that point. Bookings whose transfer fails fall back to payouts.
- `payment_jobs` also refreshes open payouts and releases Route transfers; webhooks handle `payout.*` and `transfer.failed`.

## How overbooking is prevented

Each departure row stores `total_seats`, `booked_seats` (confirmed + completed) and `held_seats` (pending).
Every seat change goes through `bookings/services.py`, which locks the departure row (`SELECT … FOR UPDATE`)
inside a transaction, and PostgreSQL rejects any update where `booked_seats + held_seats > total_seats`.

## Configuration

`backend/.env` holds the secret key and database password (generated locally — never commit it).
Set `DJANGO_DEBUG=False` and `DJANGO_ALLOWED_HOSTS` for production; demo reset is disabled when DEBUG is off.

## Branching & CI

`main` (released, tagged) ← `release/*` / `hotfix/*` ← `develop` ← `feature/<name>/<ticket>`.
See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow; GitHub Actions runs the tests and build on every PR.
