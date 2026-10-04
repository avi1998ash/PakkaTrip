"""Operator bank details and settlements.

Operator:  /api/operator/bank-account/ (GET, PUT — owner only), /api/operator/ifsc/<code>/
Admin:     /api/admin/payouts/ (GET overview, POST pay an operator), /api/admin/payouts/<id>/refresh/,
           /api/admin/bank-accounts/<operator_id>/verify|reject/
Bank account numbers and PAN never leave the server in full — only the last 4 characters.
"""
import re
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils.timezone import localtime
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from operators.models import Operator, OperatorBankAccount, OperatorMember
from payments import razorpay
from payments.models import Payout
from payments.payouts import (PayoutError, create_operator_payout, due_bookings, payout_mode, reject_bank_account,
                              save_bank_account, sync_payout, upcoming_amount, verify_bank_account)

from .admin_views import err
from .permissions import IsAdminRole, IsOperatorRole

IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def bank_out(acct):
    if not acct:
        return None
    return {
        "holder_name": acct.holder_name, "account": acct.masked_account, "last4": acct.account_last4, "ifsc": acct.ifsc,
        "bank_name": acct.bank_name, "branch": acct.branch, "account_type": acct.account_type, "pan": f"XXXXXX{acct.pan_last4}",
        "business_type": acct.business_type, "address_line": acct.address_line, "address_city": acct.address_city,
        "address_state": acct.address_state, "pincode": acct.pincode, "status": acct.status, "rejection_reason": acct.rejection_reason,
        "verified_at": localtime(acct.verified_at) if acct.verified_at else None, "updated_at": localtime(acct.updated_at),
        "payouts_ready": bool(acct.razorpayx_fund_account_id), "route_ready": bool(acct.route_account_id),
    }


def payout_out(p):
    return {"id": p.id, "operator": p.operator.business_name, "amount": p.amount, "account": f"XXXX {p.account_last4}",
            "status": p.status, "utr": p.utr, "mode": p.mode, "failure_reason": p.failure_reason, "bookings": p.bookings.count(),
            "created_at": localtime(p.created_at), "processed_at": localtime(p.processed_at) if p.processed_at else None}


def settlement_summary(operator):
    """Money position for one operator: due now, after upcoming trips, paid out so far."""
    items = due_bookings(operator)
    paid = Payout.objects.filter(operator=operator, status=Payout.Status.PROCESSED).aggregate(s=Sum("amount"))["s"] or 0
    in_flight = Payout.objects.filter(operator=operator).exclude(status__in=[*Payout.FINAL_FAILED, Payout.Status.PROCESSED]) \
        .aggregate(s=Sum("amount"))["s"] or 0
    return {"due": sum((s for _, s in items), Decimal(0)), "due_count": len(items), "upcoming": upcoming_amount(operator),
            "paid": paid, "in_flight": in_flight}


# ---------------------------------------------------------------- operator

class BankAccountIn(serializers.Serializer):
    holder_name = serializers.RegexField(r"^[A-Za-z][A-Za-z .&'-]{1,99}$", error_messages={"invalid": "Use the name exactly as on the bank account."})
    account_number = serializers.RegexField(r"^\d{9,18}$", error_messages={"invalid": "Account number is 9 to 18 digits."})
    confirm_account_number = serializers.CharField()
    ifsc = serializers.CharField(max_length=11)
    account_type = serializers.ChoiceField(choices=OperatorBankAccount.AccountType.choices)
    pan = serializers.CharField(max_length=10)
    business_type = serializers.ChoiceField(choices=OperatorBankAccount.BusinessType.choices)
    address_line = serializers.CharField(max_length=200)
    address_city = serializers.CharField(max_length=60)
    address_state = serializers.CharField(max_length=60)
    pincode = serializers.RegexField(r"^[1-9]\d{5}$", error_messages={"invalid": "Enter a 6-digit PIN code."})

    def validate_ifsc(self, v):
        v = v.strip().upper()
        if not IFSC_RE.match(v):
            raise serializers.ValidationError("IFSC is 11 characters, like HDFC0001234.")
        return v

    def validate_pan(self, v):
        v = v.strip().upper()
        if not re.match(r"^[A-Z]{5}\d{4}[A-Z]$", v):
            raise serializers.ValidationError("PAN is 10 characters, like ABCDE1234F.")
        return v

    def validate(self, d):
        if d["account_number"] != d["confirm_account_number"]:
            raise serializers.ValidationError({"confirm_account_number": "Account numbers don't match."})
        return d


