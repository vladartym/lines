# Lines

Lines is a phone app for your [VoIP.ms](https://voip.ms) numbers, on the Mac and on the iPhone. It sends and gets
texts and pictures, makes and takes calls, and plays your voicemail. The number at the top is the line: the texts and
the calls go out from it. Tap the number to select a different line.

This repository has two parts:

- **The app** (`src/`, `src-tauri/`): Tauri 2 with React. The calls use [JsSIP](https://jssip.net) over WebRTC.
- **The server** (`server/`): a small Django API and Asterisk, in Docker Compose. You run it on your own server.

Lines is not affiliated with VoIP.ms.

## How it works

The app does not talk to VoIP.ms. VoIP.ms accepts API requests only from the IP addresses on its API page, so a
phone cannot call the VoIP.ms API. The server holds your VoIP.ms keys, copies your texts in, and runs Asterisk for
the calls.

```
app --https (API key)--> Caddy --> Django /api/v1 ------------> VoIP.ms API
app --wss ?key=... ----> Caddy --> Asterisk (SIP over WebRTC) -> VoIP.ms SIP
VoIP.ms --text hook----> Caddy --> Django /voipms/text/<token>
```

- **Texts**: the server copies the texts from VoIP.ms into its database. The app reads that copy every 8 seconds.
  VoIP.ms calls the text hook of the server when a text arrives.
- **Calls**: the app registers to Asterisk as the SIP user `lines`. A call goes out from the selected line. A call
  that comes in rings every open app.
- **Voicemail**: the server reads your VoIP.ms voicemail box, and keeps the audio of each message so that it plays at
  once.
- **Push** (optional): the server sends a push to the iPhone app for each text and each call.

## What you need

- A VoIP.ms account with one or more numbers in the US or Canada.
- A Linux server with a fixed public IP address, Docker, and a domain name, such as `phone.example.com`.
- A Mac with [Bun](https://bun.sh), [Rust](https://rustup.rs) and Xcode, to build the app.
- macOS 26 or later for the Mac app, and iOS 17 or later for the iPhone app.

## Set up VoIP.ms

Do these steps in the VoIP.ms portal.

1. Open **Main Menu > SOAP and REST/JSON API**. Enable the API, set an API password, and add the IP address of your
   server.
2. Make a voicemail box (**Voicemail > Add Voicemail**). Write down its number.
3. Make a sub-account (**Sub Accounts > Create Sub Account**) with a user name and a password. Turn off
   international calls on it.
4. For each number (**DID Numbers > Manage DIDs**):
   - Set the routing to the sub-account.
   - Set the point of presence to the server in `VOIPMS_SERVER`, such as `toronto1.voip.ms`.
   - Set the voicemail box, and set the failovers (busy, unreachable, no answer) to that voicemail box.
   - Enable SMS and MMS, and set the SMS URL callback. Enable the retry.

     ```
     https://phone.example.com/voipms/text/<PHONE_HOOK_TOKEN>?from={FROM}&to={TO}&message={MESSAGE}
     ```

## Set up the server

1. Point the DNS A record of your domain at the server.
2. Open these ports in the firewall of the server:
   - TCP 80 and 443 from all addresses: HTTPS.
   - UDP 10000-10099 from all addresses: the audio of the calls.
   - UDP 5160 from the VoIP.ms server only: SIP.
3. Copy this repository to the server, and go to the server folder: `cd server`.
4. Copy `.env.example` to `.env`, and fill in each value. Make each secret with `openssl rand -hex 32`.
5. Start the server: `docker compose up -d --build`.
6. Check that Asterisk registered to VoIP.ms:

   ```sh
   docker compose exec asterisk asterisk -rx "pjsip show registrations"
   ```

The server keeps its data in the Docker volume `data` (one SQLite file).

## Build the app

1. Install the packages: `bun install`.
2. Copy `.env.example` to `.env`. Set `VITE_SERVER_URL` to the address of your server, and `VITE_SERVER_KEY` to the
   value of `LINES_API_KEY` in `server/.env`.
3. Search the repository for `com.vladartym.lines` and `C5338FSGXJ`. Replace each with a bundle ID of your own and
   your Apple team ID.
4. Build and install:

   ```sh
   bun run install-app   # the Mac app, to ~/Applications/Lines.app
   bun run install-ios   # the iPhone on the cable or on Wi-Fi (debug build)
   bun run sim           # the iOS simulator
   ```

**Warning:** the build contains your API key. Anyone with your build can read your texts and make calls. Never share
your build. To stop a key, change `LINES_API_KEY` on the server and build the app again.

The first call asks for the microphone, and the first start asks for the contacts. On the Mac, macOS keeps these
answers for the signature of the app. An ad hoc build is a new app at each build, so set `MAC_SIGNING_IDENTITY` in
`.env` to a certificate of your keychain (`security find-identity -v -p codesigning`).

`bun run dev` shows the page in a browser at http://localhost:1420. The browser reads the server through the proxy of
`vite.config.ts`. The native parts (contacts, tab bar) are not there.

### Push to the iPhone

The push is optional. To use it:

1. Make an APNs auth key in your Apple developer account.
2. Put the key, its ID, your team ID and the bundle ID of the app in `server/.env` (`APNS_*`), and restart the server.
3. The iPhone build needs a profile with push. `scripts/xcodebuild` gives Xcode the App Store Connect API key of
   `.env` (`APPLE_API_*`), so Xcode can make the profile with no Apple account signed in.

## Calls to your numbers

- **Forwarding** (Settings > Forward to my phone): a call to your number rings your cell as a regular call, and every
  open app rings with it. With no answer in 20 seconds, VoIP.ms sends the caller to voicemail. The cell shows the
  number that the caller called, because VoIP.ms refuses a caller ID that is not one of your numbers.
- **No forwarding**: the iPhone gets a push, and Asterisk waits 20 seconds for an app to open, then rings every open
  app for 30 seconds.

## Limits

- Lines has no CallKit. With forwarding off, a call rings only while the app is open.
- The calls go to numbers in the US and Canada only, and to `4443`, the echo test of VoIP.ms.
- VoIP.ms cannot mark a voicemail message as read, and deletes only the last message of a folder. The server keeps
  the read marks, and hides a deleted message until VoIP.ms can delete it.
- On the iPhone, a call continues when the phone locks, if the call started with the app open.

## Files

| Path | What it does |
|---|---|
| `src/api.ts` | The calls to the API of the server. |
| `src/phone.ts` | The calls: JsSIP over the websocket of the server. |
| `src/store.ts` | The lists that the device keeps, so they show at once at the start. |
| `src-tauri/contacts.m` | The contacts of the Mac and the iPhone. |
| `src-tauri/mac/`, `src-tauri/gen/apple/Sources/lines/` | The native tab bar in Liquid Glass. |
| `server/phone/` | The API, the texts, the calls, the voicemail and the push. |
| `server/asterisk/` | The Asterisk configs. |
| `server/Caddyfile` | HTTPS, and the check of the key before the websocket opens. |

Run the server tests:

```sh
cd server
uv venv && uv pip install -r requirements.txt
DJANGO_DEBUG=1 .venv/bin/python manage.py test phone
```

## License

MIT. See `LICENSE`.
