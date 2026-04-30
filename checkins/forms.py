from django import forms

from .models import Carrier, CheckIn, Facility


class BaseCheckInForm(forms.ModelForm):
    carrier_name = forms.CharField(label="Carrier", max_length=120)
    appointment_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    class Meta:
        model = CheckIn
        fields = [
            "driver_name",
            "phone_number",
            "truck_number",
            "trailer_number",
            "trailer_license_plate",
            "load_reference",
            "bol_number",
            "appointment_time",
            "weight_in_out",
            "temperature_controlled",
            "temperature_setpoint",
            "actual_temperature",
            "destination_delivery_address",
            "driver_signature",
            "safety_notes",
        ]
        widgets = {
            "destination_delivery_address": forms.Textarea(attrs={"rows": 3}),
            "safety_notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["carrier_name"].initial = self.instance.carrier.name

    def save(self, commit=True):
        carrier_name = self.cleaned_data["carrier_name"].strip()
        carrier, _ = Carrier.objects.get_or_create(name=carrier_name)

        self.instance.carrier = carrier
        return super().save(commit=commit)


class CheckInForm(BaseCheckInForm):
    facility = forms.ModelChoiceField(
        queryset=Facility.objects.none(),
        empty_label=None,
    )

    class Meta(BaseCheckInForm.Meta):
        fields = [
            "driver_name",
            "phone_number",
            "truck_number",
            "facility",
            "trailer_number",
            "trailer_license_plate",
            "load_reference",
            "bol_number",
            "appointment_time",
            "weight_in_out",
            "temperature_controlled",
            "temperature_setpoint",
            "actual_temperature",
            "destination_delivery_address",
            "driver_signature",
            "safety_notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(
            [
                "driver_name",
                "phone_number",
                "truck_number",
                "carrier_name",
                "facility",
                "trailer_number",
                "trailer_license_plate",
                "load_reference",
                "bol_number",
                "appointment_time",
                "weight_in_out",
                "temperature_controlled",
                "temperature_setpoint",
                "actual_temperature",
                "destination_delivery_address",
                "driver_signature",
                "safety_notes",
            ]
        )
        self.fields["facility"].queryset = Facility.objects.filter(is_active=True).order_by("name")

    def save(self, commit=True):
        self.instance.facility = self.cleaned_data["facility"]
        return super().save(commit=commit)


class DriverSelfCheckInForm(BaseCheckInForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(
            [
                "driver_name",
                "phone_number",
                "truck_number",
                "carrier_name",
                "trailer_number",
                "trailer_license_plate",
                "load_reference",
                "bol_number",
                "appointment_time",
                "weight_in_out",
                "temperature_controlled",
                "temperature_setpoint",
                "actual_temperature",
                "destination_delivery_address",
                "driver_signature",
                "safety_notes",
            ]
        )
        self.fields["driver_name"].label = "Driver Name"
        self.fields["phone_number"].label = "Driver Phone"
        self.fields["carrier_name"].label = "Trucking Company"
        self.fields["truck_number"].label = "Truck Number"
        self.fields["trailer_number"].label = "Trailer Number"
        self.fields["trailer_license_plate"].label = "License Plate (Trailer)"
        self.fields["load_reference"].label = "PO / Reference Number"
        self.fields["bol_number"].label = "BOL Number (if applicable)"
        self.fields["appointment_time"].label = "Date / Time In"
        self.fields["weight_in_out"].label = "Weight-In / Weight-Out"
        self.fields["temperature_controlled"].label = "Temperature Controlled Load"
        self.fields["temperature_setpoint"].label = "Temperature Setpoint"
        self.fields["actual_temperature"].label = "Actual Temp"
        self.fields["destination_delivery_address"].label = "Destination / Delivery Address"
        self.fields["driver_signature"].label = "Driver Signature"
        self.fields["safety_notes"].label = "Additional Notes"
        self.fields["phone_number"].widget.attrs["placeholder"] = "(555) 555-5555"
        self.fields["carrier_name"].widget.attrs["placeholder"] = "Carrier or fleet name"
        self.fields["truck_number"].widget.attrs["placeholder"] = "Truck Number"
        self.fields["trailer_number"].widget.attrs["placeholder"] = "Trailer Number"
        self.fields["trailer_license_plate"].widget.attrs["placeholder"] = "Trailer plate number"
        self.fields["load_reference"].widget.attrs["placeholder"] = "PO, reference, or BOL number"
        self.fields["bol_number"].widget.attrs["placeholder"] = "Optional BOL number"
        self.fields["weight_in_out"].widget.attrs["placeholder"] = "Inbound and outbound weight if known"
        self.fields["temperature_setpoint"].widget.attrs["placeholder"] = "Requested setpoint"
        self.fields["actual_temperature"].widget.attrs["placeholder"] = "Measured trailer temperature"
        self.fields["destination_delivery_address"].widget.attrs["placeholder"] = "Delivery address or destination details"
        self.fields["driver_signature"].widget.attrs["placeholder"] = "Type your full name"
        self.fields["safety_notes"].widget.attrs["placeholder"] = "Special instructions or load notes"


class DispatchUpdateForm(forms.ModelForm):
    class Meta:
        model = CheckIn
        fields = ["status", "dock_number", "warehouse_staff_initials"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dock_number"].required = False
        self.fields["dock_number"].widget.attrs["min"] = 1
        self.fields["warehouse_staff_initials"].required = False
        self.fields["warehouse_staff_initials"].label = "Warehouse Staff Initials"
        self.fields["warehouse_staff_initials"].widget.attrs["placeholder"] = "Staff initials"


class SMSMessageForm(forms.Form):
    body = forms.CharField(
        label="Text message",
        max_length=320,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Dock update, arrival note, or release notice",
            }
        ),
    )
