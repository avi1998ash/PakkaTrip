# PakkaTrip — project handoff (as of 3 Oct 2026)

I'm building **PakkaTrip**, an Indian travel marketplace. Local tour operators list trip packages (e.g. Delhi → Manali, 2N/3D) and travellers compare and book them instead of using WhatsApp/Instagram DMs. Operators list free with **no commission**; travellers pay a **convenience fee of 2.5% (minimum ₹49)** on online bookings. Brand: navy `#0B2E59` + saffron `#F28C28` + green `#15803D`; Hinglish touches ("Pakka booking", "Bharosa" badge).

## Locations (Windows)
- Root: `C:\Users\Admin\OneDrive\Documents\Custom Office Templates\New\`
- `demo site\` — original HTML prototypes (localStorage only): `pakkatrip.html` (traveller), `pakkatrip-admin.html` (admin + operator), `pakkatrip-data.js` (shared demo data), plus `PakkaTrip-Prototype-Documentation.docx` and `PakkaTrip-Database-Design.docx`.
- `pakkatrip-platform\` — the real app (Django + React + PostgreSQL). **This is what we work on now.**

## Stack and environment
- Backend: Django 5.2, Django REST Framework, SimpleJWT, psycopg 3, Pillow, python-dotenv. Python 3.13, virtualenv at `backend\.venv`.
- Frontend: React 19 + Vite 7 + Tailwind 4 + React Router 7. Node 24 is installed at `C:\Program Files\nodejs` (it may not be on PATH in tool shells; prefix PATH).
- Database: PostgreSQL 18 (service `postgresql-x64-18`; psql at `C:\Program Files\PostgreSQL\18\bin\psql.exe`, not on PATH). Database `pakkatrip`, owned by its own role `pakkatrip` (has CREATEDB for tests). Credentials and the secret key are in `backend\.env`, which git ignores. Created by `database\setup_db.sql`, which the user ran as postgres.
- Vite (port 5173) proxies `/api` and `/media` to Django (port 8000), so no CORS setup is needed.

## Run it
- `backend\`: `.venv\Scripts\python.exe manage.py runserver`
- `frontend\`: `npm run dev`
- Open http://localhost:5173
- Other commands: `manage.py seed_demo --reset`, `manage.py complete_trips` (schedule nightly), `manage.py test api` (23 tests, all passing).

## Logins (demo data)
- Traveller (at `/account`): priya@example.com / travel123. Guests can also book without an account.
- Admin (at `/partner/login`): admin@pakkatrip.com / admin123
- Operators (at `/partner/login`): himalayan@pakkatrip.com, and also ganga@, rajputana@, shimla@, kasol@, awadh@, konkan@, chardham@, manali@ (all @pakkatrip.com) / operator123
- On the partner login, the email decides admin vs operator. Wrong details show "Invalid credentials". The traveller and partner logins refuse each other's accounts.

## Backend layout (`backend\`)
| App | Holds |
|---|---|
| `accounts` | `User` (email login; role = admin / operator / traveller; phone) |
| `operators` | `Operator` (status pending/verified/suspended/rejected; rating cache; trips_run_offline), `OperatorMember` (user ↔ operator) |
| `catalog` | `City`, `Package` (soft delete, pickup_point, status draft/pending_review/approved/rejected/unlisted), `PackageImage` (1–8 per package, cover, order; files in `backend\media\packages\<id>\`), `PackageFacility` (meals/accommodation/transport/activities/places/other), `PackageItineraryDay`, `STANDARD_FACILITIES`; `media.py` handles upload validation (re-encoded to JPEG, max 1600px, EXIF stripped), facilities and itinerary |
| `inventory` | `Departure` (total_seats, booked_seats, held_seats, status open/blocked/cancelled; DB CHECK `booked + held ≤ total`; one per package per date) |
| `bookings` | `Booking` (booking_code `PT24001…` from a PostgreSQL sequence; snapshots of price, fee and fee rate; source online/offline; statuses pending_confirmation/confirmed/completed/cancelled; `guest_token` for guest ticket access), `BookingTraveller`. **`services.py` is the only place seat counts change** (row lock + checks): offline booking, confirm, cancel (customer → policy refund, fee kept; operator/admin → full refund incl. fee), online booking, price quote, mark completed |
| `payments` | `Payment` (demo gateway; stores only a label like "Card · ending 4242"), `Refund` |
| `reviews` | `Review` (one per booking, only after the trip; operator reply; rating caches refreshed) |
| `core` | `PlatformSetting` (fee rate %, min fee, require-verified-operator), `CancellationRule` (8+ days 100%, 3–7 days 50%, <3 days 0%), `AuditLog`; demo seed (`demo_seed.py`, `demo_media.py`, `demo_itineraries.json`) |
| `api` | All REST endpoints, permissions, tests |

## API (`/api/...`)
- **Auth:** `auth/login` (partner), `auth/refresh`, `auth/me` (any role).
- **Admin (`admin/...`):** dashboard, nav-counts, operators (CRUD, verify; delete becomes suspend if they have bookings), packages (CRUD; GET detail for review; approve/reject/unlist; approval needs a verified operator unless the setting is off), bookings (list, detail, cancel), settings (GET/PUT), reset-demo (only when DEBUG).
- **Operator (`operator/...`, always scoped to the signed-in operator):** dashboard, nav-counts, packages (multipart create/edit with images, cover, facilities, itinerary, pickup), facility-options, departures (create, edit seats, block/unblock, delete if no history, offline booking), bookings (confirm/cancel), earnings, reviews (reply).
- **Public (`public/...`, no login needed):** auth/signup, auth/login (travellers only), home, config (fee, policy, cities), packages (search), packages/<id>, quote, bookings (create), bookings/find (code + phone → key), bookings/lookup (signed-in bookings + saved guest keys), bookings/<code> (owner or `?key=`), cancel, review. Rate limit of 20/min on login, signup and find.

## Frontend layout (`frontend\src\`)
- **Traveller site** (`public\`, routes under `/`): Home, Search (filters/sort done client-side), Trip (`/trips/:id`: gallery, highlights, live dates, itinerary, inclusions, operator, reviews, policy, booking box), Book (`/book/:id`, 4 steps: travellers → review with server quote → dummy UPI/Card/Netbanking → confirmation), Ticket (`/ticket/:code`: e-ticket, dummy QR, download as HTML, print), MyBookings (tabs, cancel with refund preview, rate trip, find booking), Account (login/signup/guest). Styles in `public.css`, extracted from `demo site\pakkatrip.html` and scoped under `.pub`; icons in `public\iconPaths.js` come from the prototype. Guest ticket keys are kept in localStorage as `pakkatrip_my_tickets`.
- **Partner portal** (routes `/partner/login`, `/admin/*`, `/operator/*`): admin pages (Dashboard, Operators, Packages with a Review popup showing photos and facilities, Bookings, Settings) and operator pages (Dashboard, My Packages, PackageEditor full page at `/operator/packages/new` and `/:id/edit`, Seat Inventory with RedBus-style seat grid, My Bookings, My Earnings, Reviews). Shared code: `components\` (ui, feedback modal/toasts, Shell, bookings, ImagesField with drag-reorder, Facilities, Gallery with lightbox, PackageForm), `lib\` (api with JWT refresh, auth context, format, useApi).
- One JWT session per browser for every role; `homeFor(role)` picks the landing page.

## Demo data (`seed_demo --reset`; dates are relative to the day it's run)
- 9 operators: Himalayan Rides, Ganga Travels, Rajputana Journeys, Shimla Tours, Kasol Adventures (unverified), Awadh Travels, Konkan Explorers, Chardham Yatra (unverified), Manali Express.
- 17 packages, each with 4 drawn placeholder photos, facilities, itinerary and pickup point.
- About 49 departures, 337 bookings, about 55 reviews.
- Test scenarios on Himalayan Rides:
  - Manali Weekend Escape, +7 days: 15 booked + 3 pending = 2 left
  - Jim Corbett, +5 days: sold out
  - Dharamshala, +10 days: all 20 free
  - Manali Weekend Escape, +21 days: blocked
- Priya owns one upcoming, one completed (left unreviewed) and one cancelled booking.

## Gotchas
- Reseeding **deletes `media\packages`** (all uploaded photos). Tests use a temporary media folder and clear the rate-limit cache in `setUp`.
- Timestamps are stored in UTC. Always use `localtime(x).date()` or `timezone.localdate()` for dates (an IST midnight bug was fixed).
- Annotated querysets ignore the model's default ordering, so add `.order_by()` explicitly.
- The desktop preview tool's `launch.json` points at another project. Start servers from the shell instead.

## Known gaps / next steps
- Real payment gateway (e.g. Razorpay), plus seat holds during payment (`seat_holds` is in the design doc, not built).
- Emails/SMS/WhatsApp tickets.
- Operators can't edit the itinerary or pickup point yet (the API supports them; the PackageEditor UI doesn't).
- Admin can't add photos or facilities (the admin package form edits basics only).
- OTP login by mobile number.
- Operator KYC document upload and bank accounts/payouts (in the design doc, not built).
- Production deployment: DEBUG off, serve `/media` from a web server or object storage, schedule `complete_trips` nightly.
