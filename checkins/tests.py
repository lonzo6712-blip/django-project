from datetime import timedelta

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import CheckInForm, DispatchUpdateForm, DriverSelfCheckInForm
from .models import Carrier, CheckIn, Facility, OutboundSMS, SMSMessage
from .sms import SMSDeliveryError, SMSDeliveryResult


class DashboardTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="dispatcher",
            password="StrongPassword123",
            is_staff=True,
        )
        self.nonstaff_user = get_user_model().objects.create_user(
            username="driverportal",
            password="StrongPassword123",
        )
        self.carrier = Carrier.objects.create(name="Northbound Freight")
        self.facility = Facility.objects.create(
            name="Tacoma Yard",
            street_address="1200 Port Way",
            city="Tacoma",
            state="WA",
            dock_count=8,
        )

    def login(self):
        self.client.login(username="dispatcher", password="StrongPassword123")

    def login_nonstaff(self):
        self.client.login(username="driverportal", password="StrongPassword123")

    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse("dashboard"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('dashboard')}")

    def test_dashboard_rejects_nonstaff_user(self):
        self.login_nonstaff()

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_dashboard_loads_recent_checkins_for_authenticated_user(self):
        self.login()
        checkin = CheckIn.objects.create(
            driver_name="Sam Ortiz",
            truck_number="TRK-44",
            trailer_number="TRL-98",
            load_reference="LOAD-1001",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, checkin.load_reference)

    def test_dashboard_separates_waiting_and_completed_trucks(self):
        self.login()
        waiting_checkin = CheckIn.objects.create(
            driver_name="Sam Ortiz",
            truck_number="TRK-44",
            trailer_number="TRL-98",
            load_reference="LOAD-WAITING",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
            status=CheckIn.Status.WAITING,
        )
        completed_checkin = CheckIn.objects.create(
            driver_name="Alex Chen",
            truck_number="TRK-45",
            trailer_number="TRL-99",
            load_reference="LOAD-COMPLETE",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
            status=CheckIn.Status.COMPLETED,
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["waiting_checkins"], [waiting_checkin])
        self.assertEqual(response.context["completed_checkins"], [completed_checkin])
        self.assertContains(response, "Waiting Trucks")
        self.assertContains(response, "Completed Trucks")

    def test_qr_lookup_redirects_existing_checkin(self):
        self.login()
        checkin = CheckIn.objects.create(
            driver_name="Sam Ortiz",
            truck_number="TRK-44",
            trailer_number="TRL-98",
            load_reference="LOAD-2002",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
        )

        response = self.client.get(reverse("qr_lookup"), {"code": "LOAD-2002"})

        self.assertRedirects(response, reverse("checkin_detail", args=[checkin.pk]))

    def test_qr_lookup_prefills_new_checkin_when_missing(self):
        self.login()
        response = self.client.get(reverse("qr_lookup"), {"code": "LOAD-3003"})

        self.assertRedirects(response, f"{reverse('checkin_create')}?load_reference=LOAD-3003")

    def test_checkin_form_prefills_load_reference_from_scan(self):
        self.login()
        response = self.client.get(reverse("checkin_create"), {"load_reference": "LOAD-4004"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="LOAD-4004"')

    def test_checkin_form_accepts_typed_carrier_and_selected_facility(self):
        form = CheckInForm(
            data={
                "driver_name": "Sam Ortiz",
                "phone_number": "+15551234567",
                "truck_number": "TRK-44",
                "facility": self.facility.pk,
                "trailer_number": "TRL-98",
                "load_reference": "LOAD-4500",
                "carrier_name": "Open Road Logistics",
                "appointment_time": "2026-04-26T10:30",
                "temperature_controlled": False,
                "safety_notes": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        checkin = form.save()

        self.assertEqual(checkin.carrier.name, "Open Road Logistics")
        self.assertEqual(checkin.facility, self.facility)

    def test_driver_self_checkin_form_assigns_facility_from_view(self):
        form = DriverSelfCheckInForm(
            data={
                "driver_name": "Sam Ortiz",
                "phone_number": "+15551234567",
                "truck_number": "TRK-44",
                "trailer_number": "TRL-98",
                "trailer_license_plate": "ABC-1234",
                "load_reference": "LOAD-4501",
                "bol_number": "BOL-4501",
                "carrier_name": "Open Road Logistics",
                "appointment_time": "2026-04-26T10:30",
                "weight_in_out": "74200 / 31850",
                "temperature_controlled": False,
                "temperature_setpoint": "34F",
                "actual_temperature": "35F",
                "destination_delivery_address": "1200 Port Way, Tacoma, WA",
                "driver_signature": "Sam Ortiz",
                "safety_notes": "Check seal before unloading.",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.instance.facility = self.facility
        checkin = form.save()

        self.assertEqual(checkin.facility, self.facility)
        self.assertEqual(checkin.carrier.name, "Open Road Logistics")
        self.assertEqual(checkin.trailer_license_plate, "ABC-1234")
        self.assertEqual(checkin.bol_number, "BOL-4501")
        self.assertEqual(checkin.weight_in_out, "74200 / 31850")
        self.assertEqual(checkin.temperature_setpoint, "34F")
        self.assertEqual(checkin.actual_temperature, "35F")
        self.assertEqual(checkin.destination_delivery_address, "1200 Port Way, Tacoma, WA")
        self.assertEqual(checkin.driver_signature, "Sam Ortiz")

    def test_checkin_form_requires_an_active_facility(self):
        Facility.objects.all().delete()
        form = CheckInForm(
            data={
                "driver_name": "Sam Ortiz",
                "phone_number": "+15551234567",
                "truck_number": "TRK-44",
                "carrier_name": "Open Road Logistics",
                "load_reference": "LOAD-4510",
                "appointment_time": "2026-04-26T10:30",
                "temperature_controlled": False,
                "safety_notes": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("facility", form.errors)

    def test_public_driver_checkin_page_is_accessible_without_login(self):
        response = self.client.get(reverse("driver_checkin", args=[self.facility.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MonetteFarms Driver Check-In")
        self.assertContains(response, self.facility.street_address)

    def test_legacy_numeric_driver_url_redirects_to_slug_url(self):
        response = self.client.get(reverse("legacy_driver_checkin", args=[self.facility.pk]))

        self.assertRedirects(
            response,
            reverse("driver_checkin", args=[self.facility.slug]),
            status_code=301,
            target_status_code=200,
        )

    def test_public_driver_checkin_submission_creates_checkin(self):
        response = self.client.post(
            reverse("driver_checkin", args=[self.facility.slug]),
            {
                "driver_name": "Sam Ortiz",
                "phone_number": "+15551234567",
                "truck_number": "TRK-44",
                "trailer_number": "TRL-98",
                "trailer_license_plate": "ABC-1234",
                "load_reference": "LOAD-9009",
                "bol_number": "BOL-9009",
                "carrier_name": "Open Road Logistics",
                "appointment_time": "2026-04-26T10:30",
                "weight_in_out": "74200 / 31850",
                "temperature_controlled": True,
                "temperature_setpoint": "34F",
                "actual_temperature": "35F",
                "destination_delivery_address": "1200 Port Way, Tacoma, WA",
                "driver_signature": "Sam Ortiz",
                "safety_notes": "Arriving with reefer running.",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check-In Submitted")
        checkin = CheckIn.objects.get(load_reference="LOAD-9009")
        self.assertEqual(checkin.facility, self.facility)
        self.assertEqual(checkin.carrier.name, "Open Road Logistics")
        self.assertEqual(checkin.trailer_license_plate, "ABC-1234")
        self.assertEqual(checkin.bol_number, "BOL-9009")
        self.assertEqual(checkin.weight_in_out, "74200 / 31850")
        self.assertEqual(checkin.temperature_setpoint, "34F")
        self.assertEqual(checkin.actual_temperature, "35F")
        self.assertEqual(checkin.destination_delivery_address, "1200 Port Way, Tacoma, WA")
        self.assertEqual(checkin.driver_signature, "Sam Ortiz")

    def test_public_driver_checkin_applies_rate_limit(self):
        first_response = self.client.post(
            reverse("driver_checkin", args=[self.facility.slug]),
            {
                "driver_name": "Sam Ortiz",
                "phone_number": "+15551234567",
                "truck_number": "TRK-44",
                "trailer_number": "TRL-98",
                "load_reference": "LOAD-9010",
                "carrier_name": "Open Road Logistics",
                "appointment_time": "2026-04-26T10:30",
                "temperature_controlled": False,
                "safety_notes": "",
            },
            follow=True,
        )
        second_response = self.client.post(
            reverse("driver_checkin", args=[self.facility.slug]),
            {
                "driver_name": "Sam Ortiz",
                "phone_number": "+15551234567",
                "truck_number": "TRK-44",
                "trailer_number": "TRL-98",
                "load_reference": "LOAD-9011",
                "carrier_name": "Open Road Logistics",
                "appointment_time": "2026-04-26T10:30",
                "temperature_controlled": False,
                "safety_notes": "",
            },
            follow=True,
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertContains(second_response, "Please wait before submitting another MonetteFarms driver check-in.")
        self.assertFalse(CheckIn.objects.filter(load_reference="LOAD-9011").exists())

    def test_facility_driver_qr_requires_authentication(self):
        response = self.client.get(reverse("facility_driver_qr", args=[self.facility.slug]))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('facility_driver_qr', args=[self.facility.slug])}",
        )

    def test_facility_driver_qr_renders_svg_for_staff(self):
        self.login()

        response = self.client.get(reverse("facility_driver_qr", args=[self.facility.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<svg", html=False)
        self.assertContains(response, reverse("driver_checkin", args=[self.facility.slug]))

    def test_legacy_numeric_qr_url_redirects_to_slug_url(self):
        self.login()

        response = self.client.get(reverse("legacy_facility_driver_qr", args=[self.facility.pk]))

        self.assertRedirects(
            response,
            reverse("facility_driver_qr", args=[self.facility.slug]),
            status_code=301,
            target_status_code=200,
        )

    def test_facility_driver_qr_rejects_nonstaff_user(self):
        self.login_nonstaff()

        response = self.client.get(reverse("facility_driver_qr", args=[self.facility.slug]))

        self.assertEqual(response.status_code, 403)

    def test_checkin_detail_includes_dispatch_form_for_staff(self):
        self.login()
        checkin = CheckIn.objects.create(
            driver_name="Sam Ortiz",
            phone_number="+15551234567",
            truck_number="TRK-44",
            trailer_number="TRL-98",
            load_reference="LOAD-2010",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
        )

        response = self.client.get(reverse("checkin_detail", args=[checkin.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["dispatch_form"], DispatchUpdateForm)
        self.assertContains(response, "Dispatch Actions")
        self.assertContains(response, "Back to Dashboard")

    def test_dispatcher_can_update_checkin_status_and_dock(self):
        self.login()
        checkin = CheckIn.objects.create(
            driver_name="Sam Ortiz",
            phone_number="+15551234567",
            truck_number="TRK-44",
            trailer_number="TRL-98",
            load_reference="LOAD-2011",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
        )

        response = self.client.post(
            reverse("checkin_update", args=[checkin.pk]),
            {"status": CheckIn.Status.ON_DOCK, "dock_number": 4, "warehouse_staff_initials": "JD"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        checkin.refresh_from_db()
        self.assertEqual(checkin.status, CheckIn.Status.ON_DOCK)
        self.assertEqual(checkin.dock_number, 4)
        self.assertEqual(checkin.warehouse_staff_initials, "JD")
        self.assertContains(response, "Dispatch updated: status set to On Dock, dock 4, staff initials JD.")

    def test_dispatcher_can_complete_truck_checkout(self):
        self.login()
        checkin = CheckIn.objects.create(
            driver_name="Sam Ortiz",
            phone_number="+15551234567",
            truck_number="TRK-44",
            trailer_number="TRL-98",
            load_reference="LOAD-2012",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
            status=CheckIn.Status.UNLOADING,
            dock_number=7,
        )

        response = self.client.post(
            reverse("checkin_update", args=[checkin.pk]),
            {"action": "complete"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        checkin.refresh_from_db()
        self.assertEqual(checkin.status, CheckIn.Status.COMPLETED)
        self.assertEqual(checkin.dock_number, 7)
        self.assertContains(response, "Truck checkout completed.")
        self.assertTrue(response.redirect_chain)
        self.assertEqual(response.redirect_chain[-1][0], reverse("dashboard"))

    def test_checkin_update_rejects_nonstaff_user(self):
        self.login_nonstaff()
        checkin = CheckIn.objects.create(
            driver_name="Sam Ortiz",
            truck_number="TRK-44",
            trailer_number="TRL-98",
            load_reference="LOAD-2013",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
        )

        response = self.client.post(
            reverse("checkin_update", args=[checkin.pk]),
            {"status": CheckIn.Status.COMPLETED},
        )

        self.assertEqual(response.status_code, 403)

    def test_health_check_returns_ok(self):
        cache.set("sms-worker:heartbeat", timezone.now().isoformat(), timeout=60)
        response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["database"], "ok")
        self.assertEqual(response.json()["cache"], "ok")
        self.assertEqual(response.json()["sms_worker"], "ok")

    def test_health_check_reports_missing_worker_heartbeat_without_failing_web_probe(self):
        response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["sms_worker"], "error")

    def test_worker_health_check_reports_missing_worker_heartbeat(self):
        response = self.client.get(reverse("worker_healthz"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(response.json()["sms_worker"], "error")

    def test_worker_health_check_returns_ok_for_fresh_heartbeat(self):
        cache.set("sms-worker:heartbeat", timezone.now().isoformat(), timeout=60)

        response = self.client.get(reverse("worker_healthz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["sms_worker"], "ok")

    def test_send_sms_queues_message_for_delivery(self):
        self.login()
        checkin = CheckIn.objects.create(
            driver_name="Sam Ortiz",
            phone_number="+15551234567",
            truck_number="TRK-44",
            trailer_number="TRL-98",
            load_reference="LOAD-5005",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
        )

        response = self.client.post(
            reverse("checkin_send_sms", args=[checkin.pk]),
            {"body": "Proceed to dock 4."},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Text message queued for delivery to the driver.")
        sms = SMSMessage.objects.get(checkin=checkin)
        self.assertEqual(sms.delivery_status, SMSMessage.DeliveryStatus.QUEUED)
        self.assertEqual(OutboundSMS.objects.get(checkin=checkin).status, OutboundSMS.Status.PENDING)

    @patch("checkins.management.commands.process_outbound_sms.get_sms_backend")
    def test_process_outbound_sms_marks_sent_message(self, get_sms_backend):
        self.login()
        checkin = CheckIn.objects.create(
            driver_name="Sam Ortiz",
            phone_number="+15551234567",
            truck_number="TRK-44",
            trailer_number="TRL-98",
            load_reference="LOAD-6006",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
        )
        sms = SMSMessage.objects.create(
            checkin=checkin,
            to_number=checkin.phone_number,
            from_number="",
            body="Dock assignment changed.",
            delivery_status=SMSMessage.DeliveryStatus.QUEUED,
        )
        job = OutboundSMS.objects.create(
            checkin=checkin,
            sms_message=sms,
            to_number=checkin.phone_number,
            body=sms.body,
        )
        backend = get_sms_backend.return_value
        backend.send_message.return_value = SMSDeliveryResult(
            provider_message_id="msg-123",
            from_number="+15550000000",
        )

        from django.core.management import call_command
        call_command("process_outbound_sms")

        job.refresh_from_db()
        sms.refresh_from_db()
        self.assertEqual(job.status, OutboundSMS.Status.SENT)
        self.assertEqual(sms.delivery_status, SMSMessage.DeliveryStatus.SENT)
        self.assertEqual(sms.provider_message_id, "msg-123")
        self.assertTrue(cache.get("sms-worker:heartbeat"))

    @patch("checkins.management.commands.process_outbound_sms.get_sms_backend")
    def test_process_outbound_sms_marks_failed_message(self, get_sms_backend):
        checkin = CheckIn.objects.create(
            driver_name="Sam Ortiz",
            phone_number="+15551234567",
            truck_number="TRK-44",
            trailer_number="TRL-98",
            load_reference="LOAD-6006",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
        )
        sms = SMSMessage.objects.create(
            checkin=checkin,
            to_number=checkin.phone_number,
            from_number="",
            body="Dock assignment changed.",
            delivery_status=SMSMessage.DeliveryStatus.QUEUED,
        )
        job = OutboundSMS.objects.create(
            checkin=checkin,
            sms_message=sms,
            to_number=checkin.phone_number,
            body=sms.body,
        )
        backend = get_sms_backend.return_value
        backend.send_message.side_effect = SMSDeliveryError("Provider timeout")

        from django.core.management import call_command
        call_command("process_outbound_sms")

        job.refresh_from_db()
        sms.refresh_from_db()
        self.assertEqual(job.status, OutboundSMS.Status.FAILED)
        self.assertEqual(sms.delivery_status, SMSMessage.DeliveryStatus.FAILED)
        self.assertEqual(sms.error_message, "Provider timeout")

    @override_settings(SMS_MAX_ATTEMPTS=3, SMS_RETRY_BASE_SECONDS=30)
    @patch("checkins.management.commands.process_outbound_sms.get_sms_backend")
    def test_process_outbound_sms_retries_transient_failure(self, get_sms_backend):
        checkin = CheckIn.objects.create(
            driver_name="Sam Ortiz",
            phone_number="+15551234567",
            truck_number="TRK-44",
            trailer_number="TRL-98",
            load_reference="LOAD-6010",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
        )
        sms = SMSMessage.objects.create(
            checkin=checkin,
            to_number=checkin.phone_number,
            from_number="",
            body="Dock assignment changed.",
            delivery_status=SMSMessage.DeliveryStatus.QUEUED,
        )
        job = OutboundSMS.objects.create(
            checkin=checkin,
            sms_message=sms,
            to_number=checkin.phone_number,
            body=sms.body,
        )
        backend = get_sms_backend.return_value
        backend.send_message.side_effect = SMSDeliveryError("Provider timeout", retryable=True)

        from django.core.management import call_command
        before_attempt = timezone.now()
        call_command("process_outbound_sms")

        job.refresh_from_db()
        sms.refresh_from_db()
        self.assertEqual(job.status, OutboundSMS.Status.PENDING)
        self.assertEqual(job.attempts, 1)
        self.assertGreaterEqual(job.next_attempt_at, before_attempt + timedelta(seconds=30))
        self.assertIsNone(job.processed_at)
        self.assertEqual(sms.delivery_status, SMSMessage.DeliveryStatus.QUEUED)
        self.assertEqual(sms.error_message, "Provider timeout")

    @override_settings(SMS_MAX_ATTEMPTS=2, SMS_RETRY_BASE_SECONDS=30)
    @patch("checkins.management.commands.process_outbound_sms.get_sms_backend")
    def test_process_outbound_sms_stops_retrying_at_max_attempts(self, get_sms_backend):
        checkin = CheckIn.objects.create(
            driver_name="Sam Ortiz",
            phone_number="+15551234567",
            truck_number="TRK-44",
            trailer_number="TRL-98",
            load_reference="LOAD-6011",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
        )
        sms = SMSMessage.objects.create(
            checkin=checkin,
            to_number=checkin.phone_number,
            from_number="",
            body="Dock assignment changed.",
            delivery_status=SMSMessage.DeliveryStatus.QUEUED,
        )
        job = OutboundSMS.objects.create(
            checkin=checkin,
            sms_message=sms,
            to_number=checkin.phone_number,
            body=sms.body,
            attempts=1,
        )
        backend = get_sms_backend.return_value
        backend.send_message.side_effect = SMSDeliveryError("Provider timeout", retryable=True)

        from django.core.management import call_command
        call_command("process_outbound_sms")

        job.refresh_from_db()
        sms.refresh_from_db()
        self.assertEqual(job.status, OutboundSMS.Status.FAILED)
        self.assertEqual(job.attempts, 2)
        self.assertIsNotNone(job.processed_at)
        self.assertEqual(sms.delivery_status, SMSMessage.DeliveryStatus.FAILED)

    def test_send_sms_requires_phone_number(self):
        self.login()
        checkin = CheckIn.objects.create(
            driver_name="Sam Ortiz",
            truck_number="TRK-44",
            trailer_number="TRL-98",
            load_reference="LOAD-7007",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
        )

        response = self.client.post(
            reverse("checkin_send_sms", args=[checkin.pk]),
            {"body": "Proceed to dock 2."},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This driver does not have a phone number on file.")
        self.assertFalse(SMSMessage.objects.filter(checkin=checkin).exists())

    def test_send_sms_applies_rate_limit(self):
        self.login()
        checkin = CheckIn.objects.create(
            driver_name="Sam Ortiz",
            phone_number="+15551234567",
            truck_number="TRK-44",
            trailer_number="TRL-98",
            load_reference="LOAD-8008",
            carrier=self.carrier,
            facility=self.facility,
            appointment_time=timezone.now(),
        )
        first_response = self.client.post(
            reverse("checkin_send_sms", args=[checkin.pk]),
            {"body": "Proceed to dock 4."},
            follow=True,
        )
        second_response = self.client.post(
            reverse("checkin_send_sms", args=[checkin.pk]),
            {"body": "Proceed to dock 5."},
            follow=True,
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertContains(second_response, "Please wait before sending another text for this load.")
        self.assertEqual(SMSMessage.objects.filter(checkin=checkin).count(), 1)

    def test_twilio_production_settings_fail_fast_when_missing(self):
        from djangoproject import settings as project_settings

        with (
            patch.object(project_settings, "IS_PRODUCTION", True),
            patch.object(project_settings, "SMS_BACKEND", "checkins.sms.TwilioSMSBackend"),
            patch.object(project_settings, "SMS_FROM_NUMBER", ""),
            patch.object(project_settings, "SMS_TWILIO_ACCOUNT_SID", ""),
            patch.object(project_settings, "SMS_TWILIO_AUTH_TOKEN", ""),
        ):
            with self.assertRaises(ImproperlyConfigured):
                project_settings.validate_sms_settings()
