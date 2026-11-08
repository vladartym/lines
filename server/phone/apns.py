"""The push to the iPhone app through APNs, the push service of Apple. It is optional: with no APNS_KEY, no push goes.

APNs takes only HTTP/2, and a token signed with ES256 by the APNs auth key of the team (APNS_KEY in settings). A
failure here never stops the caller: it returns False.
"""
import base64
import logging
import time

import httpx
import jwt
from django.conf import settings

from .models import PhoneDevice

log = logging.getLogger(__name__)

HOSTS = {False: "https://api.push.apple.com", True: "https://api.sandbox.push.apple.com"}
_auth = {"token": "", "at": 0.0}


def _token():
    # Apple takes a new token at most every 20 minutes and refuses one older than 1 hour.
    if time.time() - _auth["at"] > 30 * 60:
        key = base64.b64decode(settings.APNS_KEY)
        claims = {"iss": settings.APNS_TEAM_ID, "iat": int(time.time())}
        _auth["token"] = jwt.encode(claims, key, algorithm="ES256", headers={"kid": settings.APNS_KEY_ID})
        _auth["at"] = time.time()
    return _auth["token"]


def _reason(response):
    try:
        return response.json().get("reason", "")
    except ValueError:
        return ""


def _send(client, device, payload):
    """Send to one phone. Return True when APNs took it. A token that is dead goes.

    A debug build has a token of the sandbox: production answers BadDeviceToken, so the other host gets one try, and
    the phone keeps the host that worked.
    """
    for sandbox in (device.sandbox, not device.sandbox):
        response = client.post(
            f"{HOSTS[sandbox]}/3/device/{device.token}",
            json=payload,
            headers={"authorization": f"bearer {_token()}", "apns-topic": settings.APNS_TOPIC, "apns-push-type": "alert"},
        )
        if response.status_code == 200:
            if device.sandbox != sandbox:
                device.sandbox = sandbox
                device.save(update_fields=["sandbox"])
            return True
        if response.status_code == 410:
            device.delete()
            return False
        if _reason(response) != "BadDeviceToken":
            # A bad key or too many pushes: the token can still be good.
            log.warning("APNs refused a push: %s %s", response.status_code, _reason(response))
            return False
    device.delete()
    return False


def notify(title, body, data=None):
    """Push an alert to each iPhone with the app. Return True when at least one phone got it."""
    if not (settings.APNS_KEY and settings.APNS_KEY_ID and settings.APNS_TEAM_ID):
        return False
    devices = list(PhoneDevice.objects.all())
    if not devices:
        return False
    payload = {"aps": {"alert": {"title": title, "body": body}, "sound": "default"}, **(data or {})}
    sent = False
    try:
        with httpx.Client(http2=True, timeout=10) as client:
            for device in devices:
                sent = _send(client, device, payload) or sent
    except Exception:
        log.exception("The push to the app failed")
    return sent
