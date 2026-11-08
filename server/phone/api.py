"""The JSON API that the app calls, at /api/v1/. Each request needs the API key: `Authorization: Bearer <key>`."""
import hmac
import re

from django.conf import settings
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError
from ninja.security import HttpBearer

from . import calls, texts, voicemail, voipms
from .models import LineName, PhoneDevice, PhoneSettings


def key_ok(key):
    """True when KEY is the API key of this server."""
    return bool(settings.LINES_API_KEY) and hmac.compare_digest(key.encode(), settings.LINES_API_KEY.encode())


class ApiKey(HttpBearer):
    def authenticate(self, request, token):
        return key_ok(token) or None


# No /docs and no /openapi.json: the server has one client, and the schema needs no public page.
api = NinjaAPI(title="Lines server", auth=ApiKey(), docs_url=None, openapi_url=None)


def _voipms(work, *args, **kwargs):
    """Run WORK, and turn a VoIP.ms refusal into an error that the app shows."""
    try:
        return work(*args, **kwargs)
    except voipms.Failed as error:
        raise HttpError(502, f"VoIP.ms refused: {error}") from error


class TextIn(Schema):
    # The own number to send from, and the number to send to.
    did: str
    to: str
    body: str
    # A picture as a data URL, such as data:image/jpeg;base64,... It goes as MMS.
    media: str = ""


@api.get("/texts/threads")
def text_threads(request, sync: bool = False):
    """One row for each conversation, the newest first, from the copy here.

    With sync, it first copies in the texts of the last 90 days from VoIP.ms and returns the numbers on the account
    too. The app asks so when it starts.
    """
    dids = None
    if sync:
        dids = _voipms(texts.numbers)
        _voipms(texts.sync)
    return {"dids": dids, "threads": texts.threads()}


@api.get("/texts/thread")
def text_thread(request, did: str, contact: str):
    """Every text of one conversation, the oldest first. It marks them read."""
    return {"texts": texts.thread(did, contact)}


@api.post("/texts")
def send_text(request, payload: TextIn):
    """Send one text, and return the conversation with it."""
    try:
        to = _voipms(texts.send, payload.did, payload.to, payload.body, payload.media)
    except ValueError as error:
        raise HttpError(400, str(error)) from error
    return {"contact": to, "texts": texts.thread(payload.did, to)}


@api.get("/phone")
def phone_account(request):
    """What the app signs in to Asterisk with, and the numbers it can call from.

    The websocket is /phone/ws on this host. A call goes out with one of the numbers as its caller ID: VoIP.ms
    refuses a call without one. When the VoIP.ms API fails, the app still signs in, so calls still come in.
    """
    try:
        dids = texts.numbers()
    except voipms.Failed:
        dids = []
    return {"user": settings.PHONE_SIP_USER, "password": settings.PHONE_SIP_PASSWORD, "dids": dids}


class PhoneSettingsIn(Schema):
    forward_to: str
    forward_on: bool


def _phone_settings():
    row = PhoneSettings.objects.filter(pk=1).first()
    return {"forward_to": row.forward_to if row else "", "forward_on": bool(row and row.forward_on)}


@api.get("/phone/settings")
def phone_settings(request):
    """The Settings of the app: the cell that the calls forward to, and the switch."""
    return _phone_settings()


@api.put("/phone/settings")
def set_phone_settings(request, payload: PhoneSettingsIn):
    number = texts.digits(payload.forward_to)
    if number and len(number) != 10:
        raise HttpError(400, "Give a number of 10 digits.")
    if payload.forward_on and not number:
        raise HttpError(400, "Give the number to forward to.")
    # A call forwarded to an own number comes back to Asterisk and forwards again, with no end.
    if number and number in _voipms(texts.numbers):
        raise HttpError(400, "That is one of your Lines numbers. Give your cell.")
    PhoneSettings.objects.update_or_create(pk=1, defaults={"forward_to": number, "forward_on": payload.forward_on})
    return _phone_settings()


class LineNameIn(Schema):
    did: str
    name: str


@api.get("/phone/names")
def line_names(request):
    """The names that the user gave the numbers, by number."""
    return {"names": dict(LineName.objects.values_list("did", "name"))}


@api.put("/phone/names")
def set_line_name(request, payload: LineNameIn):
    """Name one number. An empty name takes the name off."""
    did, name = texts.digits(payload.did), payload.name.strip()
    if not did:
        raise HttpError(400, "Give the number.")
    if len(name) > 40:
        raise HttpError(400, "A name takes 40 characters at most.")
    if name:
        LineName.objects.update_or_create(did=did, defaults={"name": name})
    else:
        LineName.objects.filter(did=did).delete()
    return line_names(request)


class DeviceIn(Schema):
    token: str


@api.post("/phone/devices")
def add_device(request, payload: DeviceIn):
    """The iPhone app sends its APNs token at each start, so the server can push its texts and calls to it."""
    token = payload.token.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32,200}", token):
        raise HttpError(400, "That is not an APNs token.")
    PhoneDevice.objects.get_or_create(token=token)
    return {"ok": True}


@api.get("/calls")
def recent_calls(request):
    """The calls of the last 30 days, the newest first."""
    return {"calls": _voipms(calls.recent)}


class VoicemailIn(Schema):
    folder: str
    num: int
    date: str


def _voicemail(work, *args):
    try:
        return _voipms(work, *args)
    except ValueError as error:
        raise HttpError(400, str(error)) from error


@api.get("/voicemail")
def voicemail_messages(request):
    """The messages of the voicemail box, the newest first."""
    return {"messages": _voipms(voicemail.messages)}


@api.get("/voicemail/audio")
def voicemail_audio(request, folder: str, num: int, date: str):
    """One message as a data URL of MP3."""
    return {"audio": _voicemail(voicemail.audio, folder, num, date)}


@api.put("/voicemail/read")
def voicemail_read(request, payload: VoicemailIn):
    _voicemail(voicemail.mark_read, payload.folder, payload.num, payload.date)
    return {"ok": True}


@api.delete("/voicemail")
def voicemail_delete(request, folder: str, num: int, date: str):
    """Delete one message for good."""
    _voicemail(voicemail.delete, folder, num, date)
    return {"ok": True}
