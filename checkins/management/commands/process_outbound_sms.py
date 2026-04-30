from datetime import timedelta
import logging

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from checkins.models import OutboundSMS, SMSMessage
from checkins.sms import SMSDeliveryError, get_sms_backend

logger = logging.getLogger("checkins.sms_worker")


class Command(BaseCommand):
    help = "Process queued outbound SMS jobs."
    heartbeat_cache_key = "sms-worker:heartbeat"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Maximum number of queued SMS jobs to process.",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Keep polling for outbound SMS jobs instead of exiting after one pass.",
        )
        parser.add_argument(
            "--sleep-seconds",
            type=int,
            default=settings.SMS_WORKER_POLL_SECONDS,
            help="Seconds to wait between polling iterations in loop mode.",
        )

    def handle(self, *args, **options):
        limit = max(1, options["limit"])
        sleep_seconds = max(1, options["sleep_seconds"])

        if options["loop"]:
            while True:
                processed = self.process_pending_jobs(limit)
                self.stdout.write(self.style.SUCCESS(f"Processed {processed} outbound SMS job(s)."))
                self.touch_heartbeat()
                self.sleep(sleep_seconds)
            return

        processed = self.process_pending_jobs(limit)
        self.touch_heartbeat()
        self.stdout.write(self.style.SUCCESS(f"Processed {processed} outbound SMS job(s)."))

    def process_pending_jobs(self, limit: int) -> int:
        processed = 0
        now = timezone.now()
        pending_jobs = OutboundSMS.objects.filter(
            status=OutboundSMS.Status.PENDING,
            next_attempt_at__lte=now,
        ).order_by("created_at")[:limit]
        for job in pending_jobs:
            self.process_job(job)
            processed += 1
        return processed

    def touch_heartbeat(self) -> None:
        cache.set(
            self.heartbeat_cache_key,
            timezone.now().isoformat(),
            timeout=settings.SMS_WORKER_HEARTBEAT_TTL,
        )

    @staticmethod
    def sleep(seconds: int) -> None:
        from time import sleep

        sleep(seconds)

    def process_job(self, job: OutboundSMS) -> None:
        backend = get_sms_backend()

        with transaction.atomic():
            locked_job = OutboundSMS.objects.select_for_update().get(pk=job.pk)
            if locked_job.status != OutboundSMS.Status.PENDING:
                return
            locked_job.status = OutboundSMS.Status.PROCESSING
            locked_job.attempts += 1
            locked_job.save(update_fields=["status", "attempts"])

        try:
            logger.info(
                "Sending outbound SMS",
                extra={
                    "job_id": job.pk,
                    "checkin_id": job.checkin_id,
                    "attempt": locked_job.attempts,
                },
            )
            result = backend.send_message(job.to_number, job.body)
        except SMSDeliveryError as exc:
            self.handle_failure(
                job.pk,
                str(exc),
                getattr(backend, "from_number", ""),
                retryable=exc.retryable,
            )
            return

        self.mark_sent(job.pk, result.provider_message_id, result.from_number)

    def handle_failure(
        self,
        job_id: int,
        error_message: str,
        from_number: str,
        *,
        retryable: bool,
    ) -> None:
        normalized_from_number = from_number if isinstance(from_number, str) else settings.SMS_FROM_NUMBER
        with transaction.atomic():
            job = OutboundSMS.objects.select_for_update().select_related("sms_message").get(pk=job_id)
            max_attempts = max(1, settings.SMS_MAX_ATTEMPTS)
            will_retry = retryable and job.attempts < max_attempts
            job.status = OutboundSMS.Status.PENDING if will_retry else OutboundSMS.Status.FAILED
            job.last_error = error_message[:200]
            job.processed_at = None if will_retry else timezone.now()
            if will_retry:
                delay_seconds = settings.SMS_RETRY_BASE_SECONDS * (2 ** max(0, job.attempts - 1))
                job.next_attempt_at = timezone.now() + timedelta(seconds=delay_seconds)
            else:
                job.next_attempt_at = timezone.now()
            job.save(update_fields=["status", "last_error", "processed_at", "next_attempt_at"])

            sms_message = job.sms_message
            sms_message.from_number = normalized_from_number or sms_message.from_number
            sms_message.delivery_status = (
                SMSMessage.DeliveryStatus.QUEUED if will_retry else SMSMessage.DeliveryStatus.FAILED
            )
            sms_message.error_message = error_message[:200]
            sms_message.save(update_fields=["from_number", "delivery_status", "error_message"])

        if will_retry:
            logger.warning(
                "Outbound SMS delivery failed; retry scheduled",
                extra={"job_id": job_id, "attempts": job.attempts, "error_message": error_message[:200]},
            )
        else:
            logger.error(
                "Outbound SMS delivery failed permanently",
                extra={"job_id": job_id, "attempts": job.attempts, "error_message": error_message[:200]},
            )

    def mark_sent(self, job_id: int, provider_message_id: str, from_number: str) -> None:
        with transaction.atomic():
            job = OutboundSMS.objects.select_for_update().select_related("sms_message").get(pk=job_id)
            job.status = OutboundSMS.Status.SENT
            job.last_error = ""
            job.next_attempt_at = timezone.now()
            job.processed_at = timezone.now()
            job.save(update_fields=["status", "last_error", "next_attempt_at", "processed_at"])

            sms_message = job.sms_message
            sms_message.from_number = from_number
            sms_message.delivery_status = SMSMessage.DeliveryStatus.SENT
            sms_message.provider_message_id = provider_message_id
            sms_message.error_message = ""
            sms_message.save(
                update_fields=["from_number", "delivery_status", "provider_message_id", "error_message"]
            )

        logger.info(
            "Outbound SMS delivered",
            extra={"job_id": job_id, "provider_message_id": provider_message_id},
        )
