from django.contrib import admin

from .models import Carrier, CheckIn, Facility, OutboundSMS, SMSMessage


@admin.register(Carrier)
class CarrierAdmin(admin.ModelAdmin):
    list_display = ("name", "usdot_number", "phone_number")
    search_fields = ("name", "usdot_number")


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "street_address", "city", "state", "dock_count", "is_active")
    list_filter = ("state", "is_active")
    search_fields = ("name", "slug", "street_address", "city", "state")


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    list_display = (
        "driver_name",
        "load_reference",
        "carrier",
        "facility",
        "status",
        "dock_number",
        "arrival_time",
    )
    list_filter = ("status", "facility", "temperature_controlled")
    search_fields = (
        "driver_name",
        "truck_number",
        "trailer_number",
        "trailer_license_plate",
        "load_reference",
        "bol_number",
        "driver_signature",
        "warehouse_staff_initials",
    )
    autocomplete_fields = ("carrier", "facility")


@admin.register(SMSMessage)
class SMSMessageAdmin(admin.ModelAdmin):
    list_display = (
        "checkin",
        "to_number",
        "delivery_status",
        "provider_message_id",
        "created_at",
    )
    list_filter = ("delivery_status", "created_at")
    search_fields = ("checkin__load_reference", "to_number", "body", "provider_message_id")


@admin.register(OutboundSMS)
class OutboundSMSAdmin(admin.ModelAdmin):
    list_display = (
        "checkin",
        "to_number",
        "status",
        "attempts",
        "processed_at",
        "created_at",
    )
    list_filter = ("status", "created_at", "processed_at")
    search_fields = ("checkin__load_reference", "to_number", "body", "last_error")
