# PakkaTrip — Master QA Test Plan & Zero-Knowledge Testing Manual

---

## 1. Executive Summary & Project Introduction

### 1.1 What is PakkaTrip?
**PakkaTrip** is a full-stack Indian travel marketplace designed to connect travellers directly with verified local tour operators for multi-day trips (such as *Delhi → Manali*, *Jim Corbett Safari*, *Char Dham Yatra*, *Kasol Weekend Trek*). 

In India, many local tour operators arrange trips through WhatsApp groups or Instagram DMs with informal payments. PakkaTrip replaces informal channels with an end-to-end web platform featuring:
- **Instant Online Booking & Real-Time Seat Availability** (no overbooking possible).
- **Verified Tour Operators** with tiered trust badges (**Bronze**, **Silver**, **Gold**).
- **Digital E-Tickets** with QR codes and instant retrieval for guest travellers.
- **Automated Refund Policies** and **Direct Operator Payouts** via RazorpayX.

---

### 1.2 System Architecture Overview

```
                          ┌────────────────────────────────────────┐
                          │            TRAVELLER SITE              │
                          │        http://localhost:5173/          │
                          └───────────────────┬────────────────────┘
                                              │
                                              ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                                 VITE PROXY (:5173)                                │
│                     Forwards /api and /media to Django (:8000)                    │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    ▼                                           ▼
┌──────────────────────────────────────┐     ┌──────────────────────────────────────┐
│            DJANGO REST API           │     │            PARTNER PORTAL            │
│        http://localhost:8000/api/    │     │  http://localhost:5173/partner/login │
│  (Accounts, Catalog, Bookings, Core) │     │     (Operators & Platform Admins)    │
└───────────────────┬──────────────────┘     └──────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                               POSTGRESQL DATABASE                                 │
│  - Sequence: PT24001, PT24002 (Booking Codes)                                     │
│  - Lock: SELECT ... FOR UPDATE (Prevents double booking)                          │
│  - DB Constraint: CHECK (booked_seats + held_seats <= total_seats)                │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Key Terminology & Domain Glossary

| Term | Definition for QA |
|---|---|
| **Package** | A tour package listed by an operator containing photos, inclusions/facilities, day-by-day itinerary, and pickup point (e.g. *Manali Weekend Trek 2N/3D*). |
| **Departure Date** | A specific calendar date on which a package departs. Each departure date has a fixed seat capacity (`total_seats`), `booked_seats`, and `held_seats`. |
| **Held Seats** | Seats temporarily reserved during checkout (valid for 15 minutes while payment is pending). If unpaid, seats automatically release. |
| **Convenience Fee** | The platform fee charged to travellers on online bookings (**2.5% of base fare, minimum ₹49**). |
| **Base Fare** | The net trip cost set by the tour operator. 100% of the base fare belongs to the operator upon trip completion. |
| **Verification Tiers** | Badges assigned to operators based on verified documents: <br>• **Bronze:** Phone OTP + Bank Details + PAN<br>• **Silver:** PAN + Bank Details + Aadhaar<br>• **Gold:** PAN + Bank Details + Udyam + GSTIN |
| **Guest Token** | A secure token saved in `localStorage` allowing travellers to access their e-ticket without creating an account. |
| **Idempotency** | Protection mechanism preventing duplicate payout transfers if an admin clicks "Pay" multiple times. |

---

## 3. Platform Navigation Sitemap & User Roles

```
PUBLIC TRAVELLER SITE (http://localhost:5173/)
├── / (Home: Search bar, featured trips, verification trust badges)
├── /search (Filter packages by destination, duration, price, operator verification)
├── /trips/:id (Trip Detail: photos, itinerary, facilities, operator profile, live seats)
├── /book/:id (4-Step Checkout: Seats → Review quote → Razorpay Payment → Confirmation)
├── /ticket/:code (E-Ticket with QR code, print, and HTML download)
├── /my-bookings (View bookings, cancellation with refund preview, submit review)
└── /account (Traveller Login / Sign-up)

PARTNER PORTAL (http://localhost:5173/partner/login)
├── OPERATOR DASHBOARD
│   ├── /operator (Metrics, upcoming trips, quick actions)
│   ├── /operator/packages (My Packages list: draft, pending review, approved)
│   ├── /operator/packages/new (Package Editor: photos, itinerary, facilities)
│   ├── /operator/inventory (RedBus-style seat grid management & offline booking entry)
│   ├── /operator/bookings (Confirm/cancel traveller bookings)
│   ├── /operator/verification (Submit PAN, Aadhaar, GSTIN, Udyam for Bronze/Silver/Gold)
│   ├── /operator/bank (Bank account details for RazorpayX payouts)
│   └── /operator/reviews (Read customer reviews & post responses)
│
└── ADMIN PORTAL
    ├── /admin (Platform overview metrics, pending applications counter)
    ├── /admin/applications (Review operator KYC submissions, inspect Aadhaar audit logs)
    ├── /admin/packages (Review & approve/reject operator package submissions)
    ├── /admin/bookings (View all platform bookings, initiate full refund cancellations)
    ├── /admin/payouts (Trigger IMPS transfers to verified operator bank accounts)
    └── /admin/settings (Configure convenience fee %, cancellation rules, reset demo data)
```

---

## 4. Environment Quick Start (Zero-Knowledge Setup)

### Step 1: Confirm Database & Service Status
Open PowerShell and check PostgreSQL service:
```powershell
sc query postgresql-x64-18
```
*If `STOPPED`, start it with `net start postgresql-x64-18` (as Admin).*

### Step 2: Start Django Backend (Port 8000)
```powershell
cd pakkatrip-platform\backend
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
```
*Output should say `Starting development server at http://127.0.0.1:8000/`.*

### Step 3: Start React Frontend (Port 5173)
Open a second PowerShell terminal:
```powershell
cd pakkatrip-platform\frontend
cmd /c npm run dev:lan
```
*Output will display local URL `http://localhost:5173/` and LAN network URL `http://192.168.1.5:5173/`.*

### Step 4: Run Automated API Tests (Verification Check)
In the backend terminal:
```powershell
.venv\Scripts\python.exe manage.py test api
```
*Expected Output:* `Ran 53 tests in ~60s ... OK`

---

## 5. Master Test Credentials & Payment Matrix

### 5.1 Account Login Credentials

| Role | Login Page | Email Address | Password | Assigned Business / Purpose |
|---|---|---|---|---|
| **Traveller** | `/account` | `priya@example.com` | `travel123` | Pre-loaded traveller account with past/upcoming trips. |
| **Admin** | `/partner/login` | `admin@pakkatrip.com` | `admin123` | Master platform administrator account. |
| **Operator (Gold)** | `/partner/login` | `himalayan@pakkatrip.com` | `operator123` | **Himalayan Rides** (Verified Gold Badge). |
| **Operator (Silver)** | `/partner/login` | `ganga@pakkatrip.com` | `operator123` | **Ganga Travels** (Verified Silver Badge). |
| **Operator (Bronze)** | `/partner/login` | `rajputana@pakkatrip.com` | `operator123` | **Rajputana Journeys** (Verified Bronze Badge). |
| **Operator (Verified)** | `/partner/login` | `shimla@pakkatrip.com` | `operator123` | **Shimla Tours**. |
| **Operator (Pending)** | `/partner/login` | `kasol@pakkatrip.com` | `operator123` | **Kasol Adventures** (Awaiting KYC Approval). |
| **Operator (Verified)** | `/partner/login` | `awadh@pakkatrip.com` | `operator123` | **Awadh Travels**. |
| **Operator (Verified)** | `/partner/login` | `konkan@pakkatrip.com` | `operator123` | **Konkan Explorers**. |
| **Operator (Pending)** | `/partner/login` | `chardham@pakkatrip.com` | `operator123` | **Chardham Yatra** (Awaiting KYC Approval). |
| **Operator (Verified)** | `/partner/login` | `manali@pakkatrip.com` | `operator123` | **Manali Express**. |

---

### 5.2 Razorpay Test Payment Credentials

| Payment Mode | Input Details | Expected Outcome |
|---|---|---|
| **UPI Success** | `success@razorpay` | Payment completes successfully -> Booking status `confirmed`. |
| **UPI Failure** | `failure@razorpay` | Payment fails -> Seats released -> Error toast displayed. |
| **Test Card** | Card: `4111 1111 1111 1111`<br>Exp: `12/30`<br>CVV: `123`<br>OTP: `123456` | Razorpay OTP Simulator -> Payment Success -> Confirmation. |
| **Netbanking** | Any Bank (e.g. SBI / HDFC) | Success callback -> Booking confirmed. |

---

## 6. Step-by-Step QA Execution Test Cases

---

### Test Suite 1: Traveller Search, Booking & E-Ticket Management

#### **TC-01: Public Package Search & Filtering**
- **Objective:** Verify travellers can search and filter packages without logging in.
- **Steps:**
  1. Open `http://localhost:5173/` in browser.
  2. Enter "Manali" in the search box and click **Search**.
  3. Apply filters: Duration (2–3 Days), Operator Badge (Gold Verified).
- **Expected Result:** Package list filters in real time. *Manali Weekend Escape* by *Himalayan Rides* is displayed with a Gold badge.

---

#### **TC-02: Package Detail Inspection & Price Quote**
- **Objective:** Verify price quote calculations match platform settings.
- **Steps:**
  1. Click on *Manali Weekend Escape*.
  2. Inspect photo lightbox gallery, inclusions list, and day-by-day itinerary.
  3. Select an open departure date (e.g., +7 days).
  4. Select **2 Travellers** and click **Book Now**.
- **Expected Result:** Server returns exact quote: `Base Fare + 2.5% Convenience Fee (Min ₹49) = Total Price`.

---

#### **TC-03: Razorpay Payment & E-Ticket Generation**
- **Objective:** Verify online checkout and QR code ticket generation.
- **Steps:**
  1. Enter traveller details: Name: *Rohan Sharma*, Age: *28*, Gender: *Male*, Phone: *9876543210*.
  2. Click **Proceed to Pay**.
  3. On Razorpay popup, select **UPI** -> Enter `success@razorpay` -> Click **Pay**.
- **Expected Result:** Payment completes, user lands on `/ticket/PT2400...`. E-Ticket displays booking code, QR code, pickup point, and print/download buttons.

---

#### **TC-04: Guest Ticket Retrieval via Code & Mobile**
- **Objective:** Verify guest travellers can recover tickets without an account.
- **Steps:**
  1. Copy booking code from TC-03 (e.g., `PT24005`).
  2. Open Incognito window -> Go to `http://localhost:5173/my-bookings`.
  3. Click **Find a Booking**.
  4. Enter `PT24005` and phone number `9876543210`.
- **Expected Result:** E-ticket opens successfully and saves key to browser `localStorage`.

---

#### **TC-05: Traveller Cancellation & Policy Refund Calculation**
- **Objective:** Verify refund calculation enforces cancellation rules.
- **Steps:**
  1. Log in as `priya@example.com` / `travel123` at `/account`.
  2. Go to **My Bookings** -> Select an upcoming trip.
  3. Click **Cancel Booking**. Inspect preview popup.
- **Expected Result:** 
  - If departure > 8 days away: 100% base fare refund preview.
  - If 3–7 days away: 50% refund preview.
  - If < 3 days away: 0% refund preview.
  - Confirm cancellation -> Status updates to `cancelled`.

---

### Test Suite 2: Operator Sign-Up, KYC Verification & Package Editor

#### **TC-06: Operator Self-Signup with Mobile/Email OTP**
- **Objective:** Verify new tour operators can sign up.
- **Steps:**
  1. Go to `http://localhost:5173/partner/signup`.
  2. Enter Business Name: *Kullu Treks*, Owner: *Vikram Singh*, Email: *vikram@kullutreks.com*, Mobile: *9988776655*.
  3. Enter OTP displayed on screen/console -> Click **Verify & Sign Up**.
- **Expected Result:** Operator is created with status `pending` and directed to the Operator Dashboard.

---

#### **TC-07: KYC Submission for Verification Tiers**
- **Objective:** Verify submission of PAN, Bank details, GSTIN, Udyam, and Aadhaar.
- **Steps:**
  1. Log in as `kasol@pakkatrip.com` / `operator123` at `/partner/login`.
  2. Go to **Verification**.
  3. Enter PAN: `ABCDE1234F`, Bank Account: `9182736450`, IFSC: `SBIN0001234`.
  4. Enter Aadhaar last 4 digits `4321` + Upload masked Aadhaar sample image.
  5. Enter GSTIN: `07AAAAA0000A1Z5` and Udyam Reg No.
  6. Click **Submit for Verification**.
- **Expected Result:** Account status becomes `awaiting_verification`. Aadhaar document is stored securely in `backend/private_media/` (encrypted).

---

#### **TC-08: Package Creation (Single-Photo Threshold & Facilities)**
- **Objective:** Verify creating a package with 1 to 8 photos.
- **Steps:**
  1. Go to **My Packages -> Add New Package**.
  2. Enter Title: *Kasol River Camping*, City: *Kasol*, Duration: *2 Days / 1 Night*, Pickup: *Bhuntar Bus Stand*.
  3. Upload **1 photo** (verify 1 photo minimum passes validation).
  4. Select facilities: *Meals included*, *Tents*, *Bonfire*.
  5. Add Itinerary Day 1 & Day 2 descriptions.
  6. Click **Submit Package**.
- **Expected Result:** Package is saved with status `pending_review`.

---

#### **TC-09: Seat Inventory Management & Offline Bookings**
- **Objective:** Verify RedBus-style seat grid & offline walk-in bookings.
- **Steps:**
  1. Log in as `himalayan@pakkatrip.com` / `operator123`.
  2. Go to **Seat Inventory** -> Select *Manali Weekend Escape* -> Choose departure date.
  3. Test blocking 2 seats -> Click **Save Inventory**.
  4. Click **Record Offline Booking** -> Enter Name: *Walk-in Guest*, Seats: *2*, Amount Paid: *₹4000*.
- **Expected Result:** Seat grid updates immediately (`booked_seats` increases, available seats decrease).

---

### Test Suite 3: Admin Approval, Document Inspection & Payouts

#### **TC-10: Operator KYC Approval & Aadhaar Audit Logging**
- **Objective:** Verify admin document inspection and audit logging.
- **Steps:**
  1. Log in as `admin@pakkatrip.com` / `admin123` at `/partner/login`.
  2. Go to **Applications** -> Click **Review** on *Kasol Adventures*.
  3. Click **View Masked Aadhaar Document**.
  4. Click **Approve Operator**.
- **Expected Result:** Operator is approved and assigned **Gold Tier**. Viewing Aadhaar creates a record in `backend/core/models.py` (`AuditLog`).

---

#### **TC-11: Package Review & Approval**
- **Objective:** Verify admin package review process.
- **Steps:**
  1. Go to **Admin -> Packages** -> Filter by `pending_review`.
  2. Click **Review** on *Kasol River Camping*.
  3. Inspect photos, facilities, and itinerary. Click **Approve Package**.
- **Expected Result:** Package status becomes `approved` and appears live on the traveller search page.

---

#### **TC-12: Operator Payout Execution via RazorpayX**
- **Objective:** Verify admin payout transfers for completed trips.
- **Steps:**
  1. Go to **Admin -> Payouts**.
  2. Locate a completed trip for *Himalayan Rides*.
  3. Click **Pay Operator**.
  4. Click **Pay Operator** a second time to test idempotency.
- **Expected Result:** IMPS transfer processes via RazorpayX. Duplicate click is safely ignored (idempotency key prevents double payout).

---

### Test Suite 4: Security & Concurrency Verification

#### **TC-13: Overbooking Prevention Under Race Condition**
- **Objective:** Verify PostgreSQL locks prevent double-booking last remaining seat.
- **Steps:**
  1. Open two browser windows (Window A and Window B).
  2. Navigate to a trip departure date with **1 seat left**.
  3. Click **Book** simultaneously in both windows.
- **Expected Result:** Window A succeeds. Window B is blocked with message `"Not enough seats available"`.

---

#### **TC-14: Unpaid Seat Hold Expiration**
- **Objective:** Verify unpaid checkout holds release after 15 minutes.
- **Steps:**
  1. Start checkout for a seat (status becomes `pending_payment`, `held_seats` = 1).
  2. Close tab without paying.
  3. Run `python manage.py payment_jobs` in backend terminal.
- **Expected Result:** Seat hold expires, status changes to released, and seat returns to open inventory.

---

## 7. QA Sign-Off & Verification Summary Checklist

| Module | Verification Criteria | Status (Pass/Fail) |
|---|---|---|
| **Environment** | Django Backend (:8000), Vite Frontend (:5173), PostgreSQL (:5432) running | [ ] PASS |
| **API Test Suite** | All 53 unit tests in `manage.py test api` pass cleanly | [ ] PASS |
| **Traveller Search** | Filters, search bar, and operator verification badges work | [ ] PASS |
| **Booking & Quote** | Server calculates exact 2.5% fee (min ₹49) | [ ] PASS |
| **Razorpay Checkout**| Test UPI `success@razorpay` & test card confirmations work | [ ] PASS |
| **E-Ticket** | QR code, print ticket, and HTML download functional | [ ] PASS |
| **Guest Lookup** | Booking code + phone number recovers ticket in private window | [ ] PASS |
| **Cancellation** | Policy refund percentages (100% / 50% / 0%) calculate accurately | [ ] PASS |
| **Operator Signup** | Mobile/Email OTP validation completes successfully | [ ] PASS |
| **Operator KYC** | PAN, Bank, GSTIN, Udyam, Aadhaar upload calculates tier | [ ] PASS |
| **Package Editor** | 1-photo minimum threshold and multi-day itinerary functional | [ ] PASS |
| **Seat Inventory** | RedBus seat grid blocking & offline cash booking entry functional | [ ] PASS |
| **Admin KYC Audit** | Viewing masked Aadhaar creates audit log record | [ ] PASS |
| **Admin Payouts** | RazorpayX IMPS payout transfer triggers with idempotency | [ ] PASS |
| **Overbooking Lock**| `SELECT ... FOR UPDATE` prevents concurrent overbooking | [ ] PASS |

---

## 8. Troubleshooting & Log Inspection Guide

If any issue occurs during testing, inspect the following log locations:

- **Backend Django Logs:** Printed directly in Terminal 1 or inspect `backend/logs/`.
- **Browser Developer Tools:** Press `F12` -> Check **Console** for JS errors and **Network** tab for `/api/` HTTP status codes (200 OK, 400 Bad Request, 403 Forbidden, 500 Server Error).
- **PostgreSQL Log Files:** Located at `C:\Program Files\PostgreSQL\18\data\log\`.
