from django.urls import path

from . import views


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("checkins/", views.dashboard, name="checkins"),
    path("scan/", views.qr_scan, name="qr_scan"),
    path("scan/lookup/", views.qr_lookup, name="qr_lookup"),
    path("checkins/new/", views.checkin_create, name="checkin_create"),
    path("checkins/<int:pk>/", views.checkin_detail, name="checkin_detail"),
    path("checkins/<int:pk>/update/", views.checkin_update, name="checkin_update"),
    path("checkins/<int:pk>/send-sms/", views.checkin_send_sms, name="checkin_send_sms"),
    path("driver/<int:facility_pk>/", views.driver_checkin, name="driver_checkin"),
    path("driver/submitted/<int:pk>/", views.driver_checkin_submitted, name="driver_checkin_submitted"),
    path("facilities/<int:facility_pk>/driver-qr/", views.facility_driver_qr, name="facility_driver_qr"),
    path("healthz/", views.healthz, name="healthz"),
    path("healthz/worker/", views.worker_healthz, name="worker_healthz"),
]
