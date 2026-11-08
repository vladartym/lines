from django.db import models


class Text(models.Model):
    """One text message of a VoIP.ms number, sent or received.

    VoIP.ms keeps the texts, and `phone.texts.sync` copies them here. The app reads this table, so it can ask every
    few seconds without spending the VoIP.ms API limit, and it can keep what was read.
    """

    # "sms:<id>" or "mms:<id>". The two kinds have their own id sequences.
    key = models.CharField(max_length=40, unique=True)
    did = models.CharField(max_length=20)
    contact = models.CharField(max_length=20)
    incoming = models.BooleanField()
    body = models.TextField(blank=True)
    # The links to the pictures of an MMS.
    media = models.JSONField(default=list, blank=True)
    sent_at = models.DateTimeField()
    # Only a received text can be unread.
    read = models.BooleanField(default=False)

    class Meta:
        ordering = ["sent_at", "id"]
        indexes = [models.Index(fields=["did", "contact", "sent_at"], name="phone_text_thread_idx")]


class PhoneSettings(models.Model):
    """How a call to the numbers rings. One row, pk 1, from the Settings of the app."""

    # The cell that each call forwards to, 10 digits. Asterisk rings it as a regular call, with the open apps, as one
    # call (asterisk/extensions.conf).
    forward_to = models.CharField(max_length=10, blank=True)
    forward_on = models.BooleanField(default=False)


class LineName(models.Model):
    """The name that the user gives one of the numbers, such as "Work". Only a label: VoIP.ms knows nothing of it."""

    did = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=40)


class VoicemailRead(models.Model):
    """A voicemail message that the app marked as read. VoIP.ms cannot mark it itself (phone/voicemail.py). KEY is
    the date and the caller ID of the message."""

    key = models.CharField(max_length=200, unique=True)


class VoicemailAudio(models.Model):
    """The MP3 of a voicemail message in base64, kept here so that it plays at once (phone/voicemail.py). KEY is the
    date and the caller ID of the message."""

    key = models.CharField(max_length=200, unique=True)
    data = models.TextField()


class VoicemailHidden(models.Model):
    """A voicemail message that the app deleted, but that VoIP.ms cannot delete yet (phone/voicemail.py). KEY is the
    date and the caller ID of the message."""

    key = models.CharField(max_length=200, unique=True)


class PhoneDevice(models.Model):
    """An iPhone with the app, and its APNs token for the push of a text or a call (phone/apns.py)."""

    token = models.CharField(max_length=200, unique=True)
    # A debug build has a token of the sandbox of APNs. apns.py finds this out at the first push.
    sandbox = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
