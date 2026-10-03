from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from operators.models import Operator


class LoginThrottle(AnonRateThrottle):
    rate = "20/min"


def user_payload(user):
    data = {"id": user.id, "email": user.email, "name": user.full_name, "phone": user.phone, "role": user.role, "operator": None}
    if user.role == User.Role.OPERATOR:
        op = user.operator_membership.operator
        data["operator"] = {"id": op.id, "name": op.business_name, "owner": op.owner_name, "verified": op.is_verified, "status": op.status}
    return data


class LoginView(APIView):
    """One login for admin and operators — the account's role decides where they land."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginThrottle]

    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        password = str(request.data.get("password", ""))
        user = authenticate(request, email=email, password=password)
        portal_user = user and (user.role == User.Role.ADMIN or
                                (user.role == User.Role.OPERATOR and hasattr(user, "operator_membership")))
        if not portal_user:
            return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        if user.role == User.Role.OPERATOR and user.operator_membership.operator.status == Operator.Status.SUSPENDED:
            return Response({"detail": "This operator account is suspended. Contact PakkaTrip support."}, status=status.HTTP_403_FORBIDDEN)
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        refresh = RefreshToken.for_user(user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh), "user": user_payload(user)})


class MeView(APIView):
    """Current account — admin, operator or traveller (the React app uses one session for all)."""
    def get(self, request):
        return Response(user_payload(request.user))
