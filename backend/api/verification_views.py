"""Operator self-signup and verification tiers.

Public:    /api/public/partner/otp/, /api/public/partner/signup/
Operator:  /api/operator/verification/ (GET), …/phone/otp/, …/phone/verify/, …/documents/<kind>/ (PUT, owner only),
           …/resubmit/ (rejected application → back to review)
Admin:     /api/admin/applications/, /api/admin/operators/<id>/verification/, …/reject/,
           …/documents/<kind>/<verify|reject>/, …/documents/<kind>/file/
"""
import re

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from catalog.models import City, unique_slug
from core import sms
from core.models import audit
from operators.models import Operator, OperatorDocument, OperatorMember, PhoneOtp
from operators.verification import (VerificationError, check_otp, mark_phone_verified, read_document_file, review_document, send_otp,
                                    submit_document, verification_out)

from .admin_views import err
from .auth_views import user_payload
from .permissions import IsAdminRole, IsOperatorRole
from .public_views import PUBLIC, SensitiveThrottle
from .serializers import ADMIN_EMAIL, validate_phone

Purpose = PhoneOtp.Purpose
SMS_OFF = "SMS codes are switched off for now. PakkaTrip will call you to confirm your mobile number."


def _otp_response(code):
    return Response({"sent": True, **({"dev_code": code} if code else {})})


# ---------------------------------------------------------------- public signup

def phone_taken(phone):
    return User.objects.filter(phone=phone).exists() or Operator.objects.filter(contact_phone=phone).exists()


@api_view(["POST"])
@permission_classes(PUBLIC)
@throttle_classes([SensitiveThrottle])
def signup_otp(request):
    if not sms.otp_on():
        return err(SMS_OFF)
    phone = str(request.data.get("phone", "")).strip()
    try:
        validate_phone(phone)
    except serializers.ValidationError:
        return err("Enter a 10-digit Indian mobile number.")
    if phone_taken(phone):
        return err("This mobile number is already registered. Sign in on the Partner portal instead.")
    try:
        return _otp_response(send_otp(phone, Purpose.PARTNER_SIGNUP))
    except VerificationError as e:
        return err(str(e))


class PartnerSignupIn(serializers.Serializer):
    business_name = serializers.CharField(min_length=3, max_length=120)
    owner_name = serializers.RegexField(r"^[A-Za-z][A-Za-z .'-]{1,99}$", error_messages={"invalid": "Enter the owner's full name."})
    city = serializers.RegexField(r"^[A-Za-z][A-Za-z .'-]{1,59}$", error_messages={"invalid": "Enter the city your business is based in."})
    phone = serializers.CharField(validators=[validate_phone])
    otp = serializers.RegexField(r"^\d{6}$", required=False, error_messages={"invalid": "Enter the 6-digit code we sent by SMS."})
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, max_length=64)

    def validate_email(self, v):
        v = v.strip().lower()
        if v == ADMIN_EMAIL or User.objects.filter(email=v).exists():
            raise serializers.ValidationError("An account with this email already exists. Sign in instead.")
        return v

    def validate_phone(self, v):
        if phone_taken(v):
            raise serializers.ValidationError("This mobile number is already registered.")
        return v


@api_view(["POST"])
@permission_classes(PUBLIC)
@throttle_classes([SensitiveThrottle])
def signup(request):
    """A tour operator applies. They can sign in and set up packages straight away; nothing is shown to
    travellers until an admin approves them (which needs at least Bronze).
    With SMS codes switched off, the number is saved unverified and an admin confirms it by calling."""
    ser = PartnerSignupIn(data=request.data)
    ser.is_valid(raise_exception=True)
    d = ser.validated_data
    otp_on = sms.otp_on()
    if otp_on:
        try:
            check_otp(d["phone"], Purpose.PARTNER_SIGNUP, d.get("otp"))
        except VerificationError as e:
            return Response({"otp": [str(e)]}, status=400)
    name, owner = " ".join(d["business_name"].split()), " ".join(d["owner_name"].split())
    with transaction.atomic():
        user = User.objects.create_user(d["email"], d["password"], full_name=owner, phone=d["phone"], role=User.Role.OPERATOR,
                                        phone_verified_at=timezone.now() if otp_on else None)
        op = Operator.objects.create(
            business_name=name, slug=unique_slug(Operator, name), owner_name=owner, contact_phone=d["phone"], contact_email=d["email"],
            city=City.by_name(d["city"]), status=Operator.Status.PENDING, source=Operator.Source.SIGNUP)
        OperatorMember.objects.create(operator=op, user=user, member_role=OperatorMember.Role.OWNER)
        if otp_on:
            mark_phone_verified(op, user)
        audit(user, "operator.applied", op)
    refresh = RefreshToken.for_user(user)
    return Response({"access": str(refresh.access_token), "refresh": str(refresh), "user": user_payload(user)}, status=201)


# ---------------------------------------------------------------- operator

def _is_owner(request):
    return request.user.operator_membership.member_role == OperatorMember.Role.OWNER


