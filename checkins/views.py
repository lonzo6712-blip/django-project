from datetime import timedelta
from io import BytesIO

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe

from .forms import CheckInForm, DispatchUpdateForm, DriverSelfCheckInForm, SMSMessageForm
from .models import CheckIn, Facility, OutboundSMS, SMSMessage


def _ensure_staff(request):
    if not request.user.is_staff:
        raise PermissionDenied


def _worker_ok() -> bool:
    heartbeat = cache.get("sms-worker:heartbeat")
    if not heartbeat:
        return False
    try:
        heartbeat_at = timezone.datetime.fromisoformat(heartbeat)
    except ValueError:
        return False
    if timezone.is_naive(heartbeat_at):
        heartbeat_at = timezone.make_aware(heartbeat_at, timezone.get_current_timezone())
    max_age = getattr(settings, "SMS_WORKER_HEARTBEAT_TTL", 60)
    return heartbeat_at >= timezone.now() - timedelta(seconds=max_age)


def _driver_rate_limit_key(request, facility_id: int) -> str:
    return f"driver-checkin:{facility_id}:{request.META.get('REMOTE_ADDR', 'unknown')}"


def _sms_rate_limit_key(checkin_id: int) -> str:
    return f"checkin-sms:{checkin_id}"


@login_required
def dashboard(request):
    _ensure_staff(request)

    active_facilities = Facility.objects.filter(is_active=True).order_by("name")
    checkins = CheckIn.objects.select_related("facility", "carrier")
    waiting_checkins = list(checkins.filter(status=CheckIn.Status.WAITING))
    in_progress_checkins = list(
        checkins.filter(status__in=[CheckIn.Status.ON_DOCK, CheckIn.Status.UNLOADING])
    )
    completed_checkins = list(checkins.filter(status=CheckIn.Status.COMPLETED))
    status_counts = dict(checkins.values("status").annotate(total=Count("id")).values_list("status", "total"))

    context = {
        "active_facilities": active_facilities,
        "waiting_checkins": waiting_checkins,
        "in_progress_checkins": in_progress_checkins,
        "completed_checkins": completed_checkins,
        "status_counts": status_counts,
        "active_count": len(waiting_checkins) + len(in_progress_checkins),
        "completed_today": checkins.filter(
            status=CheckIn.Status.COMPLETED,
            arrival_time__date=timezone.localdate(),
        ).count(),
    }
    return render(request, "checkins/dashboard.html", context)


@login_required
def qr_scan(request):
    _ensure_staff(request)
    return render(request, "checkins/scan.html")


@login_required
def qr_lookup(request):
    _ensure_staff(request)

    code = request.GET.get("code", "").strip()
    if not code:
        return redirect("qr_scan")

    existing = CheckIn.objects.filter(load_reference=code).first()
    if existing:
        return redirect("checkin_detail", pk=existing.pk)
    return redirect(f"{reverse('checkin_create')}?load_reference={code}")


@login_required
def checkin_create(request):
    _ensure_staff(request)

    initial = {}
    load_reference = request.GET.get("load_reference", "").strip()
    if request.method != "POST" and load_reference:
        initial["load_reference"] = load_reference

    if request.method == "POST":
        form = CheckInForm(request.POST)
        if form.is_valid():
            checkin = form.save()
            messages.success(request, "Check-in entry created.")
            return redirect("checkin_detail", pk=checkin.pk)
    else:
        form = CheckInForm(initial=initial)

    return render(request, "checkins/checkin_form.html", {"form": form})


def driver_checkin(request, facility_slug: str):
    facility = get_object_or_404(Facility, slug=facility_slug, is_active=True)

    if request.method == "POST":
        rate_limit_key = _driver_rate_limit_key(request, facility.pk)
        if cache.get(rate_limit_key):
            messages.error(request, "Please wait before submitting another MonetteFarms driver check-in.")
            form = DriverSelfCheckInForm(request.POST)
        else:
            form = DriverSelfCheckInForm(request.POST)
            if form.is_valid():
                form.instance.facility = facility
                checkin = form.save()
                cache.set(rate_limit_key, True, timeout=settings.DRIVER_CHECKIN_RATE_LIMIT_SECONDS)
                return redirect("driver_checkin_submitted", pk=checkin.pk)
    else:
        form = DriverSelfCheckInForm()

    return render(request, "checkins/driver_checkin_form.html", {"form": form, "facility": facility})


def driver_checkin_submitted(request, pk: int):
    checkin = get_object_or_404(CheckIn.objects.select_related("facility"), pk=pk)
    return render(request, "checkins/driver_checkin_submitted.html", {"checkin": checkin})


