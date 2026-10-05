import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { inr, telHref } from '../lib/format'
import { useApi } from '../lib/useApi'
import { PolicyTable } from './PublicLayout'

/* Terms, Privacy, Refund and Contact pages. Business details (legal name, address, support contacts, grievance
   officer) come from the server settings (backend/.env → /api/public/config/), so a domain move or an address
   change needs no code change. Get these pages reviewed by a lawyer before relying on them. */

const UPDATED = '6 October 2026'

function useSite() {
  const { data } = useApi('/public/config/')
  return { cfg: data, site: data?.site }
}

/** A business detail from the server settings; in development, a missing one is flagged so it gets filled in. */
function Val({ v, name }) {
  if (v) return v
  return import.meta.env.DEV ? <mark title={`Set ${name} in backend/.env`}>[{name}]</mark> : '—'
}

function LegalPage({ title, children }) {
  const { hash } = useLocation()
  useEffect(() => { document.title = `${title} — PakkaTrip` }, [title])
  useEffect(() => { if (hash) document.getElementById(hash.slice(1))?.scrollIntoView() }, [hash])
  return (
    <>
      <div className="page-top"><div className="container"><h1 className="legal-title">{title}</h1></div></div>
      <div className="container"><article className="card legal">{children}</article></div>
    </>
  )
}

const Updated = () => <p className="legal-updated">Last updated: {UPDATED}</p>

function GrievanceBlock({ site }) {
  return (
    <dl className="legal-dl">
      <dt>Grievance Officer</dt><dd><Val v={site?.grievance_officer} name="GRIEVANCE_OFFICER_NAME" /></dd>
      <dt>Email</dt><dd>{site?.grievance_email ? <a href={`mailto:${site.grievance_email}`}>{site.grievance_email}</a> : <Val name="GRIEVANCE_OFFICER_EMAIL" />}</dd>
      {site?.grievance_phone && <><dt>Phone</dt><dd><a href={telHref(site.grievance_phone)}>{site.grievance_phone}</a></dd></>}
      <dt>Address</dt><dd><Val v={site?.address} name="BUSINESS_ADDRESS" /></dd>
    </dl>
  )
}

export function Terms() {
  const { site } = useSite()
  const brand = site?.brand || 'PakkaTrip'
  return (
    <LegalPage title="Terms of use">
      <Updated />
      <p>These terms apply when you use {brand} at {site?.domain || 'our website'} or in the {brand} apps. {brand} is run by{' '}
        <b><Val v={site?.legal_name} name="BUSINESS_LEGAL_NAME" /></b> (“{brand}”, “we”, “us”). By booking a trip or creating an account you agree to them.</p>

      <h2>1. What {brand} is</h2>
      <p>{brand} is an online marketplace. Independent tour operators list trip packages, and travellers book and pay for seats on them.
        The operator runs the trip: transport, stay, meals, guides and the itinerary. {brand} provides the website, takes payment,
        issues the e-ticket and handles cancellations and refunds under our <Link to="/refund-policy">Refund policy</Link>.</p>
      <p>We check operators before their trips go live (business, PAN and bank details, mobile number and, for higher tiers, Aadhaar,
        GST or Udyam). The tier shown on each trip tells you which checks the operator has passed. Verification is not a guarantee of
        the operator's service.</p>

      <h2>2. Booking and payment</h2>
      <ul>
        <li>Prices are per person in Indian rupees and include the operator's taxes unless stated otherwise. A convenience fee is added
          to online bookings and shown before you pay.</li>
        <li>Seats are held for a few minutes while you pay. A booking is confirmed only when the payment succeeds.</li>
        <li>Payments are processed by Razorpay. We never see or store your card, UPI PIN or net-banking password.</li>
        <li>Give correct traveller names and a working mobile number. The operator uses them for pickup and to contact you.</li>
      </ul>

      <h2 id="delivery">3. Delivery of your booking</h2>
      <p>We don't ship any physical goods. As soon as your payment succeeds, your e-ticket appears on screen and under{' '}
        <Link to="/my-bookings">My Bookings</Link>. The trip itself is delivered by the operator on the departure date, from the pickup
        point shown on the ticket.</p>

      <h2>4. Cancellations and refunds</h2>
      <p>Cancellations, refunds and what happens if an operator cancels are covered in our <Link to="/refund-policy">Refund policy</Link>,
        which is part of these terms.</p>

      <h2>5. Your responsibilities</h2>
      <ul>
        <li>Reach the pickup point on time and carry a valid government photo ID.</li>
        <li>Follow the operator's safety instructions and local laws. The operator may refuse travel to anyone who is unsafe or abusive,
          without a refund.</li>
        <li>Don't misuse the site: no fake bookings, scraping, or attempts to break its security.</li>
      </ul>

      <h2>6. Operators</h2>
      <p>Operators who list on {brand} must give true business and bank details, run trips as described, and honour confirmed bookings.
        We may suspend an operator or remove trips that break these rules or receive serious complaints. Operators are paid for each booking
        after the trip is completed, less any refunds due to travellers.</p>

      <h2>7. Reviews</h2>
      <p>Only travellers with a completed booking can review a trip. Reviews must be honest and must not contain abuse or personal data.
        We may remove reviews that break these rules.</p>

      <h2>8. Liability</h2>
      <p>The operator is responsible for running the trip and for anything that happens during it. To the extent the law allows,
        {' '}{brand}'s liability for a booking is limited to the amount you paid us for it. Nothing in these terms limits your rights under
        the Consumer Protection Act, 2019.</p>

      <h2>9. Changes and governing law</h2>
      <p>We may update these terms; the date at the top shows the latest version. These terms are governed by the laws of India, and
        courts at <Val v={site?.jurisdiction} name="LEGAL_JURISDICTION_CITY" /> have jurisdiction.</p>

      <h2>10. Complaints</h2>
      <p>Write to us from the <Link to="/contact">Contact page</Link>. If you're not satisfied, contact our Grievance Officer. We
        acknowledge complaints within 48 hours and resolve them within one month.</p>
      <GrievanceBlock site={site} />
    </LegalPage>
  )
}

