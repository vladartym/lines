import json
from unittest.mock import patch

from django.test import TestCase, override_settings

KEY = "test-key"
AUTH = {"HTTP_AUTHORIZATION": f"Bearer {KEY}"}


@override_settings(LINES_API_KEY=KEY, VOIPMS_MAILBOX="416")
class ApiTestCase(TestCase):
    """A test that calls the API with the key, as the app does."""

    def get(self, url, **extra):
        return self.client.get(url, **AUTH, **extra)

    def put(self, url, data):
        return self.client.put(url, data=json.dumps(data), content_type="application/json", **AUTH)

    def post(self, url, data):
        return self.client.post(url, data=json.dumps(data), content_type="application/json", **AUTH)

    def delete(self, url):
        return self.client.delete(url, **AUTH)


class TextsTests(ApiTestCase):
    """The texts: copied in from VoIP.ms, sent, pushed, and read with the key only."""

    SMS = {"id": "7", "date": "2026-07-01 09:30:00", "type": "1", "did": "4165550123",
           "contact": "6475550100", "message": "hi"}

    def _voipms(self, answers):
        """Answer each VoIP.ms method from ANSWERS, and keep every call in self.calls."""
        self.calls = []

        def call(method, empty="", **params):
            self.calls.append((method, params))
            return answers.get(method, {})
        return patch("phone.voipms.call", side_effect=call)

    def test_the_texts_need_the_key(self):
        self.assertEqual(self.client.get("/api/v1/texts/threads").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/texts/threads", HTTP_AUTHORIZATION="Bearer wrong").status_code, 401)
        with self.settings(LINES_API_KEY=""):
            self.assertEqual(self.client.get("/api/v1/texts/threads", HTTP_AUTHORIZATION="Bearer ").status_code, 401)

    def test_sync_copies_each_text_once_in_utc(self):
        from phone import texts
        from phone.models import Text
        answers = {"getSMS": {"sms": [self.SMS]},
                   "getMMS": {"sms": [{**self.SMS, "id": "7", "type": "0", "message": "",
                                       "media": ["https://voip.ms/m/a.jpg"]}]}}
        with self._voipms(answers):
            self.assertEqual(len(texts.sync()), 2)
            self.assertEqual(texts.sync(), [])
        sms = Text.objects.get(key="sms:7")
        # 09:30 in Toronto in July is 13:30 UTC: VoIP.ms is asked with -5, as stored.
        self.assertEqual(sms.sent_at.isoformat(), "2026-07-01T13:30:00+00:00")
        self.assertEqual(self.calls[0][1]["timezone"], -5)
        self.assertTrue(sms.incoming)
        self.assertFalse(sms.read)
        mms = Text.objects.get(key="mms:7")
        self.assertEqual(mms.media, ["https://voip.ms/m/a.jpg"])
        self.assertTrue(mms.read)

    def test_a_short_text_goes_as_sms_and_a_long_one_as_mms(self):
        from phone import texts
        from phone.models import Text
        answers = {"getDIDsInfo": {"dids": [{"did": "4165550123"}]},
                   "sendSMS": {"sms": "11"}, "sendMMS": {"mms": "12"}}
        with self._voipms(answers):
            self.assertEqual(texts.send("4165550123", "+1 (647) 555-0100", " hi "), "6475550100")
            texts.send("4165550123", "6475550100", "x" * 161)
        self.assertEqual(self.calls[1], ("sendSMS", {"did": "4165550123", "dst": "6475550100", "message": "hi"}))
        self.assertEqual(self.calls[3][0], "sendMMS")
        self.assertEqual(sorted(Text.objects.values_list("key", flat=True)), ["mms:12", "sms:11"])
        # The sync later finds the same ids and adds nothing.
        with self._voipms({"getSMS": {"sms": [{**self.SMS, "id": "11", "type": "0"}]}}):
            self.assertEqual(texts.sync(), [])

    def test_a_picture_goes_as_mms_in_a_post_and_gets_its_link_from_the_sync(self):
        from phone import texts
        from phone.models import Text
        picture = "data:image/jpeg;base64," + "A" * 300_000
        mms = {**self.SMS, "id": "13", "type": "0", "message": "", "media": ["https://voip.ms/media/13.jpg"]}
        answers = {"getDIDsInfo": {"dids": [{"did": "4165550123"}]}, "sendMMS": {"mms": "13"}, "getMMS": {"mms": [mms]}}
        with self._voipms(answers):
            texts.send("4165550123", "6475550100", "", picture)
            with self.assertRaises(ValueError):
                texts.send("4165550123", "6475550100", "", "javascript:alert(1)")
        method, params = self.calls[1]
        self.assertEqual((method, params["post"], params["media1"], params["message"]), ("sendMMS", True, picture, ""))
        self.assertEqual(Text.objects.get(key="mms:13").media, ["https://voip.ms/media/13.jpg"])

    def test_a_post_to_voipms_is_multipart(self):
        from phone import voipms
        with patch("phone.voipms.httpx.post") as post:
            post.return_value.json.return_value = {"status": "success", "mms": 5}
            self.assertEqual(voipms.call("sendMMS", post=True, media1="data:image/jpeg;base64,AA")["mms"], 5)
        files = post.call_args.kwargs["files"]
        self.assertEqual((files["method"], files["media1"]), ((None, "sendMMS"), (None, "data:image/jpeg;base64,AA")))

    def test_send_refuses_a_number_that_is_not_on_the_account(self):
        from phone import texts
        with self._voipms({"getDIDsInfo": {"dids": [{"did": "4165550123"}]}}):
            with self.assertRaises(ValueError):
                texts.send("9055550100", "6475550100", "hi")
        self.assertEqual([c[0] for c in self.calls], ["getDIDsInfo"])

    def test_the_hook_needs_the_token_and_answers_ok(self):
        with self.settings(PHONE_HOOK_TOKEN="s3cret"):
            response = self.client.get("/voipms/text/wrong?from=6475550100")
            self.assertEqual(response.status_code, 404)
            with self._voipms({"getSMS": {"sms": [self.SMS]}}), patch("phone.apns.notify") as push:
                response = self.client.get("/voipms/text/s3cret?from=6475550100&to=4165550123&message=hi")
        self.assertEqual(response.content, b"ok")
        push.assert_called_once()
        self.assertEqual(push.call_args[0], ("(647) 555-0100", "hi", {"did": "4165550123", "contact": "6475550100"}))
        self.assertEqual(self.calls[0][1]["contact"], "6475550100")

    def test_the_hook_pushes_even_when_voipms_fails(self):
        from phone import voipms
        with self.settings(PHONE_HOOK_TOKEN="s3cret"), \
                patch("phone.voipms.call", side_effect=voipms.Failed("ip_not_enabled")), \
                patch("phone.apns.notify") as push:
            response = self.client.get("/voipms/text/s3cret?from=16475550100&to=4165550123&message=hi")
        self.assertEqual(response.content, b"ok")
        self.assertEqual(push.call_args[0][:2], ("(647) 555-0100", "hi"))

    def test_threads_show_the_last_text_and_reading_marks_it_read(self):
        from phone import texts
        with self._voipms({"getSMS": {"sms": [self.SMS, {**self.SMS, "id": "8", "date": "2026-07-01 10:00:00",
                                                       "message": "later"}]}}):
            texts.sync()
        response = self.get("/api/v1/texts/threads")
        [thread] = response.json()["threads"]
        self.assertEqual((thread["body"], thread["unread"]), ("later", 2))
        response = self.get("/api/v1/texts/thread?did=4165550123&contact=6475550100")
        self.assertEqual([t["body"] for t in response.json()["texts"]], ["hi", "later"])
        self.assertEqual(texts.threads()[0]["unread"], 0)

    def test_a_refusal_shows_as_an_error(self):
        from phone import voipms
        with patch("phone.voipms.call", side_effect=voipms.Failed("ip_not_enabled")):
            response = self.get("/api/v1/texts/threads?sync=true")
        self.assertEqual(response.status_code, 502)
        self.assertIn("ip_not_enabled", response.json()["detail"])


class CallsTests(ApiTestCase):
    """The calls: who may open the phone websocket, the push of a call, and the recent calls."""

    def test_the_api_key_in_the_websocket_url_opens_the_phone(self):
        def allow(uri):
            return self.client.get("/phone/allow", HTTP_X_FORWARDED_URI=uri).status_code

        self.assertEqual(allow(f"/phone/ws?key={KEY}"), 204)
        self.assertEqual(allow("/phone/ws?key=wrong"), 403)
        self.assertEqual(allow("/phone/ws?key="), 403)
        self.assertEqual(allow("/phone/ws"), 403)

    def test_the_sip_password_needs_the_key(self):
        with self.settings(PHONE_SIP_PASSWORD="pw"), \
                patch("phone.voipms.call", return_value={"dids": [{"did": "4165550123"}]}):
            response = self.get("/api/v1/phone")
            self.assertEqual(response.json(), {"user": "lines", "password": "pw", "dids": ["4165550123"]})
            self.assertEqual(self.client.get("/api/v1/phone").status_code, 401)

    def test_a_ringing_call_is_pushed(self):
        with self.settings(PHONE_HOOK_TOKEN="s3cret"), patch("phone.apns.notify") as push, \
                patch("phone.calls._background", lambda work, *args: work(*args)):
            self.assertEqual(self.client.get("/voipms/ring/nope?from=1").status_code, 404)
            response = self.client.get("/voipms/ring/s3cret?from=16475550100")
        # No forwarding: Asterisk gets nothing to dial, and rings the apps.
        self.assertEqual(response.content, b"")
        self.assertEqual(push.call_args[0], ("(647) 555-0100", "Incoming call"))

    def test_a_forwarded_call_gives_asterisk_the_cell_and_pushes_nothing(self):
        from phone.models import PhoneSettings

        PhoneSettings.objects.create(pk=1, forward_to="6475550199", forward_on=True)
        with self.settings(PHONE_HOOK_TOKEN="s3cret"), patch("phone.calls._background") as background:
            response = self.client.get("/voipms/ring/s3cret?from=16475550100")
        self.assertEqual(response.content, b"6475550199")
        background.assert_not_called()
        PhoneSettings.objects.filter(pk=1).update(forward_on=False)
        with self.settings(PHONE_HOOK_TOKEN="s3cret"), patch("phone.calls._background"):
            response = self.client.get("/voipms/ring/s3cret?from=16475550100")
        self.assertEqual(response.content, b"")

    def test_the_settings_refuse_an_own_number_and_a_short_one(self):
        own = {"dids": [{"did": "4165550123"}]}
        with patch("phone.voipms.call", return_value=own):
            def put(number, on=True):
                return self.put("/api/v1/phone/settings", {"forward_to": number, "forward_on": on})
            self.assertEqual(put("4165550123").status_code, 400)
            self.assertEqual(put("555").status_code, 400)
            self.assertEqual(put("", True).status_code, 400)
            response = put("+1 (647) 555-0199")
        self.assertEqual(response.json(), {"forward_to": "6475550199", "forward_on": True})
        self.assertEqual(self.get("/api/v1/phone/settings").json()["forward_to"], "6475550199")

    def test_a_number_gets_a_name_and_an_empty_name_takes_it_off(self):
        def put(did, name):
            return self.put("/api/v1/phone/names", {"did": did, "name": name})
        self.assertEqual(put("+1 (416) 555-0123", "  Work ").json(), {"names": {"4165550123": "Work"}})
        self.assertEqual(put("4165550123", "x" * 41).status_code, 400)
        self.assertEqual(put("4165550123", "").json(), {"names": {}})
        self.assertEqual(self.get("/api/v1/phone/names").json(), {"names": {}})

    def test_a_phone_registers_its_push_token_once(self):
        from phone.models import PhoneDevice

        def post(token):
            return self.post("/api/v1/phone/devices", {"token": token})
        self.assertEqual(post("not a token").status_code, 400)
        self.assertEqual(post("AB" * 32).status_code, 200)
        self.assertEqual(post("ab" * 32).status_code, 200)
        self.assertEqual(list(PhoneDevice.objects.values_list("token", flat=True)), ["ab" * 32])


class ApnsTests(ApiTestCase):
    """The push to the iPhone app: the sandbox of a debug build, a dead token, and no key at all."""

    def setUp(self):
        import base64

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        from phone.models import PhoneDevice

        pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        self.keys = {"APNS_KEY": base64.b64encode(pem).decode(), "APNS_KEY_ID": "KEY1", "APNS_TEAM_ID": "TEAM1"}
        self.device = PhoneDevice.objects.create(token="ab" * 32)
        self.hits = []

    def _apns(self, answers):
        """APNs answers each host with ANSWERS[host] (status, reason)."""
        import httpx

        def handler(request):
            self.hits.append(request.url.host)
            status, reason = answers[request.url.host]
            return httpx.Response(status, json={"reason": reason} if reason else None)

        real = httpx.Client
        return patch("phone.apns.httpx.Client", lambda **kw: real(transport=httpx.MockTransport(handler)))

    def test_a_debug_build_gets_the_push_from_the_sandbox(self):
        from phone import apns

        answers = {"api.push.apple.com": (400, "BadDeviceToken"), "api.sandbox.push.apple.com": (200, "")}
        with self.settings(**self.keys), self._apns(answers):
            self.assertTrue(apns.notify("(647) 555-0100", "hi"))
            self.device.refresh_from_db()
            self.assertTrue(self.device.sandbox)
            # The next push goes to the sandbox first.
            self.assertTrue(apns.notify("(647) 555-0100", "again"))
        self.assertEqual(self.hits, ["api.push.apple.com", "api.sandbox.push.apple.com", "api.sandbox.push.apple.com"])

    def test_a_dead_token_goes(self):
        from phone import apns
        from phone.models import PhoneDevice

        with self.settings(**self.keys), self._apns({"api.push.apple.com": (410, "Unregistered")}):
            self.assertFalse(apns.notify("x", "y"))
        self.assertFalse(PhoneDevice.objects.exists())

    def test_a_refused_key_keeps_the_token_and_with_no_key_nothing_goes(self):
        from phone import apns
        from phone.models import PhoneDevice

        with self.settings(**self.keys), self._apns({"api.push.apple.com": (403, "InvalidProviderToken")}):
            self.assertFalse(apns.notify("x", "y"))
        self.assertTrue(PhoneDevice.objects.exists())
        with self.settings(APNS_KEY=""), self._apns({}):
            self.assertFalse(apns.notify("x", "y"))
        self.assertEqual(self.hits, ["api.push.apple.com"])

    def test_a_text_pushes_even_when_voipms_fails(self):
        from phone import voipms

        with self.settings(PHONE_HOOK_TOKEN="s3cret"), patch("phone.apns.notify", return_value=True) as notify, \
                patch("phone.voipms.call", side_effect=voipms.Failed("x")):
            response = self.client.get("/voipms/text/s3cret?from=6475550100&to=4165550123&message=hi")
        self.assertEqual(response.content, b"ok")
        self.assertEqual(notify.call_args[0][:2], ("(647) 555-0100", "hi"))

    def test_recent_calls_name_the_other_number(self):
        from phone import calls
        cdr = [
            {"date": "2026-07-01 09:30:00", "callerid": '"Jo" <6475550100>', "destination": "4165550123",
             "disposition": "NO ANSWER", "seconds": "0", "uniqueid": "a", "destination_type": "IN:CAN"},
            {"date": "2026-07-01 10:00:00", "callerid": "4165550123", "destination": "16475550100",
             "disposition": "ANSWERED", "seconds": "61", "uniqueid": "b", "destination_type": "OUT:CAN"},
        ]
        answers = {"getCDR": {"cdr": cdr}}
        sent = []

        def call(method, empty="", **params):
            sent.append((method, params))
            return answers[method]
        with patch("phone.voipms.call", side_effect=call):
            out, missed = calls.recent()
        self.assertEqual(sent[0][1]["timezone"], -5)
        self.assertEqual((out["number"], out["incoming"], out["answered"], out["seconds"]), ("6475550100", False, True, 61))
        self.assertEqual((missed["number"], missed["incoming"], missed["answered"]), ("6475550100", True, False))
        self.assertEqual(missed["at"], "2026-07-01T13:30:00+00:00")


class VoicemailTests(ApiTestCase):
    """The voicemail box (416 in these tests): the list with the called number, and the actions, which find the message again first."""

    def voipms(self, answers):
        sent = []

        def call(method, empty="", **params):
            sent.append((method, params))
            return answers[method]
        return sent, patch("phone.voipms.call", side_effect=call)

    def test_the_list_names_the_called_number_the_transcript_and_the_read_messages(self):
        from phone import voicemail
        from phone.models import VoicemailRead

        box = [
            {"folder": "INBOX", "message_num": "0", "date": "2026-10-31 14:46:09", "callerid": '"Jo" <6475550100>',
             "duration": "00:01:05", "listened": "no"},
            {"folder": "INBOX", "message_num": "1", "date": "2026-10-31 16:00:30", "callerid": "4165550199",
             "duration": "00:00:07", "listened": "no"},
        ]
        cdr = [  # the newest first, as VoIP.ms gives them
            {"date": "2026-10-31 16:00:00", "callerid": "4165550199", "destination": "4165550123",
             "destination_type": "IN:CAN", "call_logs": "Routing to SIP URI: x\nRouting to voicemail: 416"},
            # Another box, whose number starts with 416: not this box.
            {"date": "2026-10-31 14:46:00", "callerid": '"Jo" <6475550100>', "destination": "4169999999",
             "destination_type": "IN:CAN", "call_logs": "Routing to voicemail: 4160"},
            {"date": "2026-10-31 14:45:34", "callerid": '"Jo" <6475550100>', "destination": "4165550145",
             "destination_type": "IN:CAN", "call_logs": "Routing to sub-account: x\nRouting to voicemail: 416"},
        ]
        transcripts = [{"date": "2026-10-31 16:00:30", "callerid": "4165550199", "folder": "INBOX", "result": "Call me."}]
        VoicemailRead.objects.create(key='2026-10-31 14:46:09 "Jo" <6475550100>')
        sent, patched = self.voipms({"getVoicemailMessages": {"messages": box}, "getCDR": {"cdr": cdr},
                                     "getVoicemailTranscriptions": {"messages": transcripts}})
        with patched:
            newest, jo = voicemail.messages()
        self.assertEqual(dict(sent)["getCDR"]["timezone"], -5)
        self.assertEqual((newest["number"], newest["called"], newest["seconds"], newest["listened"], newest["transcript"]),
                         ("4165550199", "4165550123", 7, False, "Call me."))
        self.assertEqual((jo["number"], jo["called"], jo["seconds"], jo["listened"], jo["transcript"]),
                         ("6475550100", "4165550145", 65, True, ""))

    def test_the_audio_of_a_message_that_voipms_numbered_again_is_refused(self):
        box = [{"folder": "INBOX", "message_num": "0", "date": "2026-10-31 14:46:09", "callerid": "4165550199"}]
        _, patched = self.voipms({"getVoicemailMessages": {"messages": box},
                                  "getVoicemailMessageFile": {"message": {"data": "QUJD"}}})
        url = "/api/v1/voicemail/audio?folder=INBOX&num=0&date={}"
        with patched:
            stale = self.get(url.format("2026-10-30+10:00:00"))
            ok = self.get(url.format("2026-10-31+14:46:09"))
        self.assertEqual(stale.status_code, 400)
        self.assertEqual(ok.json(), {"audio": "data:audio/mpeg;base64,QUJD"})

    def test_the_audio_comes_from_voipms_once_and_then_from_the_server(self):
        from phone.models import VoicemailAudio

        box = [{"folder": "INBOX", "message_num": "0", "date": "2026-10-31 14:46:09", "callerid": "4165550199"}]
        files = []

        def call(method, empty="", **params):
            if method == "getVoicemailMessages":
                return {"messages": box}
            return {"message": {"data": files.pop(0)}}  # IndexError when VoIP.ms is asked with nothing to send
        url = "/api/v1/voicemail/audio?folder=INBOX&num=0&date=2026-10-31+14:46:09"
        with patch("phone.voipms.call", side_effect=call):
            files[:] = [False, False]  # VoIP.ms sometimes sends "data": false
            none = self.get(url)
            files[:] = [False, "QUJD"]
            again = self.get(url)
            files[:] = []
            kept = self.get(url)
        self.assertEqual(none.status_code, 400)
        self.assertEqual(again.json(), {"audio": "data:audio/mpeg;base64,QUJD"})
        self.assertEqual(kept.json(), {"audio": "data:audio/mpeg;base64,QUJD"})
        self.assertEqual(list(VoicemailAudio.objects.values_list("key", flat=True)), ["2026-10-31 14:46:09 4165550199"])

    def test_the_download_keeps_each_new_message_and_forgets_the_gone_ones(self):
        from phone import voicemail
        from phone.models import VoicemailAudio, VoicemailHidden

        box = [
            {"folder": "INBOX", "message_num": "0", "date": "2026-10-31 14:46:09", "callerid": "4165550199"},
            {"folder": "INBOX", "message_num": "1", "date": "2026-10-31 15:00:00", "callerid": "4165550188"},
            {"folder": "INBOX", "message_num": "2", "date": "2026-10-31 16:00:00", "callerid": "4165550177"},
        ]
        VoicemailAudio.objects.create(key="2026-10-31 14:46:09 4165550199", data="T0xE")
        VoicemailAudio.objects.create(key="2026-10-30 09:00:00 4165550100", data="R09ORQ==")  # deleted at VoIP.ms
        VoicemailHidden.objects.create(key="2026-10-31 16:00:00 4165550177")
        files = [False, False, "TkVX"]
        asked = []

        def call(method, empty="", **params):
            if method == "getVoicemailMessages":
                return {"messages": box}
            asked.append(params["message_num"])
            return {"message": {"data": files.pop(0)}}
        with patch("phone.voipms.call", side_effect=call):
            voicemail.download()
        self.assertEqual(asked, ["1", "1", "1"])  # only the new message, asked again while VoIP.ms sent none
        self.assertEqual(dict(VoicemailAudio.objects.values_list("key", "data")), {
            "2026-10-31 14:46:09 4165550199": "T0xE",
            "2026-10-31 15:00:00 4165550188": "TkVX",
        })

    def test_a_delete_that_voipms_refuses_hides_the_message_until_it_is_the_last(self):
        from phone import voicemail, voipms
        from phone.models import VoicemailHidden

        box = [{"folder": "INBOX", "date": "2026-10-31 14:46:09", "callerid": "4165550199", "duration": "00:00:05"},
               {"folder": "INBOX", "date": "2026-10-31 15:00:00", "callerid": "4165550188", "duration": "00:00:05"}]
        sent = []
        stale = []

        def call(method, empty="", **params):
            """Box 416: it deletes only the last message of a folder, and numbers the messages from 0. Just after a
            delete, it lists the deleted message one more time, and refuses the next delete once."""
            sent.append((method, params))
            if method == "delMessages":
                if int(params["message_num"]) != len(box) - 1 or "settling" in stale:
                    stale[:] = [row for row in stale if row != "settling"]
                    raise voipms.Failed("error_deleting_msg")
                stale.extend([box.pop(), "settling"])
                return {"status": "success"}
            if method == "getVoicemailMessages":
                listed = box + [row for row in stale if row != "settling"]
                stale[:] = [row for row in stale if row == "settling"]
                return {"messages": [dict(row, message_num=str(i)) for i, row in enumerate(listed)]}
            return {}
        url = "/api/v1/voicemail?folder=INBOX&num={}&date={}"
        # The purge runs here and at once, in place of a thread that waits.
        with patch("phone.voipms.call", side_effect=call), patch("phone.voicemail.time.sleep") as sleep, \
                patch("phone.voicemail.connection"), \
                patch("phone.voicemail._background", side_effect=lambda work, *args: work(*args)):
            # A number that VoIP.ms gave to another message deletes nothing.
            self.assertEqual(self.delete(url.format(1, "2026-10-31%2014:46:09")).status_code, 400)
            self.assertNotIn("delMessages", [method for method, _ in sent])
            # The older message: VoIP.ms refuses, so it hides.
            self.assertEqual(self.delete(url.format(0, "2026-10-31%2014:46:09")).json(), {"ok": True})
            self.assertEqual([m["date"] for m in voicemail.messages()], ["2026-10-31 15:00:00"])
            self.assertEqual(len(box), 2)
            # The last message goes for good. The hidden one is then the last, and goes too.
            self.delete(url.format(1, "2026-10-31%2015:00:00"))
        self.assertEqual(box, [])
        self.assertFalse(VoicemailHidden.objects.exists())
        self.assertGreaterEqual(sleep.call_count, 2)  # The first try came too soon, so the purge tried again.
        # delMessages with the mailbox alone empties the box.
        self.assertTrue(all(p["folder"] == "INBOX" and p["message_num"] != "" for m, p in sent if m == "delMessages"))


