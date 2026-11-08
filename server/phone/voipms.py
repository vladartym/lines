"""The one road to the VoIP.ms API.

VoIP.ms accepts API requests only from the IP addresses on its API page, so this server must run on an address that
is on that list.
"""
import json
import urllib.parse
import urllib.request

import httpx
from django.conf import settings

API = "https://voip.ms/api/v1/rest.php"
# VoIP.ms refuses the default urllib agent.
AGENT = {"User-Agent": "lines-server/1.0"}


class Failed(Exception):
    """VoIP.ms refused the request. The message is the status that VoIP.ms gave, such as "ip_not_enabled"."""


def call(method, empty="", post=False, **params):
    """Run one API method and return the answer. A status of EMPTY reads as no rows.

    POST puts the parameters in the body: a picture in base64 is too long for a URL, which takes about 160 KB.
    """
    fields = {
        "api_username": settings.VOIPMS_USERNAME,
        "api_password": settings.VOIPMS_API_PASSWORD,
        "method": method,
        **params,
    }
    if post:
        # VoIP.ms takes a picture only as multipart/form-data: a plain form POST answers 500.
        answer = httpx.post(API, files={k: (None, str(v)) for k, v in fields.items()}, headers=AGENT, timeout=60).json()
    else:
        request = urllib.request.Request(f"{API}?{urllib.parse.urlencode(fields)}", headers=AGENT)
        with urllib.request.urlopen(request, timeout=30) as response:
            answer = json.load(response)
    if empty and answer.get("status") == empty:
        return {}
    # Anything else, such as "ip_not_enabled", must not read as "no rows".
    if answer.get("status") != "success":
        raise Failed(answer.get("status", "no status"))
    return answer
