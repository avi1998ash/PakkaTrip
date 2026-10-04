import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { FeedbackProvider } from './components/feedback'
import Shell, { RequireRole } from './components/Shell'
import './index.css'
import { AuthProvider } from './lib/auth'
import AdminBookings from './pages/admin/Bookings'
import AdminDashboard from './pages/admin/Dashboard'
import AdminOperators from './pages/admin/Operators'
import AdminPackages from './pages/admin/Packages'
import AdminPayouts from './pages/admin/Payouts'
import AdminSettings from './pages/admin/Settings'
import Login from './pages/Login'
import OpBank from './pages/operator/Bank'
import OpBookings from './pages/operator/Bookings'
import OpDashboard from './pages/operator/Dashboard'
import OpEarnings from './pages/operator/Earnings'
import Inventory from './pages/operator/Inventory'
import PackageEditor from './pages/operator/PackageEditor'
import OpPackages from './pages/operator/Packages'
import OpReviews from './pages/operator/Reviews'
import Account from './public/Account'
import Book from './public/Book'
import Home from './public/Home'
import MyBookings from './public/MyBookings'
import PublicLayout from './public/PublicLayout'
import Search from './public/Search'
import Ticket from './public/Ticket'
import Trip from './public/Trip'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <FeedbackProvider>
          <Routes>
            {/* Traveller site */}
            <Route element={<PublicLayout />}>
              <Route index element={<Home />} />
              <Route path="search" element={<Search />} />
              <Route path="trips/:id" element={<Trip />} />
              <Route path="book/:id" element={<Book />} />
              <Route path="ticket/:code" element={<Ticket />} />
              <Route path="my-bookings" element={<MyBookings />} />
              <Route path="account" element={<Account />} />
            </Route>

            {/* Partner portal (admin + operators) */}
            <Route path="/partner/login" element={<Login />} />
            <Route path="/login" element={<Navigate to="/partner/login" replace />} />
            <Route path="/admin" element={<RequireRole role="admin"><Shell /></RequireRole>}>
              <Route index element={<Navigate to="dashboard" replace />} />
              <Route path="dashboard" element={<AdminDashboard />} />
              <Route path="operators" element={<AdminOperators />} />
              <Route path="packages" element={<AdminPackages />} />
              <Route path="bookings" element={<AdminBookings />} />
              <Route path="payouts" element={<AdminPayouts />} />
              <Route path="settings" element={<AdminSettings />} />
            </Route>
            <Route path="/operator" element={<RequireRole role="operator"><Shell /></RequireRole>}>
              <Route index element={<Navigate to="dashboard" replace />} />
              <Route path="dashboard" element={<OpDashboard />} />
              <Route path="packages" element={<OpPackages />} />
              <Route path="packages/new" element={<PackageEditor />} />
              <Route path="packages/:id/edit" element={<PackageEditor />} />
              <Route path="inventory" element={<Inventory />} />
              <Route path="bookings" element={<OpBookings />} />
              <Route path="earnings" element={<OpEarnings />} />
              <Route path="bank" element={<OpBank />} />
              <Route path="reviews" element={<OpReviews />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </FeedbackProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
