import base64
import json
from dataclasses import dataclass
from importlib import import_module
from urllib import error, parse, request

from django.conf import settings


class SMSDeliveryError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class SMSDeliveryResult:
    provider_message_id: str
    from_number: str


class ConsoleSMSBackend:
    def send_message(self, to_number: str, body: str) -> SMSDeliveryResult:
        from_number = getattr(settings, "SMS_FROM_NUMBER", "") or "console"
        print(f"SMS to {to_number} from {from_number}: {body}")
        return SMSDeliveryResult(provider_message_id="console-message", from_number=from_number)


class TwilioSMSBackend:
    api_base = "https://api.twilio.com/2010-04-01"

    def send_message(self, to_number: str, body: str) -> SMSDeliveryResult:
        account_sid = settings.SMS_TWILIO_ACCOUNT_SID
        auth_token = settings.SMS_TWILIO_AUTH_TOKEN
        from_number = settings.SMS_FROM_NUMBER
        if not account_sid or not auth_token or not from_number:
            raise SMSDeliveryError("Twilio credentials or from number are not configured.")

        url = f"{self.api_base}/Accounts/{account_sid}/Messages.json"
        payload = parse.urlencode(
            {"To": to_number, "From": from_number, "Body": body}
        ).encode("utf-8")
        auth = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
        req = request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            retryable = exc.code == 429 or 500 <= exc.code < 600
            raise SMSDeliveryError(
                f"SMS provider rejected the request: {details}",
                retryable=retryable,
            ) from exc
        except error.URLError as exc:
            raise SMSDeliveryError("SMS provider could not be reached.", retryable=True) from exc

        return SMSDeliveryResult(
            provider_message_id=data.get("sid", ""),
            from_number=data.get("from", from_number),
        )


def get_sms_backend():
    backend_path = settings.SMS_BACKEND
    module_name, class_name = backend_path.rsplit(".", 1)
    module = import_module(module_name)
    backend_class = getattr(module, class_name)
    return backend_class()
