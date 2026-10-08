"""Live transcription proxy — FireForm issue #705.

Accepts a browser WebSocket connection, connects upstream to a Collabora
WhisperLive server, and proxies audio in real time.

Protocol (verified against WhisperLive main branch):
  1. Browser connects to  ws://localhost:8000/live-transcribe
  2. This proxy connects to  ws://WHISPERLIVE_HOST  (default ws://localhost:9090)
  3. Proxy sends WhisperLive the JSON init frame:
       {"uid": "<uuid4>", "language": null, "task": "translate",
        "model": "<WHISPERLIVE_MODEL>", "use_vad": false, "audio_format": "int16"}
     - task="translate" → Whisper outputs English regardless of source language
     - language=null    → auto-detect source language
     - use_vad=false    → every chunk is processed (lower latency for live use)
     - audio_format="int16" → browser sends raw PCM int16 16 kHz mono bytes
  4. Browser sends binary PCM int16 16 kHz mono audio frames; proxy forwards them.
  5. WhisperLive sends back JSON text frames:
       {"uid": "...", "segments": [{"text": "...", "completed": false}, ...]}
     Proxy relays these to the browser unchanged.
  6. When the user presses Stop, the browser sends the exact binary marker:
       b"END_OF_AUDIO"  (12 ASCII bytes, binary frame — verified from WhisperLive
       client.py: Client.END_OF_AUDIO.encode("utf-8"))
     Proxy forwards the marker to WhisperLive and keeps the browser WebSocket open.
  7. Proxy continues relaying WhisperLive messages until WhisperLive closes or a
     final message with all completed segments arrives, then closes both connections.

Environment variables (same pattern as WHISPER_HOST / OLLAMA_HOST in forms.py):
  WHISPERLIVE_HOST   — WebSocket URL of the WhisperLive server
                       default: ws://localhost:9090
  WHISPERLIVE_MODEL  — Whisper model name (must be multilingual, NOT a *.en model)
                       default: small
"""

import asyncio
import json
import logging
import os
import uuid

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed, WebSocketException

logger = logging.getLogger(__name__)

router = APIRouter(tags=["live-transcribe"])

# Binary marker verified from WhisperLive client.py:
#   Client.END_OF_AUDIO = "END_OF_AUDIO"
#   websocket.send(Client.END_OF_AUDIO.encode("utf-8"))
_END_OF_AUDIO: bytes = b"END_OF_AUDIO"


def _whisperlive_url() -> str:
    """WebSocket URL of the WhisperLive sidecar.

    Follows the same env-var pattern as WHISPER_HOST for the batch ASR service.
    Inside Docker Compose the value will be ws://whisperlive:9090; for local
    development the default ws://localhost:9090 applies.
    """
    return os.getenv("WHISPERLIVE_HOST", "ws://localhost:9090").rstrip("/")


def _whisperlive_model() -> str:
    """Whisper model for live transcription.

    Must be a multilingual model (no .en suffix) because task=translate is used
    to produce English output from any source language.
    """
    return os.getenv("WHISPERLIVE_MODEL", "small")


def _finalization_timeout() -> float:
    """Timeout in seconds for the finalization phase after END_OF_AUDIO."""
    try:
        return float(os.getenv("WHISPERLIVE_FINALIZATION_TIMEOUT", "10.0"))
    except (ValueError, TypeError):
        return 10.0


def _build_init_options(uid: str) -> str:
    """Return the JSON init frame expected by WhisperLive on connect.

    Fields verified from WhisperLive server.py / client.py:
      uid           — unique session identifier (uuid4 string)
      language      — null → auto-detect source language
      task          — "translate" → Whisper outputs English from any source
      model         — Whisper model size (must be a multilingual model)
      use_vad       — false → process every frame (lower latency for real-time)
      audio_format  — "int16" → server interprets bytes as signed 16-bit PCM
    """
    return json.dumps({
        "uid": uid,
        "language": None,
        "task": "translate",
        "model": _whisperlive_model(),
        "use_vad": False,
        "audio_format": "int16",
    })


def _all_segments_completed(message: str) -> bool:
    """Return True when WhisperLive reports all segments as completed.

    A final WhisperLive message has at least one segment and every segment has
    completed=True.  WhisperLive closes the upstream connection shortly after
    receiving END_OF_AUDIO, so this check is best-effort; the proxy also handles
    an upstream ConnectionClosed directly.
    """
    try:
        data = json.loads(message)
    except (ValueError, TypeError):
        return False
    segments = data.get("segments")
    if not segments:
        return False
    return all(seg.get("completed", False) for seg in segments)