@api_view(["GET"])
@permission_classes([IsOperatorRole])
def my_verification(request):
    return Response({**verification_out(request.operator), "can_edit": _is_owner(request)})


@api_view(["POST"])
@permission_classes([IsOperatorRole])
@throttle_classes([SensitiveThrottle])
def phone_otp(request):
    op = request.operator
    if op.phone_verified_at:
        return err("Your mobile number is already verified.")
    if not sms.otp_on():
        return err(SMS_OFF)
    try:
        return _otp_response(send_otp(op.contact_phone, Purpose.OPERATOR_PHONE))
    except VerificationError as e:
        return err(str(e))


@api_view(["POST"])
@permission_classes([IsOperatorRole])
@throttle_classes([SensitiveThrottle])
def phone_verify(request):
    op = request.operator
    if not sms.otp_on():
        return err(SMS_OFF)
    try:
        check_otp(op.contact_phone, Purpose.OPERATOR_PHONE, request.data.get("code"))
    except VerificationError as e:
        return err(str(e))
    mark_phone_verified(op, request.user)
    return Response({**verification_out(op), "can_edit": _is_owner(request)})


@api_view(["PUT"])
@permission_classes([IsOperatorRole])
def document(request, kind):
    if kind not in OperatorDocument.Kind.values:
        return err("Unknown document.", 404)
    if not _is_owner(request):
        return err("Only the business owner can submit verification documents.", 403)
    try:
        submit_document(request.operator, kind, request.data.get("number"), request.FILES.get("file"), request.user)
    except VerificationError as e:
        return err(str(e))
    return Response({**verification_out(request.operator), "can_edit": True})


@api_view(["POST"])
@permission_classes([IsOperatorRole])
def resubmit(request):
    op = request.operator
    if op.status != Operator.Status.REJECTED:
        return err("Your application isn't rejected.")
    if not _is_owner(request):
        return err("Only the business owner can resubmit the application.", 403)
    op.status = Operator.Status.PENDING
    op.save(update_fields=["status", "updated_at"])
    audit(request.user, "operator.resubmitted", op)
    return Response({**verification_out(op), "can_edit": True})


# ---------------------------------------------------------------- admin

@api_view(["GET"])
@permission_classes([IsAdminRole])
def applications(request):
    """Operators waiting for review, oldest first so nobody waits too long, then rejected ones."""
    qs = Operator.objects.filter(status__in=[Operator.Status.PENDING, Operator.Status.REJECTED]).select_related("city").order_by("created_at", "id")
    return Response([verification_out(op, for_admin=True) for op in qs])


@api_view(["GET"])
@permission_classes([IsAdminRole])
def operator_verification(request, pk):
    return Response(verification_out(get_object_or_404(Operator.objects.select_related("city"), pk=pk), for_admin=True))


@api_view(["POST"])
@permission_classes([IsAdminRole])
def reject_application(request, pk):
    op = get_object_or_404(Operator.objects.select_related("city"), pk=pk)
    if op.status != Operator.Status.PENDING:
        return err("Only applications waiting for review can be rejected.")
    reason = re.sub(r"\s+", " ", str(request.data.get("reason", ""))).strip()
    if len(reason) < 5:
        return err("Tell the operator why, so they can fix it and resubmit.")
    op.status, op.rejection_reason = Operator.Status.REJECTED, reason[:200]
    op.save(update_fields=["status", "rejection_reason", "updated_at"])
    audit(request.user, "operator.rejected", op, reason=reason)
    return Response(verification_out(op, for_admin=True))


@api_view(["POST"])
@permission_classes([IsAdminRole])
def phone_confirm(request, pk):
    """The admin called the operator's number and confirmed it (used while SMS codes are off)."""
    op = get_object_or_404(Operator.objects.select_related("city"), pk=pk)
    if op.phone_verified_at:
        return err("This mobile number is already verified.")
    mark_phone_verified(op, request.user)
    audit(request.user, "operator.phone_confirmed_by_call", op, phone=op.contact_phone)
    return Response(verification_out(op, for_admin=True))


@api_view(["POST"])
@permission_classes([IsAdminRole])
def document_action(request, pk, kind, action):
    if action not in ("verify", "reject"):
        return err("Unknown action.", 404)
    doc = get_object_or_404(OperatorDocument.objects.select_related("operator__city"), operator_id=pk, kind=kind)
    try:
        review_document(doc, action == "verify", request.user, str(request.data.get("reason", "")))
    except VerificationError as e:
        return err(str(e))
    return Response(verification_out(doc.operator, for_admin=True))


@api_view(["GET"])
@permission_classes([IsAdminRole])
def document_file(request, pk, kind):
    """The decrypted masked copy, for the admin reviewing it. Every view is written to the audit log."""
    doc = get_object_or_404(OperatorDocument, operator_id=pk, kind=kind)
    if not doc.file:
        return err("No file was uploaded.", 404)
    audit(request.user, "document.viewed", doc, kind=kind)
    resp = HttpResponse(read_document_file(doc), content_type=doc.file_type or "application/octet-stream")
    resp["Cache-Control"] = "no-store"
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Content-Disposition"] = "inline"
    return resp
