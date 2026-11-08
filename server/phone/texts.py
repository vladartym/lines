"""The texts of the VoIP.ms numbers: copy them in, send them, and push a new one.

VoIP.ms keeps every text. `sync` copies a span of days into `phone.Text`, and the
app reads that table. VoIP.ms calls `incoming` (through the URL callback of
the number) when a text arrives, which syncs and pushes it to the iPhone.
"""
from datetime import datetime, timedelta, timezone

from zoneinfo import ZoneInfo

from django.db.models import Count, Max, Q
from django.utils import timezone as django_time

from . import apns, voipms
from .models import Text

# VoIP.ms writes its dates in Toronto time, and its `timezone` parameter
# converts as if Toronto never moved its clocks: in summer, 0 gives a time one
# hour late. -5 gives the dates as stored, and zoneinfo converts them right.
VOIPMS_TIME = ZoneInfo("America/Toronto")
# sendSMS takes 160 characters. A longer text goes as one MMS, which takes 1600
# and costs less than the SMS parts it replaces.
SMS_MAX = 160
MMS_MAX = 1600
# A picture comes as a data URL. VoIP.ms takes about 1.2 MB for one, which is about 1.7 million characters of base64.
PICTURE_MAX = 1_700_000


def digits(number):
    """The 10 digits of a North American number, or the digits as given, such as a short code."""
    number = "".join(c for c in str(number) if c.isdigit())
    return number[1:] if len(number) == 11 and number.startswith("1") else number


def pretty(number):
    """(555) 555-0100, the way a phone shows a number."""
    return f"({number[:3]}) {number[3:6]}-{number[6:]}" if len(number) == 10 else number


def numbers():
    """The phone numbers on the account."""
    return [d["did"] for d in voipms.call("getDIDsInfo", "no_did").get("dids", [])]


def _when(value):
    stored = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return stored.replace(tzinfo=VOIPMS_TIME).astimezone(timezone.utc)


def sync(days=90, contact=""):
    """Copy in the texts of the last DAYS days. Return the texts that were new."""
    today = datetime.now(VOIPMS_TIME).date()
    span = {
        "from": (today - timedelta(days=days)).isoformat(),
        "to": (today + timedelta(days=1)).isoformat(),
        "timezone": -5,
        "limit": 10000,
    }
    if contact:
        span["contact"] = contact
    rows = [("sms", m) for m in voipms.call("getSMS", "no_sms", **span).get("sms", [])]
    # Without all_messages, getMMS gives the MMS only, so no text comes in twice.
    mms = voipms.call("getMMS", "no_sms", **span)
    rows += [("mms", m) for m in mms.get("mms") or mms.get("sms") or []]

    known = set(Text.objects.filter(key__in=[f"{kind}:{m['id']}" for kind, m in rows])
                .values_list("key", flat=True))
    new = [
        Text(
            key=f"{kind}:{m['id']}",
            did=m["did"],
            contact=digits(m["contact"]),
            incoming=str(m["type"]) == "1",
            body=m.get("message") or "",
            media=[url for url in m.get("media") or [] if url],
            sent_at=_when(m["date"]),
            # A text sent from somewhere else was read when it was written.
            read=str(m["type"]) != "1",
        )
        for kind, m in rows
        if f"{kind}:{m['id']}" not in known
    ]
    # Two syncs can run at once: the app and the URL callback.
    Text.objects.bulk_create(new, ignore_conflicts=True)
    # A picture sent from here was copied in before VoIP.ms gave the link of its picture.
    for kind, m in rows:
        media = [url for url in m.get("media") or [] if url]
        if media and f"{kind}:{m['id']}" in known:
            Text.objects.filter(key=f"{kind}:{m['id']}", media=[]).update(media=media)
    return new


def send(did, to, body, media=""):
    """Send BODY from DID to TO, with the picture MEDIA (a data URL) when there is one, and copy it in at once.
    Raise ValueError on bad input."""
    to, body = digits(to), body.strip()
    if not to or not (body or media):
        raise ValueError("Give a number and a message.")
    if len(body) > MMS_MAX:
        raise ValueError(f"A text takes {MMS_MAX} characters at most.")
    if media and (not media.startswith("data:image/") or len(media) > PICTURE_MAX):
        raise ValueError("Send a picture of 1.2 MB at most.")
    if did not in numbers():
        raise ValueError("That number is not on the account.")
    kind = "sms" if len(body) <= SMS_MAX and not media else "mms"
    if media:
        answer = voipms.call("sendMMS", post=True, did=did, dst=to, message=body, media1=media)
    else:
        answer = voipms.call("sendSMS" if kind == "sms" else "sendMMS", did=did, dst=to, message=body)
    sent = answer.get("sms") or answer.get("mms")
    if sent:
        # The same key as the sync gives it, so the sync does not add it twice.
        Text.objects.get_or_create(key=f"{kind}:{sent}", defaults={
            "did": did, "contact": to, "incoming": False, "body": body,
            "sent_at": django_time.now(), "read": True,
        })
        if media:
            # VoIP.ms gives the link of the picture in a sync, so the copy gets it now and not at the next sync.
            try:
                sync(days=1, contact=to)
            except voipms.Failed:
                pass
    return to


def incoming(sender, did, message):
    """What the URL callback runs: copy the new texts in and push each one to the phone."""
    sender = digits(sender)
    try:
        new = [t for t in sync(days=2, contact=sender) if t.incoming]
    except Exception:
        # VoIP.ms refused or timed out. The push still goes out, from the
        # callback itself, and the next sync copies the text in.
        new = [Text(did=digits(did), contact=sender, incoming=True, body=message)]
    for text in new:
        apns.notify(pretty(text.contact), text.body or "Picture", {"did": text.did, "contact": text.contact})
    return new


def threads():
    """One row for each pair of own number and other number, the newest first."""
    pairs = list(
        Text.objects.values("did", "contact")
        .annotate(at=Max("sent_at"), unread=Count("id", filter=Q(incoming=True, read=False)))
    )
    if not pairs:
        return []
    match = Q()
    for pair in pairs:
        match |= Q(did=pair["did"], contact=pair["contact"], sent_at=pair["at"])
    last = {(t.did, t.contact): t for t in Text.objects.filter(match).order_by("id")}
    rows = []
    for pair in pairs:
        text = last[(pair["did"], pair["contact"])]
        rows.append({
            "did": text.did,
            "contact": text.contact,
            "body": text.body,
            "media": len(text.media),
            "incoming": text.incoming,
            "at": text.sent_at.isoformat(),
            "unread": pair["unread"],
        })
    return sorted(rows, key=lambda row: row["at"], reverse=True)


def thread(did, contact):
    """Every text between DID and CONTACT, the oldest first. Reading them marks them read."""
    texts = Text.objects.filter(did=did, contact=contact)
    texts.filter(incoming=True, read=False).update(read=True)
    return [
        {"id": t.id, "incoming": t.incoming, "body": t.body, "media": t.media, "at": t.sent_at.isoformat()}
        for t in texts
    ]
