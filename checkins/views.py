from io import BytesIO
from urllib.parse import quote

import qrcode
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.conf import settings
from django.core.cache import cache
from django.db import connections, transaction
from django.db.models import Count
from django.db.utils import DatabaseError
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView
from qrcode.image.svg import SvgPathImage

from .forms import CheckInForm, DispatchUpdateForm, DriverSelfCheckInForm, SMSMessageForm
from .models import CheckIn, Facility, OutboundSMS, SMSMessage


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        return self.request.user.is_staff

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        return super().handle_no_permission()


class DashboardView(StaffRequiredMixin, ListView):
    model = CheckIn
    template_name = "checkins/dashboard.html"
    context_object_name = "checkins"

    def get_queryset(self):
        return (
            CheckIn.objects.select_related("carrier", "facility")
            .order_by("-arrival_time")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_checkins = list(context["checkins"])
        context["status_counts"] = dict(
            CheckIn.objects.values_list("status").annotate(total=Count("id"))
        )
        context["active_count"] = CheckIn.objects.exclude(
            status__in=[CheckIn.Status.COMPLETED, CheckIn.Status.CANCELLED]
        ).count()
        context["completed_today"] = CheckIn.objects.filter(
            status=CheckIn.Status.COMPLETED,
            arrival_time__date=timezone.localdate(),
        ).count()
        context["active_facilities"] = Facility.objects.filter(is_active=True).order_by("name")
        context["waiting_checkins"] = [
            checkin for checkin in all_checkins if checkin.status == CheckIn.Status.WAITING
        ]
        context["in_progress_checkins"] = [
            checkin
            for checkin in all_checkins
            if checkin.status in {CheckIn.Status.ON_DOCK, CheckIn.Status.UNLOADING}
        ]
        context["completed_checkins"] = [
            checkin for checkin in all_checkins if checkin.status == CheckIn.Status.COMPLETED
        ]
        return context


class CheckInCreateView(StaffRequiredMixin, CreateView):
    model = CheckIn
    form_class = CheckInForm
    template_name = "checkins/checkin_form.html"

    def get_initial(self):
        initial = super().get_initial()
        scanned_code = self.request.GET.get("load_reference", "").strip()
        if scanned_code:
            initial["load_reference"] = scanned_code
        return initial


class DriverCheckInView(CreateView):
    model = CheckIn
    form_class = DriverSelfCheckInForm
    template_name = "checkins/driver_checkin_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.facility = get_object_or_404(Facility, pk=kwargs["facility_id"], is_active=True)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        scanned_code = self.request.GET.get("load_reference", "").strip()
        if scanned_code:
            initial["load_reference"] = scanned_code
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.instance.facility = self.facility
        return form

    def form_valid(self, form):
        if self.is_rate_limited():
            messages.error(
                self.request,
                "Please wait before submitting another MonetteFarms driver check-in.",
            )
            return self.form_invalid(form)
        form.instance.facility = self.facility
        response = super().form_valid(form)
        messages.success(
            self.request,
            "Check-in submitted. Please wait for receiving instructions.",
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["facility"] = self.facility
        return context

    def get_success_url(self):
        return reverse("driver_checkin_submitted", args=[self.object.pk])

    def is_rate_limited(self) -> bool:
        remote_addr = self.request.META.get("REMOTE_ADDR", "unknown")
        cache_key = f"driver-checkin-rate-limit:{self.facility.pk}:{remote_addr}"
        cooldown_seconds = max(1, int(getattr(settings, "DRIVER_CHECKIN_RATE_LIMIT_SECONDS", 60)))
        return not cache.add(cache_key, True, timeout=cooldown_seconds)


class DriverCheckInSubmittedView(TemplateView):
    template_name = "checkins/driver_checkin_submitted.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        checkin = get_object_or_404(CheckIn.objects.select_related("facility"), pk=kwargs["pk"])
        context["checkin"] = checkin
        return context


class FacilityDriverQRCodeView(StaffRequiredMixin, DetailView):
    model = Facility
    template_name = "checkins/facility_driver_qr.html"
    context_object_name = "facility"

    def get_queryset(self):
        return Facility.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        driver_url = self.request.build_absolute_uri(
            reverse("driver_checkin", args=[self.object.pk])
        )
        context["driver_checkin_url"] = driver_url
        context["driver_checkin_qr_svg"] = mark_safe(self.build_qr_svg(driver_url))
        return context

    @staticmethod
    def build_qr_svg(data: str) -> str:
        image = qrcode.make(data, image_factory=SvgPathImage, box_size=8, border=2)
        buffer = BytesIO()
        image.save(buffer)
        return buffer.getvalue().decode("utf-8")


class CheckInDetailView(StaffRequiredMixin, DetailView):
    model = CheckIn
    template_name = "checkins/checkin_detail.html"
    context_object_name = "checkin"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dispatch_form"] = kwargs.get("dispatch_form") or DispatchUpdateForm(instance=self.object)
        context["sms_form"] = kwargs.get("sms_form") or SMSMessageForm(
            initial={"body": self.get_default_sms_message()}
        )
        context["sms_history"] = self.object.sms_messages.all()[:5]
        return context

    def get_default_sms_message(self) -> str:
        dock_text = (
            f"Dock {self.object.dock_number}"
            if self.object.dock_number
            else "the receiving desk"
        )
        return (
            f"{self.object.driver_name}, your load {self.object.load_reference} is checked in "
            f"at {self.object.facility.name}. Please proceed to {dock_text}."
        )


class UpdateCheckInView(StaffRequiredMixin, View):
    def post(self, request, pk):
        checkin = get_object_or_404(CheckIn, pk=pk)
        action = request.POST.get("action", "").strip()

        if action == "complete":
            checkin.status = CheckIn.Status.COMPLETED
            checkin.save(update_fields=["status"])
            messages.success(request, "Truck checkout completed.")
            return redirect("dashboard")

        form = DispatchUpdateForm(request.POST, instance=checkin)
        if not form.is_valid():
            detail_view = CheckInDetailView()
            detail_view.request = request
            detail_view.object = checkin
            context = detail_view.get_context_data(dispatch_form=form)
            return detail_view.render_to_response(context)

        updated_checkin = form.save()
        status_label = updated_checkin.get_status_display()
        dock_label = updated_checkin.dock_number or "Pending"
        initials_label = updated_checkin.warehouse_staff_initials or "Not set"
        messages.success(
            request,
            f"Dispatch updated: status set to {status_label}, dock {dock_label}, staff initials {initials_label}.",
        )
        return redirect(updated_checkin)


class SendSMSView(StaffRequiredMixin, View):
    def post(self, request, pk):
        checkin = get_object_or_404(CheckIn, pk=pk)
        form = SMSMessageForm(request.POST)
        if not checkin.phone_number:
            messages.error(request, "This driver does not have a phone number on file.")
            return redirect(checkin)

        if not form.is_valid():
            detail_view = CheckInDetailView()
            detail_view.request = request
            detail_view.object = checkin
            context = detail_view.get_context_data(sms_form=form)
            return detail_view.render_to_response(context)

        body = form.cleaned_data["body"].strip()
        if self.is_rate_limited(request, checkin.pk):
            messages.error(request, "Please wait before sending another text for this load.")
            return redirect(checkin)

        with transaction.atomic():
            sms_message = SMSMessage.objects.create(
                checkin=checkin,
                to_number=checkin.phone_number,
                from_number=settings.SMS_FROM_NUMBER or "",
                body=body,
                delivery_status=SMSMessage.DeliveryStatus.QUEUED,
            )
            OutboundSMS.objects.create(
                checkin=checkin,
                sms_message=sms_message,
                to_number=checkin.phone_number,
                body=body,
            )

        messages.success(request, "Text message queued for delivery to the driver.")
        return redirect(checkin)

    def is_rate_limited(self, request, checkin_id: int) -> bool:
        remote_addr = request.META.get("REMOTE_ADDR", "unknown")
        cache_key = f"sms-rate-limit:{checkin_id}:{remote_addr}"
        cooldown_seconds = max(1, int(settings.SMS_RATE_LIMIT_SECONDS))
        return not cache.add(cache_key, True, timeout=cooldown_seconds)


class QRScannerView(StaffRequiredMixin, TemplateView):
    template_name = "checkins/scan.html"


class QRLookupView(StaffRequiredMixin, TemplateView):
    template_name = "checkins/scan.html"

    def get(self, request, *args, **kwargs):
        raw_code = request.GET.get("code", "").strip()
        normalized_code = self.normalize_code(raw_code)
        if not normalized_code:
            return redirect("qr_scan")

        existing_checkin = CheckIn.objects.filter(load_reference=normalized_code).first()
        if existing_checkin:
            return redirect(existing_checkin)
        create_url = reverse("checkin_create")
        return HttpResponseRedirect(
            f"{create_url}?load_reference={quote(normalized_code)}"
        )

    @staticmethod
    def normalize_code(raw_code: str) -> str:
        if not raw_code:
            return ""
        trimmed = raw_code.strip()
        marker = "load_reference="
        if marker in trimmed:
            return trimmed.split(marker, 1)[1].split("&", 1)[0].strip()
        return trimmed


class HealthCheckView(View):
    def get(self, request, *args, **kwargs):
        payload = {
            "status": "ok",
            "environment": settings.ENVIRONMENT,
        }
        http_status = 200

        try:
            connections["default"].cursor().execute("SELECT 1")
            facility_count = Facility.objects.count()
            payload["database"] = "ok"
            payload["facility_count"] = facility_count
        except DatabaseError:
            payload["database"] = "error"
            payload["status"] = "error"
            http_status = 503

        cache_probe_key = "healthz:probe"
        try:
            cache.set(cache_probe_key, "ok", timeout=30)
            payload["cache"] = "ok" if cache.get(cache_probe_key) == "ok" else "error"
        except Exception:
            payload["cache"] = "error"
        if payload.get("cache") != "ok":
            payload["status"] = "error"
            http_status = 503

        payload.update(self.worker_health_payload())
        return JsonResponse(payload, status=http_status)

    @staticmethod
    def worker_health_payload() -> dict[str, object]:
        now = timezone.now()
        worker_heartbeat = cache.get("sms-worker:heartbeat")
        worker_seen_at = parse_datetime(worker_heartbeat) if worker_heartbeat else None
        worker_healthy = bool(
            worker_seen_at and (now - worker_seen_at).total_seconds() <= settings.SMS_WORKER_HEARTBEAT_TTL
        )
        payload = {
            "sms_worker": "ok" if worker_healthy else "error",
            "queue_depth": OutboundSMS.objects.filter(status=OutboundSMS.Status.PENDING).count(),
        }
        if worker_seen_at:
            payload["sms_worker_seen_at"] = worker_seen_at.isoformat()
        return payload


class WorkerHealthCheckView(View):
    def get(self, request, *args, **kwargs):
        payload = {
            "status": "ok",
            "environment": settings.ENVIRONMENT,
        }
        payload.update(HealthCheckView.worker_health_payload())
        http_status = 200
        if payload["sms_worker"] != "ok":
            payload["status"] = "error"
            http_status = 503
        return JsonResponse(payload, status=http_status)
