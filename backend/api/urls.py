from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import admin_views as a
from . import auth_views as auth
from . import operator_views as o
from . import payout_views as pay
from . import public_views as pub
from . import webhooks as hooks

urlpatterns = [
    # auth
    path("auth/login/", auth.LoginView.as_view()),
    path("auth/refresh/", TokenRefreshView.as_view()),
    path("auth/me/", auth.MeView.as_view()),

    # admin
    path("admin/dashboard/", a.dashboard),
    path("admin/nav-counts/", a.nav_counts),
    path("admin/operators/", a.operators),
    path("admin/operators/<int:pk>/", a.operator_detail),
    path("admin/operators/<int:pk>/verify/", a.operator_verify),
    path("admin/packages/", a.packages),
    path("admin/packages/<int:pk>/", a.package_detail),
    path("admin/packages/<int:pk>/<str:action>/", a.package_action),
    path("admin/bookings/", a.bookings),
    path("admin/bookings/<str:code>/", a.booking_detail),
    path("admin/bookings/<str:code>/cancel/", a.booking_cancel),
    path("admin/settings/", a.platform_settings),
    path("admin/reset-demo/", a.reset_demo),
    path("admin/payouts/", pay.payouts),
    path("admin/payouts/<int:pk>/refresh/", pay.payout_refresh),
    path("admin/bank-accounts/<int:operator_id>/<str:action>/", pay.bank_account_action),

    # operator
    path("operator/dashboard/", o.dashboard),
    path("operator/nav-counts/", o.nav_counts),
    path("operator/packages/", o.packages),
    path("operator/packages/<int:pk>/", o.package_detail),
    path("operator/facility-options/", o.facility_options),
    path("operator/departures/", o.departures),
    path("operator/departures/<int:pk>/", o.departure_detail),
    path("operator/departures/<int:pk>/bookings/", o.departure_booking),
    path("operator/departures/<int:pk>/<str:action>/", o.departure_block),
    path("operator/bookings/", o.bookings),
    path("operator/bookings/<str:code>/", o.booking_detail),
    path("operator/bookings/<str:code>/<str:action>/", o.booking_action),
    path("operator/earnings/", o.earnings),
    path("operator/reviews/", o.reviews),
    path("operator/reviews/<int:pk>/reply/", o.review_reply),
    path("operator/bank-account/", pay.bank_account),
    path("operator/ifsc/<str:code>/", pay.ifsc),

    # public (traveller site)
    path("public/auth/signup/", pub.signup),
    path("public/auth/login/", pub.login),
    path("public/home/", pub.home),
    path("public/config/", pub.config),
    path("public/packages/", pub.search),
    path("public/packages/<int:pk>/", pub.package_detail),
    path("public/quote/", pub.quote),
    path("public/bookings/", pub.create_booking),
    path("public/bookings/find/", pub.booking_find),
    path("public/bookings/lookup/", pub.bookings_lookup),
    path("public/bookings/<str:code>/", pub.booking_detail),
    path("public/bookings/<str:code>/cancel/", pub.booking_cancel),
    path("public/bookings/<str:code>/review/", pub.booking_review),
    path("public/bookings/<str:code>/pay/verify/", pub.payment_verify),
    path("public/bookings/<str:code>/pay/abandon/", pub.payment_abandon),

    # payment gateway (server-to-server)
    path("payments/razorpay/webhook/", hooks.razorpay_webhook),
]
