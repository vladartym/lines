"""The voicemail of the numbers: the VoIP.ms box VOIPMS_MAILBOX, where the numbers send a call that nobody answers.

VoIP.ms keeps the messages, and the app reads them through here. A message has no lasting id: VoIP.ms numbers
the messages of a folder 0, 1, 2 ... and numbers them again after a delete. So an action names a message by its
folder, its number and its date, and finds it again before it acts. A ValueError is a refusal that the app shows.

VoIP.ms cannot write into the folders INBOX and Old of a box. So:
- It cannot mark a message as listened: markListenedVoicemailMessage moves it to Old and answers "error_moving_msg".
  The server keeps the messages that the app marked as read (VoicemailRead).
- It deletes only the last message of a folder: an older one answers "error_deleting_msg", because the delete
  numbers the newer messages again. The server hides such a message (VoicemailHidden), and _purge deletes it when it
  is the last of its folder.
Both keep a message by its date and its caller ID, which stay the same when VoIP.ms numbers the messages again.

The server keeps the MP3 of each message (VoicemailAudio): VoIP.ms takes 1 to 12 seconds for a file, and about one
time in two it sends none. The worker of compose.yml runs download() each minute, so a message plays at once.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from django.conf import settings
from django.db import connection

from . import voipms
from .calls import _background
from .models import VoicemailAudio, VoicemailHidden, VoicemailRead
from .texts import VOIPMS_TIME, _when, digits

# The call records of VoIP.ms go back about 90 days, so an older message shows no called number.
CDR_DAYS = 90
# VoIP.ms takes some seconds to settle after a delete: a delete just after it can still need the renumbering. So the
# purge waits, and tries again after each of these numbers of seconds.
PURGE_WAITS = (10, 30, 90)
MP3 = "data:audio/mpeg;base64,"


def _stored(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _number(callerid):
    """The digits of "Name" <6475550100>, Name <6475550100> or 6475550100."""
    return digits(callerid.rpartition("<")[2])


def _seconds(duration):
    hours, minutes, seconds = (int(part) for part in duration.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _key(row):
    return f"{row['date']} {row['callerid']}"


def _called(cdr, number, stored):
    """The number that the caller called: the last call from NUMBER that VoIP.ms sent to this box before STORED."""
    for row in cdr:  # the newest first
        at = _stored(row["date"])
        if (row.get("destination_type", "").startswith("IN") and f"Routing to voicemail: {settings.VOIPMS_MAILBOX}" in row.get("call_logs", "").splitlines()
                and _number(row.get("callerid", "")) == number and stored - timedelta(minutes=10) <= at <= stored):
            return digits(row.get("destination", ""))
    return ""


def messages():
    """Every message of the box, the newest first."""
    hidden = set(VoicemailHidden.objects.values_list("key", flat=True))
    rows = [row for row in voipms.call("getVoicemailMessages", "no_messages", mailbox=settings.VOIPMS_MAILBOX).get("messages", [])
            if _key(row) not in hidden]
    if not rows:
        return []
    dates = [_stored(row["date"]) for row in rows]
    span = {
        "date_from": max(min(dates).date(), datetime.now(VOIPMS_TIME).date() - timedelta(days=CDR_DAYS)).isoformat(),
        "date_to": max(dates).date().isoformat(),
    }
    # Each call to VoIP.ms takes one to eight seconds, so the calls go side by side.
    with ThreadPoolExecutor() as pool:
        # As stored, in Toronto time, the same as the dates of the messages: see texts.VOIPMS_TIME.
        cdr = pool.submit(voipms.call, "getCDR", "no_cdr", timezone=-5, answered=1, noanswer=1, busy=1, failed=1,
                          **span)
        found = [pool.submit(_transcripts, folder, span) for folder in {row["folder"] for row in rows}]
    cdr = cdr.result().get("cdr", [])
    transcripts = {f"{text.get('date')} {text.get('callerid')}": text.get("result", "")
                   for texts in found for text in texts.result()}
    read = set(VoicemailRead.objects.values_list("key", flat=True))
    out = []
    for row, stored in zip(rows, dates):
        number = _number(row.get("callerid", ""))
        out.append({
            "folder": row["folder"],
            "num": int(row["message_num"]),
            "date": row["date"],
            "at": _when(row["date"]).isoformat(),
            "number": number,
            "called": _called(cdr, number, stored),
            "seconds": _seconds(row.get("duration", "0:0:0")),
            "listened": row.get("listened") == "yes" or _key(row) in read,
            "transcript": transcripts.get(_key(row), ""),
        })
    return sorted(out, key=lambda message: message["date"], reverse=True)


def _transcripts(folder, span):
    try:
        return voipms.call("getVoicemailTranscriptions", "no_messages", mailbox=settings.VOIPMS_MAILBOX, folder=folder,
                                **span).get("messages", [])
    except voipms.Failed:
        return []  # A transcript is extra: without one, the message still plays.


def _find(folder, num, date):
    """The message of FOLDER and NUM, if it still has DATE. Else VoIP.ms numbered it again, or it is gone."""
    rows = voipms.call("getVoicemailMessages", "no_messages", mailbox=settings.VOIPMS_MAILBOX, folder=folder).get("messages", [])
    for row in rows:
        if row["folder"] == folder and int(row["message_num"]) == num and row["date"] == date:
            return row
    raise ValueError("That message changed. Open Voicemail again.")


def audio(folder, num, date):
    """The message as a data URL of MP3: from the server when it has it, which is at once, else from VoIP.ms."""
    # The key is the date and the caller ID. Two messages in the same second need the caller ID from VoIP.ms.
    stored = list(VoicemailAudio.objects.filter(key__startswith=f"{date} ").values_list("data", flat=True)[:2])
    if len(stored) == 1:
        return MP3 + stored[0]
    data = _download(_find(folder, num, date), tries=2)
    if not data:
        raise ValueError("VoIP.ms sent no audio for that message. Try again.")
    return MP3 + data


def _download(row, tries):
    """Keep the MP3 of ROW on the server, and return it in base64, or "" when VoIP.ms sent none in TRIES asks."""
    for _ in range(tries):
        # VoIP.ms sometimes answers "data": false for a message that it has. A next ask then gets it.
        data = _file(row["folder"], row["message_num"])
        if data:
            # A delete in the meantime numbers the messages again, and then the file is of another message.
            _find(row["folder"], int(row["message_num"]), row["date"])
            VoicemailAudio.objects.update_or_create(key=_key(row), defaults={"data": data})
            return data
    return ""


def download():
    """Keep the MP3 of each new message on the server, and forget the MP3 of each message that is gone. The worker
    runs it each minute (manage.py downloadvoicemail)."""
    rows = voipms.call("getVoicemailMessages", "no_messages", mailbox=settings.VOIPMS_MAILBOX).get("messages", [])
    hidden = set(VoicemailHidden.objects.values_list("key", flat=True))
    VoicemailAudio.objects.exclude(key__in=[_key(row) for row in rows]).delete()
    stored = set(VoicemailAudio.objects.values_list("key", flat=True))
    for row in rows:
        if _key(row) not in stored | hidden:
            try:
                _download(row, tries=4)
            except ValueError:
                pass  # VoIP.ms numbered the messages again: the next run gets the new numbers.


def _file(folder, num):
    """The MP3 of the message in base64, or "" when VoIP.ms sent none."""
    data = voipms.call("getVoicemailMessageFile", mailbox=settings.VOIPMS_MAILBOX, folder=folder, message_num=num,
                            format="mp3")["message"]["data"]
    return data if isinstance(data, str) else ""


def mark_read(folder, num, date):
    VoicemailRead.objects.get_or_create(key=_key(_find(folder, num, date)))


def _delete(row):
    # delMessages with the mailbox alone deletes every message of the box, so it must get the folder and the number.
    if not row["folder"] or str(row["message_num"]) == "":
        raise ValueError("That message has no folder or number.")
    voipms.call("delMessages", mailbox=settings.VOIPMS_MAILBOX, folder=row["folder"], message_num=row["message_num"])
    VoicemailHidden.objects.filter(key=_key(row)).delete()
    VoicemailRead.objects.filter(key=_key(row)).delete()


def _purge(folder, gone=""):
    """Delete the hidden messages at the end of FOLDER, the newest first, while VoIP.ms takes them.

    GONE is the key of a message that was just deleted: VoIP.ms can list it for some seconds more. The numbers of
    the others are right, because VoIP.ms deletes only the last message of a folder.
    """
    hidden = set(VoicemailHidden.objects.values_list("key", flat=True))
    if not hidden:
        return True
    rows = voipms.call("getVoicemailMessages", "no_messages", mailbox=settings.VOIPMS_MAILBOX, folder=folder).get("messages", [])
    for row in sorted(rows, key=lambda row: int(row["message_num"]), reverse=True):
        if _key(row) == gone:
            continue
        if _key(row) not in hidden:
            return True
        try:
            _delete(row)
        except voipms.Failed:
            return False  # It stays hidden, and the purge tries again later.
    return True


def _purge_later(folder, gone):
    try:
        for wait in PURGE_WAITS:
            time.sleep(wait)
            if _purge(folder, gone):
                return
    finally:
        connection.close()


def delete(folder, num, date):
    """Delete one message for good, or hide it while VoIP.ms cannot delete it."""
    row = _find(folder, num, date)
    gone = _key(row)
    try:
        _delete(row)
    except voipms.Failed as error:
        if str(error) != "error_deleting_msg":
            raise
        # shortcut: a hidden message stays at VoIP.ms, and counts toward the 100 messages of the box, until it is the
        # last of its folder. Delete the newer messages, or ask VoIP.ms to fix the box, to free the room.
        VoicemailHidden.objects.get_or_create(key=_key(row))
        gone = ""
    VoicemailAudio.objects.filter(key=_key(row)).delete()
    if VoicemailHidden.objects.exists():
        # shortcut: a restart of the server ends the purge. Then the hidden messages wait for the purge of the next delete.
        _background(_purge_later, row["folder"], gone)