export function Privacy() {
  const { site } = useSite()
  const brand = site?.brand || 'PakkaTrip'
  return (
    <LegalPage title="Privacy policy">
      <Updated />
      <p>This policy explains what personal data {brand} (<Val v={site?.legal_name} name="BUSINESS_LEGAL_NAME" />) collects, why, and
        your rights under the Digital Personal Data Protection Act, 2023.</p>

      <h2>What we collect</h2>
      <ul>
        <li><b>Travellers:</b> name, mobile number, email, password (stored only as a secure hash), the names of people travelling with
          you, and your bookings, cancellations and reviews.</li>
        <li><b>Operators:</b> business and owner name, city, mobile number, email, PAN, bank account details, and, if you choose to add
          them, GSTIN, Udyam number and the last 4 digits of Aadhaar with a masked Aadhaar copy.</li>
        <li><b>Payments:</b> Razorpay processes payments. We receive only the payment status and reference, never your card or bank
          login details.</li>
        <li><b>Technical:</b> basic logs (IP address, browser, pages requested) to keep the site secure. Your login is kept in your
          browser's local storage. We don't use advertising trackers.</li>
      </ul>

      <h2>Why we use it</h2>
      <ul>
        <li>To make and manage your bookings, issue e-tickets, and process refunds.</li>
        <li>To verify operators and pay them for completed trips.</li>
        <li>To contact you about your booking or account, and to handle complaints.</li>
        <li>To prevent fraud and meet legal, tax and accounting duties.</li>
      </ul>

      <h2>Who we share it with</h2>
      <ul>
        <li>The <b>operator of the trip you book</b> gets the traveller names and the lead traveller's mobile number, for pickup and
          on-trip coordination.</li>
        <li><b>Razorpay</b>, to take payments, refund them and pay operators.</li>
        <li><b>Google (Gmail)</b>, which delivers our emails, including one-time codes.</li>
        <li>An <b>SMS provider</b> (MSG91), only to send one-time codes, when SMS codes are switched on.</li>
        <li><b>Government authorities</b>, when the law requires it.</li>
      </ul>
      <p>We never sell your personal data.</p>

      <h2>How we protect it</h2>
      <p>Operators' bank account numbers, PAN and Aadhaar copies are encrypted when stored, and only authorised {brand} staff can view
        them. Every view of an Aadhaar copy is logged. We never store a full Aadhaar number. The site uses HTTPS.</p>

      <h2>How long we keep it</h2>
      <p>We keep account data while your account is open. Booking and payment records are kept for as long as tax and accounting laws
        require (usually 8 years). Verification documents are kept while the operator is listed and for up to 3 years after, unless the
        law needs them longer.</p>

      <h2>Your rights</h2>
      <p>You can ask to see, correct or delete your personal data, or withdraw consent, by writing to our Grievance Officer. Some records
        (such as paid bookings) must be kept by law even after you close your account. If you're not satisfied with our reply, you can
        complain to the Data Protection Board of India.</p>
      <GrievanceBlock site={site} />
    </LegalPage>
  )
}

