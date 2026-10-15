"""Tests for WebSocket proxy /api/v1/live-transcribe to WhisperLive.

Tests cover:
- Privacy policy / feature toggle (ENABLE_REALTIME_TRANSCRIPTION).
- Initial handshake frame sent to upstream WhisperLive (uid, task, language, model, use_vad, audio_format).
- Streaming binary PCM audio frame forwarding.
- Real WhisperLive finalization:
  - upstream sends interim segment with completed=False
  - client sends END_OF_AUDIO
  - upstream does not send a completed=True segment
  - proxy sends an explicit FireForm final message {"type": "final", "uid": "...", "segments": [...]}
    using latest known segments
  - timeout fallback finalizes using latest known segments without reporting failure
- Upstream message relay (interim segments).
- Connection error handling when WhisperLive is unreachable.
- Invalid task rejection.
- Client disconnect before EOF.
- Upstream disconnect during stream.
"""

import asyncio
import json
import socket
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
import websockets
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Mock heavy external services before route imports
import sys
if "pdfplumber" not in sys.modules:
    sys.modules["pdfplumber"] = MagicMock()
if "celery" not in sys.modules:
    _celery = MagicMock()
    _celery.schedules = MagicMock()
    sys.modules["celery"] = _celery
    sys.modules["celery.schedules"] = _celery.schedules

from app.api.routes import live_transcribe
from app.core import config


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ThreadedMockWhisperLiveServer:
    """Thread-isolated mock WhisperLive WebSocket server reflecting actual WhisperLive behavior.

    - Audio updates are sent with completed=False.
    - Upon END_OF_AUDIO, server does NOT necessarily send a completed=True segment.
    - In standard Faster Whisper mode, server may send one last segment update or simply close.
    """

    def __init__(
        self,
        port: int,
        send_post_eof_update: bool = False,
        post_eof_delay: float = 0.0,
        close_on_eof: bool = False,
    ):
        self.port = port
        self.send_post_eof_update = send_post_eof_update
        self.post_eof_delay = post_eof_delay
        self.close_on_eof = close_on_eof
        self.received_messages: list[str | bytes] = []
        self.handshake_event = threading.Event()
        self.eof_event = threading.Event()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    async def _handler(self, websocket):
        try:
            init_frame = await websocket.recv()
            self.received_messages.append(init_frame)
            self.handshake_event.set()

            while True:
                msg = await websocket.recv()
                self.received_messages.append(msg)
                if isinstance(msg, bytes) and msg == b"END_OF_AUDIO":
                    self.eof_event.set()
                    if self.send_post_eof_update:
                        if self.post_eof_delay > 0:
                            await asyncio.sleep(self.post_eof_delay)
                        post_eof_msg = {
                            "uid": "test-uid",
                            "segments": [
                                {
                                    "start": 0.0,
                                    "end": 2.5,
                                    "text": "Hello world complete.",
                                    "completed": False,  # Note: Real WhisperLive may still set completed=False
                                }
                            ],
                        }
                        await websocket.send(json.dumps(post_eof_msg))
                    if self.close_on_eof:
                        await websocket.close()
                    break
                else:
                    # Normal streaming audio chunk -> emit interim segment with completed=False
                    interim_msg = {
                        "uid": "test-uid",
                        "segments": [
                            {
                                "start": 0.0,
                                "end": 1.0,
                                "text": "Hello",
                                "completed": False,
                            }
                        ],
                    }
                    await websocket.send(json.dumps(interim_msg))
        except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
            pass

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def main():
            async with websockets.serve(self._handler, "127.0.0.1", self.port):
                while not self.stop_event.is_set():
                    await asyncio.sleep(0.05)

        loop.run_until_complete(main())
        loop.close()

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        time.sleep(0.2)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2.0)


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(live_transcribe.router, prefix="/api/v1")
    return test_app


@pytest.fixture
def live_client(app):
    return TestClient(app)


