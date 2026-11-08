"""The three URLs that are not the API: the text hook of VoIP.ms, the ring hook of Asterisk, and the websocket check."""
import hmac
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from . import calls, texts
from .api import key_ok


def _hook_allowed(token):
    """True when TOKEN is the secret that VoIP.ms and Asterisk know (PHONE_HOOK_TOKEN)."""
    secret = settings.PHONE_HOOK_TOKEN
    return bool(secret) and hmac.compare_digest(token.encode(), secret.encode())


@csrf_exempt
def incoming_text(request, token):
    """The URL callback of a VoIP.ms number: a text arrived.

    VoIP.ms sends it again every 30 minutes until the answer is "ok", so the answer is "ok" whenever the token is
    right, even when the sync failed.
    """
    if not _hook_allowed(token):
        raise Http404
    texts.incoming(request.GET.get("from", ""), request.GET.get("to", ""), request.GET.get("message", ""))
    return HttpResponse("ok", content_type="text/plain")


def incoming_call(request, token):
    """Asterisk calls this when a call comes in. The answer is the cell to forward to, 10 digits, or nothing."""
    if not _hook_allowed(token):
        raise Http404
    return HttpResponse(calls.ring(request.GET.get("from", "")), content_type="text/plain")


def phone_allow(request):
    """Caddy asks this before it opens the websocket of the app to Asterisk. 204 lets it through, 403 stops it.

    A websocket cannot carry a header, so the app puts the API key in the query: /phone/ws?key=... Caddy passes the
    URL in X-Forwarded-Uri.
    """
    query = parse_qs(urlsplit(request.headers.get("X-Forwarded-Uri", "")).query)
    return HttpResponse(status=204 if key_ok(query.get("key", [""])[0]) else 403)