@api_view(["GET", "PUT"])
@permission_classes([IsOperatorRole])
def bank_account(request):
    op = request.operator
    if request.method == "PUT":
        if request.user.operator_membership.member_role != OperatorMember.Role.OWNER:
            return err("Only the business owner can change bank details.", 403)
        ser = BankAccountIn(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            save_bank_account(op, ser.validated_data, request.user)
        except PayoutError as e:
            return err(str(e))
    acct = OperatorBankAccount.objects.filter(operator=op).first()
    return Response({"bank": bank_out(acct), "can_edit": request.user.operator_membership.member_role == OperatorMember.Role.OWNER,
                     "mode": payout_mode(), **settlement_summary(op),
                     "payouts": [payout_out(p) for p in Payout.objects.filter(operator=op).select_related("operator")[:20]]})


@api_view(["GET"])
@permission_classes([IsOperatorRole])
def ifsc(request, code):
    code = code.strip().upper()
    if not IFSC_RE.match(code):
        return err("IFSC is 11 characters, like HDFC0001234.")
    try:
        bank = razorpay.ifsc_lookup(code)
    except razorpay.GatewayError as e:
        return err(str(e), 502)
    return Response(bank) if bank else err("That IFSC code doesn't exist.", 404)


# ---------------------------------------------------------------- admin

@api_view(["GET", "POST"])
@permission_classes([IsAdminRole])
def payouts(request):
    if request.method == "POST":
        op = get_object_or_404(Operator, pk=request.data.get("operator_id"))
        try:
            p = create_operator_payout(op, request.user)
        except PayoutError as e:
            return err(str(e))
        return Response(payout_out(p), status=201)
    ops = Operator.objects.select_related("bank_account").order_by("business_name")
    rows = []
    for op in ops:
        acct = getattr(op, "bank_account", None)   # reverse one-to-one: None when not added yet
        rows.append({"id": op.id, "name": op.business_name, "verified": op.is_verified, "bank": bank_out(acct), **settlement_summary(op)})
    return Response({
        "mode": payout_mode(), "razorpayx_ready": bool(settings.RAZORPAYX_ACCOUNT_NUMBER), "test_mode": settings.RAZORPAY_KEY_ID.startswith("rzp_test_"),
        "operators": rows,
        "history": [payout_out(p) for p in Payout.objects.select_related("operator")[:50]],
    })


@api_view(["POST"])
@permission_classes([IsAdminRole])
def payout_refresh(request, pk):
    p = get_object_or_404(Payout, pk=pk)
    try:
        p = sync_payout(p)
    except PayoutError as e:
        return err(str(e))
    return Response(payout_out(p))


@api_view(["POST"])
@permission_classes([IsAdminRole])
def bank_account_action(request, operator_id, action):
    acct = get_object_or_404(OperatorBankAccount.objects.select_related("operator"), operator_id=operator_id)
    try:
        if action == "verify":
            verify_bank_account(acct, request.user)
        elif action == "reject":
            reason = str(request.data.get("reason", "")).strip()
            if len(reason) < 5:
                return err("Tell the operator what's wrong so they can fix it.")
            reject_bank_account(acct, reason, request.user)
        else:
            return err("Unknown action.", 404)
    except PayoutError as e:
        return err(str(e))
    return Response(bank_out(acct))
