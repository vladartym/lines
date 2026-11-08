"""The calls of the VoIP.ms numbers: the recent calls, the forwarding, and the push when one comes in.

The calls themselves go through Asterisk (server/asterisk/). The app talks SIP
to it over a websocket; Django only checks who may open that websocket
(`views.phone_allow`) and pushes a call that comes in.
"""
import threading
from datetime import datetime, timedelta

from django.db import connection

from . import apns, voipms
from .models import PhoneSettings
from .texts import VOIPMS_TIME, _when, digits, pretty


def forward_number():
    """The cell that the calls forward to, 10 digits, or "" when forwarding is off."""
    row = PhoneSettings.objects.filter(pk=1).first()
    return row.forward_to if row and row.forward_on and len(row.forward_to) == 10 else ""


def _background(work, *args):
    threading.Thread(target=work, args=args, daemon=True).start()


def _push_call(sender):
    try:
        apns.notify(pretty(sender) if sender else "No Caller ID", "Incoming call")
    finally:
        connection.close()


def ring(sender):
    """Asterisk asks this when a call comes in. Return the cell to forward the call to, or "".

    With forwarding on, the cell rings as a regular call, so no push goes. Without it, the iPhone gets a push, so an
    app that is closed can open and take the call: Asterisk waits 20 seconds for it. The push goes in
    the background, because Asterisk waits for this answer before it rings anything.
    """
    forward = forward_number()
    if not forward:
        _background(_push_call, digits(sender))
    return forward


def _seconds(row):
    try:
        return int(row.get("seconds") or 0)
    except ValueError:
        return 0


def recent(days=30):
    """The calls of the last DAYS days, the newest first, from the call records of VoIP.ms."""
    today = datetime.now(VOIPMS_TIME).date()
    rows = voipms.call(
        "getCDR", "no_cdr",
        date_from=(today - timedelta(days=days)).isoformat(),
        date_to=today.isoformat(),
        # As stored, in Toronto time: see texts.VOIPMS_TIME.
        timezone=-5,
        answered=1, noanswer=1, busy=1, failed=1,
    ).get("cdr", [])
    calls = []
    for row in rows:
        callee = digits(row.get("destination", ""))
        # "IN:CAN", "OUT:CAN", "OUT:OTHER". The number alone cannot tell: a
        # call to an own number has a row each way with the same numbers.
        incoming = row.get("destination_type", "").startswith("IN")
        calls.append({
            "id": row.get("uniqueid") or f"{row['date']}-{callee}",
            "at": _when(row["date"]).isoformat(),
            "incoming": incoming,
            # The other number. callerid can carry a name: "Name" <6475550100>.
            "number": digits(row.get("callerid", "").rpartition("<")[2]) if incoming else callee,
            "answered": row.get("disposition") == "ANSWERED",
            "seconds": _seconds(row),
        })
    return sorted(calls, key=lambda call: call["at"], reverse=True)