class TestPrivacyToggle:
    """Verify ENABLE_REALTIME_TRANSCRIPTION privacy behavior."""

    def test_rejected_when_realtime_transcription_disabled(self, live_client):
        with patch.object(config, "ENABLE_REALTIME_TRANSCRIPTION", False):
            with pytest.raises(Exception):
                with live_client.websocket_connect("/api/v1/live-transcribe") as ws:
                    ws.receive()


class TestLiveTranscribeProxy:
    """Verify WebSocket proxying between client and WhisperLive."""

    def test_handshake_interim_streaming_and_final_message(self, app):
        """Model real WhisperLive: interim segments sent, EOF sent, proxy emits final message."""
        port = get_free_port()
        # Mock WhisperLive that sends an interim segment, then on EOF sends one last segment (completed=False)
        mock_server = ThreadedMockWhisperLiveServer(port, send_post_eof_update=True, post_eof_delay=0.05)
        mock_server.start()

        try:
            with patch.object(config, "ENABLE_REALTIME_TRANSCRIPTION", True), \
                 patch.object(config, "WHISPERLIVE_HOST", f"ws://127.0.0.1:{port}"), \
                 patch.object(config, "WHISPERLIVE_MODEL", "base"):

                client = TestClient(app)
                with client.websocket_connect("/api/v1/live-transcribe?task=translate&language=es") as ws:
                    assert mock_server.handshake_event.wait(timeout=2.0)
                    handshake = json.loads(mock_server.received_messages[0])
                    assert handshake["task"] == "translate"
                    assert handshake["language"] == "es"
                    assert handshake["model"] == "base"
                    assert handshake["use_vad"] is False
                    assert handshake["audio_format"] == "int16"
                    assert "uid" in handshake

                    # Send dummy audio frame (int16 PCM)
                    pcm_chunk = b"\x00\x00" * 1600
                    ws.send_bytes(pcm_chunk)

                    # Interim message relayed directly from WhisperLive
                    interim_resp = ws.receive_json()
                    assert "segments" in interim_resp
                    assert interim_resp["segments"][0]["text"] == "Hello"
                    assert interim_resp["segments"][0]["completed"] is False

                    # Send END_OF_AUDIO
                    ws.send_bytes(b"END_OF_AUDIO")

                    # Relayed post-EOF update from WhisperLive
                    post_eof_relay = ws.receive_json()
                    assert post_eof_relay["segments"][0]["text"] == "Hello world complete."

                    # Explicit FireForm final message
                    final_msg = ws.receive_json()
                    assert final_msg["type"] == "final"
                    assert "segments" in final_msg
                    assert final_msg["segments"][0]["text"] == "Hello world complete."

        finally:
            mock_server.stop()

    def test_finalization_without_post_eof_message(self, app):
        """Real Faster Whisper: upstream sends NO message after END_OF_AUDIO and closes.
        Proxy must finalize using latest known segments without failing.
        """
        port = get_free_port()
        mock_server = ThreadedMockWhisperLiveServer(port, send_post_eof_update=False, close_on_eof=True)
        mock_server.start()

        try:
            with patch.object(config, "ENABLE_REALTIME_TRANSCRIPTION", True), \
                 patch.object(config, "WHISPERLIVE_HOST", f"ws://127.0.0.1:{port}"), \
                 patch.object(config, "WHISPERLIVE_FINALIZATION_TIMEOUT", 1.0):

                client = TestClient(app)
                with client.websocket_connect("/api/v1/live-transcribe?task=transcribe") as ws:
                    assert mock_server.handshake_event.wait(timeout=2.0)

                    # Stream audio
                    ws.send_bytes(b"\x00\x00" * 1600)
                    interim = ws.receive_json()
                    assert interim["segments"][0]["text"] == "Hello"

                    # Stop recording
                    ws.send_bytes(b"END_OF_AUDIO")

                    # Proxy must send final message with latest known segments
                    final_msg = ws.receive_json()
                    assert final_msg["type"] == "final"
                    assert len(final_msg["segments"]) == 1
                    assert final_msg["segments"][0]["text"] == "Hello"

        finally:
            mock_server.stop()

    def test_finalization_timeout_finalizes_with_latest_state(self, app):
        """If upstream does not close and does not emit after EOF before timeout,
        proxy finalizes using latest known segments and closes cleanly without failure.
        """
        port = get_free_port()
        # Mock server keeps connection open and does NOT send anything after EOF
        mock_server = ThreadedMockWhisperLiveServer(port, send_post_eof_update=False, close_on_eof=False)
        mock_server.start()

        try:
            with patch.object(config, "ENABLE_REALTIME_TRANSCRIPTION", True), \
                 patch.object(config, "WHISPERLIVE_HOST", f"ws://127.0.0.1:{port}"), \
                 patch.object(config, "WHISPERLIVE_FINALIZATION_TIMEOUT", 0.3):

                client = TestClient(app)
                with client.websocket_connect("/api/v1/live-transcribe") as ws:
                    assert mock_server.handshake_event.wait(timeout=2.0)

                    # Stream audio
                    ws.send_bytes(b"\x00\x00" * 1600)
                    interim = ws.receive_json()
                    assert interim["segments"][0]["text"] == "Hello"

                    # Stop recording
                    ws.send_bytes(b"END_OF_AUDIO")

                    # After 0.3s timeout, proxy sends final message with latest known segments
                    final_msg = ws.receive_json()
                    assert final_msg["type"] == "final"
                    assert final_msg["segments"][0]["text"] == "Hello"

        finally:
            mock_server.stop()

    def test_transcribe_task_opt_out_translation(self, app):
        port = get_free_port()
        mock_server = ThreadedMockWhisperLiveServer(port, send_post_eof_update=False, close_on_eof=True)
        mock_server.start()

        try:
            with patch.object(config, "ENABLE_REALTIME_TRANSCRIPTION", True), \
                 patch.object(config, "WHISPERLIVE_HOST", f"ws://127.0.0.1:{port}"):

                client = TestClient(app)
                with client.websocket_connect("/api/v1/live-transcribe?task=transcribe") as ws:
                    assert mock_server.handshake_event.wait(timeout=2.0)
                    handshake = json.loads(mock_server.received_messages[0])
                    assert handshake["task"] == "transcribe"
                    assert handshake["language"] is None

                    ws.send_bytes(b"\x00\x00" * 1600)
                    ws.receive_json()
                    ws.send_bytes(b"END_OF_AUDIO")
                    final_msg = ws.receive_json()
                    assert final_msg["type"] == "final"

        finally:
            mock_server.stop()

    def test_upstream_unavailable_closes_gracefully(self, app):
        unused_port = get_free_port()
        with patch.object(config, "ENABLE_REALTIME_TRANSCRIPTION", True), \
             patch.object(config, "WHISPERLIVE_HOST", f"ws://127.0.0.1:{unused_port}"):

            client = TestClient(app)
            with client.websocket_connect("/api/v1/live-transcribe") as ws:
                resp = ws.receive_json()
                assert "error" in resp
                assert "unavailable" in resp["error"].lower()

    def test_invalid_task_rejected(self, app):
        with patch.object(config, "ENABLE_REALTIME_TRANSCRIPTION", True):
            client = TestClient(app)
            with client.websocket_connect("/api/v1/live-transcribe?task=invalid_mode") as ws:
                resp = ws.receive_json()
                assert "error" in resp
                assert "transcribe" in resp["error"]

    def test_client_disconnect_before_eof(self, app):
        port = get_free_port()
        mock_server = ThreadedMockWhisperLiveServer(port)
        mock_server.start()

        try:
            with patch.object(config, "ENABLE_REALTIME_TRANSCRIPTION", True), \
                 patch.object(config, "WHISPERLIVE_HOST", f"ws://127.0.0.1:{port}"):

                client = TestClient(app)
                with client.websocket_connect("/api/v1/live-transcribe") as ws:
                    assert mock_server.handshake_event.wait(timeout=2.0)
                    ws.send_bytes(b"\x00\x00" * 800)
                    # Disconnect client immediately without sending END_OF_AUDIO
                assert not mock_server.eof_event.is_set()
        finally:
            mock_server.stop()

    def test_fast_post_eof_message_race(self, app):
        """Verify that when WhisperLive sends the post-EOF message immediately (zero delay),
        the proxy catches it without race condition and does not block for the full timeout.
        """
        port = get_free_port()
        # Post-EOF message sent with zero delay
        mock_server = ThreadedMockWhisperLiveServer(port, send_post_eof_update=True, post_eof_delay=0.0)
        mock_server.start()

        try:
            with patch.object(config, "ENABLE_REALTIME_TRANSCRIPTION", True), \
                 patch.object(config, "WHISPERLIVE_HOST", f"ws://127.0.0.1:{port}"), \
                 patch.object(config, "WHISPERLIVE_FINALIZATION_TIMEOUT", 2.0):

                start_time = time.time()
                client = TestClient(app)
                with client.websocket_connect("/api/v1/live-transcribe") as ws:
                    assert mock_server.handshake_event.wait(timeout=2.0)
                    ws.send_bytes(b"\x00\x00" * 1600)
                    interim = ws.receive_json()
                    assert interim["segments"][0]["text"] == "Hello"

                    ws.send_bytes(b"END_OF_AUDIO")
                    post_eof_relay = ws.receive_json()
                    assert post_eof_relay["segments"][0]["text"] == "Hello world complete."

                    final_msg = ws.receive_json()
                    assert final_msg["type"] == "final"
                    assert final_msg["segments"][0]["text"] == "Hello world complete."

                elapsed = time.time() - start_time
                # Elapsed should be well under the 2.0s timeout since the post-EOF message arrived immediately
                assert elapsed < 1.5
        finally:
            mock_server.stop()

    def test_post_eof_message_arrives_instantly_race(self, app):
        """Regression test: verify that when WhisperLive sends the post-EOF update immediately
        upon receiving END_OF_AUDIO, unconditional creation of msg_waiter catches it instantly
        without blocking for the full timeout.
        """
        port = get_free_port()
        mock_server = ThreadedMockWhisperLiveServer(port, send_post_eof_update=True, post_eof_delay=0.0)
        mock_server.start()

        try:
            with patch.object(config, "ENABLE_REALTIME_TRANSCRIPTION", True), \
                 patch.object(config, "WHISPERLIVE_HOST", f"ws://127.0.0.1:{port}"), \
                 patch.object(config, "WHISPERLIVE_FINALIZATION_TIMEOUT", 3.0):

                t0 = time.perf_counter()
                client = TestClient(app)
                with client.websocket_connect("/api/v1/live-transcribe") as ws:
                    assert mock_server.handshake_event.wait(timeout=2.0)
                    ws.send_bytes(b"\x00\x00" * 1600)
                    ws.receive_json()

                    ws.send_bytes(b"END_OF_AUDIO")
                    relayed = ws.receive_json()
                    assert relayed["segments"][0]["text"] == "Hello world complete."

                    final_msg = ws.receive_json()
                    assert final_msg["type"] == "final"
                    assert final_msg["segments"][0]["text"] == "Hello world complete."

                duration = time.perf_counter() - t0
                # Must finish in a fraction of a second, far below the 3.0s timeout
                assert duration < 1.0, f"Took {duration:.2f}s; should have resolved immediately"
        finally:
            mock_server.stop()

    def test_upstream_disconnect_during_stream(self, app):
        port = get_free_port()
        mock_server = ThreadedMockWhisperLiveServer(port)
        mock_server.start()

        try:
            with patch.object(config, "ENABLE_REALTIME_TRANSCRIPTION", True), \
                 patch.object(config, "WHISPERLIVE_HOST", f"ws://127.0.0.1:{port}"):

                client = TestClient(app)
                with client.websocket_connect("/api/v1/live-transcribe") as ws:
                    assert mock_server.handshake_event.wait(timeout=2.0)
                    mock_server.stop()
                    ws.send_bytes(b"\x00\x00" * 800)
        finally:
            mock_server.stop()
