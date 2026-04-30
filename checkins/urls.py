from django.urls import path
from django.views.generic import RedirectView

from .views import (
    CheckInCreateView,
    CheckInDetailView,
    DashboardView,
    DriverCheckInSubmittedView,
    DriverCheckInView,
    FacilityDriverQRCodeView,
    QRLookupView,
    QRScannerView,
    SendSMSView,
    UpdateCheckInView,
)


urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
    path("checkins/", DashboardView.as_view(), name="dashboard"),
    path("driver-checkin/<int:facility_id>/", DriverCheckInView.as_view(), name="driver_checkin"),
    path(
        "driver-checkin/submitted/<int:pk>/",
        DriverCheckInSubmittedView.as_view(),
        name="driver_checkin_submitted",
    ),
    path("MonetteFarmsCheck-out/", RedirectView.as_view(pattern_name="dashboard", permanent=True)),
    path(
        "MonetteFarmsdriverCheck-in/<int:facility_id>/",
        RedirectView.as_view(pattern_name="driver_checkin", permanent=True),
    ),
    path(
        "MonetteFarmsdriverCheck-in/submitted/<int:pk>/",
        RedirectView.as_view(pattern_name="driver_checkin_submitted", permanent=True),
    ),
    path("scan/", QRScannerView.as_view(), name="qr_scan"),
    path("scan/lookup/", QRLookupView.as_view(), name="qr_lookup"),
    path("checkins/new/", CheckInCreateView.as_view(), name="checkin_create"),
    path("facilities/<int:pk>/driver-qr/", FacilityDriverQRCodeView.as_view(), name="facility_driver_qr"),
    path("checkins/<int:pk>/update/", UpdateCheckInView.as_view(), name="checkin_update"),
    path("checkins/<int:pk>/text/", SendSMSView.as_view(), name="checkin_send_sms"),
    path("checkins/<int:pk>/", CheckInDetailView.as_view(), name="checkin_detail"),
]
