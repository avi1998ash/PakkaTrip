# Running PakkaTrip locally — start and check

Quick guide for starting the app on Windows and confirming it works. First-time setup (database, `.env`) is in
[README.md](README.md#first-time-setup-windows).

You need **two terminals**: one for the Django API (port 8000), one for the React site (port 5173).
The site at 5173 forwards `/api` and `/media` to 8000, so **both must be running**.

## 1. Start

**Check PostgreSQL is running** (service `postgresql-x64-18`):

```
sc query postgresql-x64-18
```

If it says `STOPPED`, start it: `net start postgresql-x64-18` (run as Administrator).

**Terminal 1: backend** (from `pakkatrip-platform\backend`):

```
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
```

`migrate` only does something after you pull new code. Leave this window open. You should see
`Starting development server at http://127.0.0.1:8000/`.

**Terminal 2: frontend** (from `pakkatrip-platform\frontend`):

```
npm install
npm run dev
```

`npm install` is only needed the first time or after `package.json` changes. You should see
`Local: http://localhost:5173/`.

> If `npm` is "not recognized", Node isn't on PATH. Use `"C:\Program Files\nodejs\npm.cmd" run dev`.

## 2. Check it works

| Check | How | Expected |
|---|---|---|
| Backend is up | Open http://localhost:8000/api/public/packages/ | JSON list of trip packages |
| Frontend is up | Open http://localhost:5173 | PakkaTrip home page ("Trip pakka, paisa safe.") |
| Frontend talks to backend | Click **Search trips** on the home page | Trip cards appear |
| Traveller login | http://localhost:5173/account: `priya@example.com` / `travel123` | My Bookings shows Priya's trips |
| Admin login | http://localhost:5173/partner/login: `admin@pakkatrip.com` / `admin123` | Admin Dashboard |
| Operator login | http://localhost:5173/partner/login: `himalayan@pakkatrip.com` / `operator123` | Operator Dashboard |
| Automated tests | In `backend\`: `.venv\Scripts\python.exe manage.py test api` | All tests `OK` |

> **Warning: don't run `seed_demo --reset` on a database you care about.** It wipes every operator, package, booking
> and bank account, and deletes all uploaded package photos (`backend\media\packages`). Use it only on a fresh, empty
> database (plain `seed_demo` does nothing if data already exists). If trips or logins are missing, check that the
> backend is connected to the right database in `backend\.env` before reseeding anything.

## 3. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `localhost refused to connect` / `ERR_CONNECTION_REFUSED` at :5173 | The frontend isn't running. Start Terminal 2 (`npm run dev`) and keep that window open. |
| Site loads but no trips, or "Network error" / 500 on login | The backend isn't running or crashed. Check Terminal 1. |
| Backend error `connection refused` / `password authentication failed` | PostgreSQL is stopped, or the password in `backend\.env` doesn't match `database\setup_db.sql`. |
| `No module named ...` | Reinstall packages: `.venv\Scripts\pip install -r requirements.txt` |
| `Port 5173 is in use` / `port 8000 already in use` | An old server is still running. Close it, or find it with `netstat -ano \| findstr :5173` and end it in Task Manager. |
| Payment step fails | Put Razorpay **test** keys (`rzp_test_...`) in `backend\.env`. See README "Payments". In test mode use UPI `success@razorpay`. |

## 4. Install the apps on a phone (PWA)

The site installs as two phone apps: **PakkaTrip** (orange icon, traveller site) and **PakkaTrip Partner** (navy icon,
opens on partner login). Chrome offers whichever app matches the page you're on.

1. Start the backend as usual, but start the frontend with `npm run dev:lan` instead of `npm run dev`. If Windows
   Firewall asks about Node.js, click **Allow** (private networks).
2. Find the PC's Wi-Fi address with `ipconfig` (IPv4 Address, e.g. `192.168.1.5`). The phone must be on the same Wi-Fi.
3. Chrome only installs apps over HTTPS, so for Wi-Fi testing allow this one address on the phone: open
   `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, enter `http://192.168.1.5:5173`, set it to
   **Enabled** and tap **Relaunch**. Not needed once the site is on a real HTTPS domain.
4. Traveller app: open `http://192.168.1.5:5173` → Chrome menu (⋮) → **Install app** (or **Add to Home screen**).
5. Partner app: open `http://192.168.1.5:5173/partner/login` → Chrome menu (⋮) → **Install app**.

Without internet the apps show a "You're offline" page; prices, seats and bookings are never cached. On iPhone use
Safari → Share → **Add to Home Screen**.

## 5. Stop

Press `Ctrl+C` in each terminal.
