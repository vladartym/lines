from django.urls import path

from phone import views
from phone.api import api

urlpatterns = [
    path("api/v1/", api.urls),
    # VoIP.ms calls this when a text arrives. The secret in the path is the whole check, because VoIP.ms cannot sign in.
    path("voipms/text/<str:token>", views.incoming_text),
    # Asterisk calls this when a call comes in, with the same secret.
    path("voipms/ring/<str:token>", views.incoming_call),
    # Caddy asks this before it opens the websocket of the app (Caddyfile).
    path("phone/allow", views.phone_allow),
]
