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

Payments are simulated (no gateway yet): only a label like "Card ending 4242" is stored, never card numbers.

## Useful commands (from `backend\`)

| Command | What it does |
|---|---|
| `manage.py seed_demo --reset` | Wipe and reload the demo data (also: Admin → Settings → Reset demo data, development only) |
| `manage.py complete_trips` | Mark finished trips' bookings as completed — schedule nightly |
| `manage.py test api` | Run the API tests (login, role access, overbooking, seat counters) |
| `manage.py createsuperuser` | Create another admin login |

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