@router.websocket("/live-transcribe")
async def live_transcribe(browser_ws: WebSocket) -> None:
    """WebSocket proxy between the Electron/browser client and WhisperLive.

    The browser must:
      - Send raw 16-bit signed PCM, 16 kHz, mono audio as binary frames.
      - Send the exact binary marker b"END_OF_AUDIO" when the user stops.
      - Keep its WebSocket open after sending the marker to receive the final
        translated segments before the connection is closed by the proxy.

    The proxy relays partial WhisperLive segment JSON back to the browser so the
    UI can display live partial transcription while the user is still speaking.
    """
    await browser_ws.accept()
    uid = str(uuid.uuid4())
    upstream_url = _whisperlive_url()

    logger.info("live-transcribe %s: connecting to %s", uid, upstream_url)

    # ------------------------------------------------------------------
    # Connect to WhisperLive.
    # ------------------------------------------------------------------
    try:
        upstream_ws = await websockets.connect(upstream_url)
    except (OSError, WebSocketException) as exc:
        logger.warning(
            "live-transcribe %s: cannot reach WhisperLive at %s — %s",
            uid, upstream_url, exc,
        )
        await browser_ws.send_text(
            json.dumps({
                "error": (
                    "Live transcription service is unavailable. "
                    "Please ensure WhisperLive is running."
                )
            })
        )
        await browser_ws.close(code=1011)
        return

    # ------------------------------------------------------------------
    # Send WhisperLive the required JSON init frame before any audio.
    # ------------------------------------------------------------------
    try:
        await upstream_ws.send(_build_init_options(uid))
        logger.debug("live-transcribe %s: init sent", uid)
    except (ConnectionClosed, WebSocketException) as exc:
        logger.warning("live-transcribe %s: upstream closed during init — %s", uid, exc)
        await browser_ws.send_text(json.dumps({"error": "Upstream closed unexpectedly."}))
        await browser_ws.close(code=1011)
        await upstream_ws.close()
        return

    # ------------------------------------------------------------------
    # Shared state between the two async tasks below.
    # ------------------------------------------------------------------
    eof_sent = asyncio.Event()     # set once the END_OF_AUDIO marker was forwarded
    session_done = asyncio.Event() # set to signal both tasks to exit cleanly

    # ------------------------------------------------------------------
    # Task A: browser → upstream (read audio frames from the browser and
    #         forward them to WhisperLive).
    # ------------------------------------------------------------------
    async def browser_to_upstream() -> None:
        try:
            while not session_done.is_set():
                try:
                    message = await browser_ws.receive()
                except (WebSocketDisconnect, RuntimeError):
                    logger.info(
                        "live-transcribe %s: browser disconnected unexpectedly", uid
                    )
                    if not eof_sent.is_set():
                        # Best-effort: signal WhisperLive to stop so it can
                        # release its transcription thread.
                        try:
                            await upstream_ws.send(_END_OF_AUDIO)
                        except Exception:
                            pass
                    session_done.set()
                    return

                msg_type = message.get("type", "")
                if msg_type == "websocket.disconnect":
                    logger.info(
                        "live-transcribe %s: browser sent disconnect frame", uid
                    )
                    session_done.set()
                    return

                raw_bytes: bytes | None = message.get("bytes")
                raw_text: str | None = message.get("text")

                if raw_bytes is not None:
                    if raw_bytes == _END_OF_AUDIO:
                        # Normal stop: forward the marker and let the upstream
                        # task drain the final results before closing.
                        logger.info(
                            "live-transcribe %s: forwarding END_OF_AUDIO", uid
                        )
                        try:
                            await upstream_ws.send(_END_OF_AUDIO)
                        except (ConnectionClosed, WebSocketException) as exc:
                            logger.warning(
                                "live-transcribe %s: upstream gone when sending "
                                "END_OF_AUDIO — %s", uid, exc,
                            )
                            session_done.set()
                            return
                        eof_sent.set()
                        # Stop reading from the browser; let upstream_to_browser
                        # drain the remaining messages and set session_done.
                        return
                    else:
                        # Normal PCM audio frame.
                        try:
                            await upstream_ws.send(raw_bytes)
                        except (ConnectionClosed, WebSocketException) as exc:
                            logger.warning(
                                "live-transcribe %s: upstream closed while sending "
                                "audio — %s", uid, exc,
                            )
                            try:
                                await browser_ws.send_text(
                                    json.dumps({"error": "Upstream connection lost."})
                                )
                            except Exception:
                                pass
                            session_done.set()
                            return
                elif raw_text is not None:
                    # Text from the browser during the audio phase is unexpected;
                    # log and ignore to avoid crashing the session.
                    logger.debug(
                        "live-transcribe %s: unexpected text from browser: %r",
                        uid, raw_text,
                    )
        except Exception as exc:
            logger.warning(
                "live-transcribe %s: error in browser_to_upstream: %s", uid, exc
            )
            session_done.set()
        finally:
            logger.debug("live-transcribe %s: browser_to_upstream task exiting", uid)

    # ------------------------------------------------------------------
    # Task B: upstream → browser (relay WhisperLive responses back to the
    #         browser, including partial segments during recording and the
    #         final segments after END_OF_AUDIO).
    # ------------------------------------------------------------------
    async def upstream_to_browser() -> None:
        try:
            while not session_done.is_set():
                try:
                    upstream_msg: str = await upstream_ws.recv()
                except ConnectionClosed:
                    logger.info(
                        "live-transcribe %s: upstream closed connection", uid
                    )
                    session_done.set()
                    return
                except WebSocketException as exc:
                    logger.warning(
                        "live-transcribe %s: upstream error — %s", uid, exc
                    )
                    session_done.set()
                    return

                # Relay the message to the browser.
                try:
                    await browser_ws.send_text(upstream_msg)
                except (WebSocketDisconnect, RuntimeError):
                    logger.info(
                        "live-transcribe %s: browser disconnected while relaying", uid
                    )
                    session_done.set()
                    return

                # After EOF has been forwarded, check whether this is the final
                # message so we can close cleanly without waiting for the upstream
                # to time out.
                if eof_sent.is_set() and _all_segments_completed(upstream_msg):
                    logger.info(
                        "live-transcribe %s: final segments received, closing", uid
                    )
                    session_done.set()
                    return
        except Exception as exc:
            logger.warning(
                "live-transcribe %s: error in upstream_to_browser: %s", uid, exc
            )
            session_done.set()
        finally:
            # Ensure session_done is set whenever upstream_to_browser finishes
            session_done.set()
            logger.debug("live-transcribe %s: upstream_to_browser task exiting", uid)

    # ------------------------------------------------------------------
    # Task C: finalization watcher (after END_OF_AUDIO is forwarded,
    #         enforce a timeout on receiving the final response).
    # ------------------------------------------------------------------
    async def finalization_watcher() -> None:
        try:
            await eof_sent.wait()
            if session_done.is_set():
                return
            timeout = _finalization_timeout()
            try:
                await asyncio.wait_for(session_done.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                if not session_done.is_set():
                    logger.warning(
                        "live-transcribe %s: finalization timed out after %s seconds",
                        uid, timeout,
                    )
                    try:
                        await browser_ws.send_text(
                            json.dumps({
                                "error": "Timed out waiting for final transcription.",
                            })
                        )
                    except Exception:
                        pass
                    session_done.set()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning(
                "live-transcribe %s: error in finalization_watcher: %s", uid, exc
            )
            session_done.set()
        finally:
            logger.debug("live-transcribe %s: finalization_watcher task exiting", uid)

    # ------------------------------------------------------------------
    # Run tasks concurrently. Normal session completion is signaled
    # by session_done (when upstream finishes relaying final segments).
    # ------------------------------------------------------------------
    task_a = asyncio.create_task(browser_to_upstream(), name=f"b2u-{uid}")
    task_b = asyncio.create_task(upstream_to_browser(), name=f"u2b-{uid}")
    task_c = asyncio.create_task(finalization_watcher(), name=f"fw-{uid}")

    try:
        await session_done.wait()
    finally:
        # Cancel whichever task is still running.
        for task in (task_a, task_b, task_c):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close both WebSockets gracefully.
        try:
            await upstream_ws.close()
        except Exception:
            pass
        try:
            await browser_ws.close()
        except Exception:
            pass

        logger.info("live-transcribe %s: session ended", uid)

