"""The settings of the Lines server. Each value comes from the environment (.env, see .env.example)."""
import os
from pathlib import Path

env = os.environ.get

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = env("DJANGO_SECRET_KEY", "")
DEBUG = env("DJANGO_DEBUG", "") == "1"
if not SECRET_KEY and not DEBUG:
    raise RuntimeError("Set DJANGO_SECRET_KEY in .env.")

# The public name of the server, such as phone.example.com. Asterisk calls the ring hook on 127.0.0.1.
SERVER_HOST = env("SERVER_HOST", "localhost")
ALLOWED_HOSTS = [SERVER_HOST, "127.0.0.1", "localhost"]
CSRF_TRUSTED_ORIGINS = [f"https://{SERVER_HOST}"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = ["django.contrib.contenttypes", "phone"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "django.middleware.common.CommonMiddleware"]
ROOT_URLCONF = "lines_server.urls"
WSGI_APPLICATION = "lines_server.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env("DATABASE_PATH", str(BASE_DIR / "db.sqlite3")),
        # The text hook and the app can write at the same time.
        "OPTIONS": {"timeout": 20},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LOGGING = {
    "version": 1,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    # httpx writes a line for each request, such as each push.
    "loggers": {"httpx": {"level": "WARNING"}},
}

# The key of the app. The app sends it in each request, and in the URL of the websocket.
LINES_API_KEY = env("LINES_API_KEY", "")
# The secret in the URLs of the text hook (VoIP.ms) and the ring hook (Asterisk).
PHONE_HOOK_TOKEN = env("PHONE_HOOK_TOKEN", "")

# The VoIP.ms API: the email of the account, and the API password from the API page of the portal.
VOIPMS_USERNAME = env("VOIPMS_USERNAME", "")
VOIPMS_API_PASSWORD = env("VOIPMS_API_PASSWORD", "")
# The voicemail box that the numbers send an unanswered call to.
VOIPMS_MAILBOX = env("VOIPMS_MAILBOX", "")

# The SIP user that the app signs in to Asterisk as (asterisk/pjsip.conf), and its password.
PHONE_SIP_USER = "lines"
PHONE_SIP_PASSWORD = env("PHONE_SIP_PASSWORD", "")

# The push to the iPhone app (phone/apns.py). Optional: with no APNS_KEY, no push goes.
APNS_KEY = env("APNS_KEY", "")  # The .p8 file of the APNs auth key, in base64.
APNS_KEY_ID = env("APNS_KEY_ID", "")
APNS_TEAM_ID = env("APNS_TEAM_ID", "")
APNS_TOPIC = env("APNS_TOPIC", "")  # The bundle ID of the app, such as com.example.lines.
