from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone


class Carrier(models.Model):
    name = models.CharField(max_length=120)
    usdot_number = models.CharField(max_length=20, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Facility(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    street_address = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=2)
    dock_count = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "facilities"

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "facility"
            slug = base_slug
            index = 2
            while Facility.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                slug = f"{base_slug}-{index}"
                index += 1
            self.slug = slug
        super().save(*args, **kwargs)


class CheckIn(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        ON_DOCK = "on_dock", "On Dock"
        UNLOADING = "unloading", "Unloading"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    driver_name = models.CharField(max_length=120)
    phone_number = models.CharField(max_length=20, blank=True)
    cdl_number = models.CharField(max_length=40, blank=True)
    truck_number = models.CharField(max_length=30)
    trailer_number = models.CharField(max_length=30, blank=True)
    trailer_license_plate = models.CharField(max_length=30, blank=True)
    load_reference = models.CharField(max_length=40, unique=True)
    bol_number = models.CharField(max_length=40, blank=True)
    carrier = models.ForeignKey(Carrier, on_delete=models.PROTECT, related_name="checkins")
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name="checkins")
    appointment_time = models.DateTimeField()
    weight_in_out = models.CharField(max_length=80, blank=True)
    arrival_time = models.DateTimeField(auto_now_add=True)
    dock_number = models.PositiveIntegerField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING)
    cargo_description = models.CharField(max_length=200, blank=True)
    temperature_controlled = models.BooleanField(default=False)
    temperature_setpoint = models.CharField(max_length=40, blank=True)
    actual_temperature = models.CharField(max_length=40, blank=True)
    destination_delivery_address = models.TextField(blank=True)
    driver_signature = models.CharField(max_length=120, blank=True)
    warehouse_staff_initials = models.CharField(max_length=20, blank=True)
    safety_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["status", "-arrival_time"]
        verbose_name = "MonetteFarms check-in entry"
        verbose_name_plural = "MonetteFarms check-in entries"

    def __str__(self) -> str:
        return f"{self.driver_name} - {self.load_reference}"

    def get_absolute_url(self):
        return reverse("checkin_detail", args=[self.pk])


class SMSMessage(models.Model):
    class DeliveryStatus(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    checkin = models.ForeignKey(CheckIn, on_delete=models.CASCADE, related_name="sms_messages")
    to_number = models.CharField(max_length=20)
    from_number = models.CharField(max_length=20, blank=True)
    body = models.TextField()
    delivery_status = models.CharField(
        max_length=10,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.SENT,
    )
    provider_message_id = models.CharField(max_length=120, blank=True)
    error_message = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "driver text message"
        verbose_name_plural = "driver text messages"

    def __str__(self) -> str:
        return f"{self.checkin.load_reference} -> {self.to_number}"


class OutboundSMS(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    checkin = models.ForeignKey(CheckIn, on_delete=models.CASCADE, related_name="outbound_sms")
    sms_message = models.OneToOneField(
        SMSMessage,
        on_delete=models.CASCADE,
        related_name="outbound_sms",
    )
    to_number = models.CharField(max_length=20)
    body = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "outbound SMS job"
        verbose_name_plural = "outbound SMS jobs"

    def __str__(self) -> str:
        return f"{self.checkin.load_reference} -> {self.to_number} ({self.status})"