export function Refund() {
  const { cfg, site } = useSite()
  const brand = site?.brand || 'PakkaTrip'
  return (
    <LegalPage title="Cancellation & refund policy">
      <Updated />
      <h2>If you cancel</h2>
      <p>Cancel from <Link to="/my-bookings">My Bookings</Link> (open the booking, then Cancel). The refund depends on how many days
        before departure you cancel:</p>
      {cfg ? <PolicyTable policy={cfg.policy} /> : <p className="help">Loading the current policy…</p>}
      <ul>
        {cfg && <li>The convenience fee is {cfg.fee_rate}% of the package amount, minimum {inr(cfg.fee_min)}.</li>}
        <li>No refund for a no-show, or if you leave the trip partway through.</li>
        <li>Cancelling some seats and keeping others isn't possible online yet. <Link to="/contact">Contact us</Link> and we'll help.</li>
      </ul>

      <h2>If the operator cancels</h2>
      <p>If the operator cancels the trip for any reason, including weather, landslides or too few bookings, you get a <b>100% refund,
        including the convenience fee</b>. If they offer a different date instead, you can accept it or take the full refund.</p>

      <h2>When the money reaches you</h2>
      <p>Refunds go back to the original payment method (UPI, card or net banking) through Razorpay. We start the refund straight
        away; your bank usually credits it within <b>5–7 working days</b>.</p>

      <h2>Booking delivery</h2>
      <p>{brand} sells trip bookings, not physical goods, so nothing is shipped. Your e-ticket is issued as soon as payment succeeds. See
        the <Link to="/terms#delivery">Terms of use</Link>.</p>

      <h2>Questions or disputes</h2>
      <p>Write to us from the <Link to="/contact">Contact page</Link> with your booking code.</p>
    </LegalPage>
  )
}

export function Contact() {
  const { site } = useSite()
  const brand = site?.brand || 'PakkaTrip'
  return (
    <LegalPage title="Contact us">
      <p>Questions about a booking, a refund or listing your trips? Reach us here. Keep your booking code handy.</p>
      <dl className="legal-dl">
        <dt>Email</dt><dd>{site?.support_email ? <a href={`mailto:${site.support_email}`}>{site.support_email}</a> : <Val name="SUPPORT_EMAIL" />}</dd>
        <dt>Phone</dt><dd>{site?.support_phone ? <a href={telHref(site.support_phone)}>{site.support_phone}</a> : <Val name="SUPPORT_PHONE" />}</dd>
        <dt>Hours</dt><dd>{site?.support_hours}</dd>
        <dt>Business</dt><dd><Val v={site?.legal_name} name="BUSINESS_LEGAL_NAME" />{site?.legal_name && site.legal_name !== brand && ` (operating ${brand})`}</dd>
        <dt>Address</dt><dd><Val v={site?.address} name="BUSINESS_ADDRESS" /></dd>
        {site?.gstin && <><dt>GSTIN</dt><dd>{site.gstin}</dd></>}
      </dl>

      <h2>Tour operators</h2>
      <p>Want to list your trips? <a href="/partner/signup">Apply on the Partner portal</a>. It's free to list.</p>

      <h2>Grievance Officer</h2>
      <p>As required by the Consumer Protection (E-Commerce) Rules, 2020 and the IT Rules, 2021. Complaints are acknowledged within 48
        hours and resolved within one month.</p>
      <GrievanceBlock site={site} />
    </LegalPage>
  )
}
