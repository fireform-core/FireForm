# Real-Time Live Transcription & Translation (WhisperLive)

FireForm supports real-time, low-latency live audio transcription and translation during microphone recording via a WebSocket proxy endpoint backed by [Collabora WhisperLive](https://github.com/collabora/WhisperLive).

---

## Architecture Overview

```
Browser / Client (Mic PCM 16kHz mono int16)
         │
         │  WebSocket (/api/v1/live-transcribe)
         ▼
FireForm API Proxy (app/api/routes/live_transcribe.py)
         │
         │  WebSocket (ws://whisperlive:9090)
         ▼
WhisperLive Server (ghcr.io/collabora/whisperlive-cpu:latest)
```

- **Separation of Concerns:** The existing batch transcription endpoint (`POST /api/v1/forms/transcribe` via `app/services/whisper.py` using `onerahmet/openai-whisper-asr-webservice`) continues to operate independently for file uploads and offline batch processing.
- **Protocol:** Raw audio is streamed in binary 16 kHz mono 16-bit signed integer (int16) PCM frames.
- **Interim Transcripts:** WhisperLive returns live JSON messages with interim segments (`completed: false`) and committed segments (`completed: true`) which are relayed in real time to the connected client.
- **End-of-Audio Signaling:** When recording stops, the client sends a binary EOF sentinel frame: `b"END_OF_AUDIO"`. The proxy forwards this upstream and holds the upstream reader open until the final completed transcript arrives or the finalization timeout expires.

---

## Privacy & Consent Control

Real-time audio streaming from the client to live transcription servers is governed by a strict privacy control:

- **Environment Variable:** `ENABLE_REALTIME_TRANSCRIPTION`
- **Default:** `false` (opt-in)
- **Rationale:** Audio streams captured live from microphones should not be proxied to external/live transcription services without explicit deployment configuration and user consent.
- **Behavior when disabled:** When `ENABLE_REALTIME_TRANSCRIPTION=false`, connecting to `/api/v1/live-transcribe` is immediately rejected with WebSocket close code `1008` (`WS_1008_POLICY_VIOLATION`) and reason: `"Real-time transcription is disabled by system policy."`.

---

## WebSocket API Specification

### Endpoint

```
ws://<FIREFORM_HOST>:<PORT>/api/v1/live-transcribe
```

### Query Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `task` | `string` | `"translate"` | Mode of operation: `"translate"` (live translation to English) or `"transcribe"` (transcription in spoken language). |
| `language` | `string` | `null` | Optional ISO 639-1 language code (e.g. `"es"`, `"de"`, `"fr"`). When omitted (`null`), Whisper automatically detects the spoken language. |

### Message Protocol

1. **Client Connection:**
   The client connects to `ws://<host>:<port>/api/v1/live-transcribe?task=translate&language=es`.
2. **Audio Streaming:**
   While recording, the client continuously sends binary frames containing raw 16 kHz, mono, 16-bit signed integer Little-Endian PCM audio.
3. **Interim Transcripts (Proxy -> Client):**
   The proxy relays JSON text messages containing interim and completed segments:
   ```json
   {
     "uid": "<client-session-id>",
     "segments": [
       {
         "start": 0.0,
         "end": 1.5,
         "text": "Hello, how are you?",
         "completed": false
       }
     ]
   }
   ```
4. **Stopping Recording:**
   When the user stops recording, the client sends the exact binary frame:
   ```python
   b"END_OF_AUDIO"
   ```
5. **Finalization & Final Message:**
   The proxy forwards `b"END_OF_AUDIO"` to WhisperLive, waits up to `WHISPERLIVE_FINALIZATION_TIMEOUT` seconds for any final in-flight or finalized updates, and sends an explicit final message to the client containing the latest known transcript state:
   ```json
   {
     "type": "final",
     "uid": "<client-session-id>",
     "segments": [
       {
         "start": 0.0,
         "end": 2.5,
         "text": "Hello world.",
         "completed": false
       }
     ]
   }
   ```
   Both connections are then cleanly closed.

---

## Configuration Reference

The following settings are configured in `docker/.env.dev` and read by `app/core/config.py`:

| Variable | Default | Description |
|---|---|---|
| `ENABLE_REALTIME_TRANSCRIPTION` | `false` | Master toggle to enable real-time transcription WebSocket proxy (privacy opt-in). |
| `WHISPERLIVE_HOST` | `ws://localhost:9090` | WebSocket URI of upstream Collabora WhisperLive server (in Docker Compose: `ws://whisperlive:9090`). |
| `WHISPERLIVE_MODEL` | `small` | Whisper model size loaded by WhisperLive (`tiny`, `base`, `small`, `medium`, `large-v3`). |
| `WHISPERLIVE_FINALIZATION_TIMEOUT` | `10.0` | Timeout in seconds to await final WhisperLive results after `b"END_OF_AUDIO"` before terminating cleanly. |

---

## Docker Compose Dev Stack

In `docker/dev/compose.yml`, the `whisperlive` container runs as a dedicated sidecar service:

```yaml
whisperlive:
  image: ghcr.io/collabora/whisperlive-cpu:latest
  container_name: fireform-whisperlive
  ports:
    - "127.0.0.1:9090:9090"
  volumes:
    - whisperlive_models:/root/.cache/whisper
  networks:
    - fireform-network
```

Models are persisted locally across container restarts in the `whisperlive_models` Docker volume.

---

## Frontend Integration Note

The FireForm web/desktop frontend now resides in the separate repository [`fireform-core/fireform-frontend`](https://github.com/fireform-core/fireform-frontend).

- **Backend Capability:** The backend provides the underlying streaming API, model proxying, language auto-detection or parameter passing, and translation opt-out (`task=transcribe` vs `task=translate`).
- **User Interface Scope:** The user-facing UI controls (recording button, real-time waveform / transcript container, language selector, and live translation toggle) belong to and are maintained in `fireform-core/fireform-frontend`.