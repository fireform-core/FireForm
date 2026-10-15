"""WebSocket proxy for real-time WhisperLive transcription and live translation."""

import asyncio
import json
import logging
import uuid

import websockets
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/live-transcribe", tags=["live-transcription"])

END_OF_AUDIO = b"END_OF_AUDIO"


@router.websocket("")
async def live_transcribe(
    websocket: WebSocket,
    task: str = Query(
        default="translate",
        description="Transcription task: 'translate' (live English translation) or 'transcribe'.",
    ),
    language: str | None = Query(
        default=None,
        description="Source audio language code (e.g. 'en', 'es', 'de'). None for auto-detection.",
    ),
) -> None:
    """Proxy browser audio streams to WhisperLive and relay live interim and final transcripts.

    Protocol flow:
    1. Client connects to `/api/v1/live-transcribe` with query parameters `task` and optional `language`.
    2. Proxy verifies the privacy/consent flag (ENABLE_REALTIME_TRANSCRIPTION).
    3. Proxy connects upstream to the WhisperLive WebSocket server.
    4. Proxy sends WhisperLive handshake JSON: {uid, language, task, model, use_vad=False, audio_format='int16'}.
    5. Client streams raw mono 16 kHz int16 PCM audio frames as binary WebSocket payloads.
    6. WhisperLive produces interim transcript JSON frames which are relayed immediately to the client.
    7. Client sends the b"END_OF_AUDIO" binary marker when recording stops.
    8. Proxy forwards b"END_OF_AUDIO" upstream, holds the upstream reader open up to WHISPERLIVE_FINALIZATION_TIMEOUT
       to receive any in-flight or finalized updates, and sends an explicit finalization frame to the client:
       {"type": "final", "uid": "...", "segments": [...]}.
    9. Connections are then cleanly closed.
    """
    if not config.ENABLE_REALTIME_TRANSCRIPTION:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Real-time transcription is disabled by system policy.",
        )
        return

    await websocket.accept()

    whisper_socket = None

    try:
        if task not in {"transcribe", "translate"}:
            await websocket.send_json({"error": "task must be 'transcribe' or 'translate'."})
            await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
            return

        # Connect to upstream WhisperLive
        try:
            whisper_socket = await websockets.connect(
                config.WHISPERLIVE_HOST,
                max_size=None,
            )
        except Exception as exc:
            logger.error("Failed to connect to WhisperLive at %s: %s", config.WHISPERLIVE_HOST, exc)
            await websocket.send_json({"error": "WhisperLive service unavailable."})
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return

        session_uid = uuid.uuid4().hex

        # Upstream handshake
        init_payload = {
            "uid": session_uid,
            "language": language,
            "task": task,
            "model": config.WHISPERLIVE_MODEL,
            "use_vad": False,
            "audio_format": "int16",
        }
        await whisper_socket.send(json.dumps(init_payload))

        # Coordination events & state
        eof_forwarded_event = asyncio.Event()
        latest_segments: list[dict] = []
        post_eof_update_event = asyncio.Event()

        async def browser_to_whisper() -> None:
            """Read binary PCM from client and forward to WhisperLive until EOF or disconnect."""
            while not eof_forwarded_event.is_set():
                msg = await websocket.receive()
                msg_type = msg.get("type")
                if msg_type == "websocket.disconnect":
                    break

                raw_bytes = msg.get("bytes")
                if raw_bytes is not None:
                    if raw_bytes == END_OF_AUDIO:
                        # Forward END_OF_AUDIO upstream exactly once, then mark the EOF-forwarded state
                        await whisper_socket.send(END_OF_AUDIO)
                        eof_forwarded_event.set()
                        break
                    await whisper_socket.send(raw_bytes)
                elif msg.get("text"):
                    # Pass-through any control text if sent
                    await whisper_socket.send(msg["text"])

        async def whisper_to_browser() -> None:
            """Relay WhisperLive messages to client until upstream closes or task is cancelled."""
            nonlocal latest_segments
            try:
                while True:
                    upstream_msg = await whisper_socket.recv()
                    if isinstance(upstream_msg, bytes):
                        await websocket.send_bytes(upstream_msg)
                    else:
                        await websocket.send_text(upstream_msg)
                        try:
                            parsed = json.loads(upstream_msg)
                            if isinstance(parsed, dict) and "segments" in parsed:
                                segs = parsed.get("segments")
                                if isinstance(segs, list):
                                    latest_segments = segs
                                    # Always set post_eof_update_event if EOF has already been forwarded
                                    if eof_forwarded_event.is_set():
                                        post_eof_update_event.set()
                        except json.JSONDecodeError:
                            pass
            except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
                pass

        b2w_task = asyncio.create_task(browser_to_whisper())
        w2b_task = asyncio.create_task(whisper_to_browser())

        # Wait until client finishes sending audio (EOF or disconnect) or upstream closes
        done, pending = await asyncio.wait(
            [b2w_task, w2b_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        if eof_forwarded_event.is_set():
            # Client sent END_OF_AUDIO cleanly and it was forwarded to WhisperLive.
            # Upstream may emit one more finalized segment frame or close.
            # Unconditionally create the waiter task on post_eof_update_event so any message
            # already arrived or arriving shortly resolves immediately without race conditions.
            msg_waiter = asyncio.create_task(post_eof_update_event.wait())
            try:
                await asyncio.wait(
                    [w2b_task, msg_waiter],
                    timeout=config.WHISPERLIVE_FINALIZATION_TIMEOUT,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except Exception:
                pass
            finally:
                if not msg_waiter.done():
                    msg_waiter.cancel()

            # Cleanly cancel upstream reader if still running
            w2b_task.cancel()
            try:
                await w2b_task
            except asyncio.CancelledError:
                pass

            # Send explicit FireForm final message with latest known segments state
            final_payload = {
                "type": "final",
                "uid": session_uid,
                "segments": latest_segments,
            }
            try:
                await websocket.send_json(final_payload)
            except Exception:
                pass
        else:
            # Client disconnected unexpectedly or upstream terminated prematurely
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    except WebSocketDisconnect:
        pass
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as exc:
        logger.exception("Error in live_transcribe session: %s", exc)
        try:
            await websocket.send_json({"error": str(exc)})
        except Exception:
            pass
    finally:
        if whisper_socket is not None:
            try:
                await whisper_socket.close()
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass