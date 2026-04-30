"""
URL configuration for djangoproject project.
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from checkins.views import HealthCheckView, WorkerHealthCheckView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("healthz/", HealthCheckView.as_view(), name="healthz"),
    path("healthz/worker/", WorkerHealthCheckView.as_view(), name="worker_healthz"),
    path("", include("checkins.urls")),
]
