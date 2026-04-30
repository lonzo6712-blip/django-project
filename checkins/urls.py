from django.urls import path

from .views import checkins


urlpatterns = [
    path("", checkins, name="checkins"),
]