@login_required
def facility_driver_qr(request, facility_slug: str):
    _ensure_staff(request)

    facility = get_object_or_404(Facility, slug=facility_slug, is_active=True)
    driver_checkin_url = request.build_absolute_uri(reverse("driver_checkin", args=[facility.slug]))

    qr = qrcode.QRCode(border=1)
    qr.add_data(driver_checkin_url)
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgImage)
    buffer = BytesIO()
    image.save(buffer)
    qr_svg = buffer.getvalue().decode("utf-8")

    context = {
        "facility": facility,
        "driver_checkin_url": driver_checkin_url,
        "driver_checkin_qr_svg": mark_safe(qr_svg),
    }
    return render(request, "checkins/facility_driver_qr.html", context)


def legacy_driver_checkin(request, facility_pk: int):
    facility = get_object_or_404(Facility, pk=facility_pk, is_active=True)
    return redirect("driver_checkin", facility_slug=facility.slug, permanent=True)


@login_required
def legacy_facility_driver_qr(request, facility_pk: int):
    _ensure_staff(request)

    facility = get_object_or_404(Facility, pk=facility_pk, is_active=True)
    return redirect("facility_driver_qr", facility_slug=facility.slug, permanent=True)


@login_required
def checkin_detail(request, pk: int):
    _ensure_staff(request)

    checkin = get_object_or_404(CheckIn.objects.select_related("facility", "carrier"), pk=pk)
    context = {
        "checkin": checkin,
        "dispatch_form": DispatchUpdateForm(instance=checkin),
        "sms_form": SMSMessageForm(),
        "sms_history": checkin.sms_messages.all(),
    }
    return render(request, "checkins/checkin_detail.html", context)


@login_required
def checkin_update(request, pk: int):
    _ensure_staff(request)

    checkin = get_object_or_404(CheckIn, pk=pk)
    if request.method != "POST":
        return redirect("checkin_detail", pk=checkin.pk)

    if request.POST.get("action") == "complete":
        checkin.status = CheckIn.Status.COMPLETED
        checkin.save(update_fields=["status"])
        messages.success(request, "Truck checkout completed.")
        return redirect("dashboard")

    form = DispatchUpdateForm(request.POST, instance=checkin)
    if form.is_valid():
        updated = form.save()
        status_label = updated.get_status_display()
        dock_text = updated.dock_number if updated.dock_number is not None else "unassigned"
        initials_text = updated.warehouse_staff_initials or "not provided"
        messages.success(
            request,
            f"Dispatch updated: status set to {status_label}, dock {dock_text}, staff initials {initials_text}.",
        )
    return redirect("checkin_detail", pk=checkin.pk)


@login_required
def checkin_send_sms(request, pk: int):
    _ensure_staff(request)

    checkin = get_object_or_404(CheckIn, pk=pk)
    if request.method != "POST":
        return redirect("checkin_detail", pk=checkin.pk)

    if not checkin.phone_number:
        messages.error(request, "This driver does not have a phone number on file.")
        return redirect("checkin_detail", pk=checkin.pk)

    rate_limit_key = _sms_rate_limit_key(checkin.pk)
    if cache.get(rate_limit_key):
        messages.error(request, "Please wait before sending another text for this load.")
        return redirect("checkin_detail", pk=checkin.pk)

    form = SMSMessageForm(request.POST)
    if form.is_valid():
        sms = SMSMessage.objects.create(
            checkin=checkin,
            to_number=checkin.phone_number,
            from_number="",
            body=form.cleaned_data["body"],
            delivery_status=SMSMessage.DeliveryStatus.QUEUED,
        )
        OutboundSMS.objects.create(
            checkin=checkin,
            sms_message=sms,
            to_number=checkin.phone_number,
            body=sms.body,
        )
        cache.set(rate_limit_key, True, timeout=settings.SMS_RATE_LIMIT_SECONDS)
        messages.success(request, "Text message queued for delivery to the driver.")

    return redirect("checkin_detail", pk=checkin.pk)


def healthz(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    cache.set("healthz:ping", "ok", timeout=5)

    worker_ok = _worker_ok()
    payload = {
        "status": "ok",
        "database": "ok",
        "cache": "ok",
        "sms_worker": "ok" if worker_ok else "error",
    }
    return JsonResponse(payload, status=200)


def worker_healthz(request):
    worker_ok = _worker_ok()
    payload = {"status": "ok" if worker_ok else "error", "sms_worker": "ok" if worker_ok else "error"}
    return JsonResponse(payload, status=200 if worker_ok else 503)
