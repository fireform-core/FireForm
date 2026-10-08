"""Focused tests for the live-transcribe WebSocket proxy (issue #705).

These tests use a lightweight asyncio WebSocket server as the mock WhisperLive
target so nothing real needs to be running.

Test scope:
  - WebSocket connection to /live-transcribe
  - WhisperLive initialization frame verification
  - Binary audio forwarding
  - END_OF_AUDIO forwarding and browser connection stays open
  - Partial segment relay
  - Final segment relay and clean shutdown
  - Upstream unreachable → error message to browser
  - WHISPERLIVE_HOST / WHISPERLIVE_MODEL env vars respected
  - Existing /forms/transcribe batch endpoint regression
"""

import asyncio
import json
import threading
import uuid
from unittest.mock import patch, MagicMock

import pytest
import websockets
from websockets.server import serve as ws_serve
from fastapi.testclient import TestClient

from api.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _MockWhisperLive:
    """Minimal asyncio WebSocket server that mimics a WhisperLive instance.

    The test configures what the server will send back via `responses`.
    The server records every binary and text frame it receives in `received`.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self.received: list = []       # frames received from the proxy
        self.responses: list = []      # text frames to send back, in order
        self.close_on_eof: bool = True # whether to close upon receiving END_OF_AUDIO
        self._server = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)

    # -- async handler -------------------------------------------------------

    async def _handler(self, websocket):
        idx = 0
        try:
            async for message in websocket:
                with self._cv:
                    self.received.append(message)
                    self._cv.notify_all()
                # Send any queued responses.
                if idx < len(self.responses):
                    await websocket.send(self.responses[idx])
                    idx += 1
                # If we received END_OF_AUDIO, send remaining responses and close.
                if isinstance(message, bytes) and message == b"END_OF_AUDIO":
                    while idx < len(self.responses):
                        await websocket.send(self.responses[idx])
                        idx += 1
                    if self.close_on_eof:
                        break  # closes the server-side socket
        except websockets.exceptions.ConnectionClosed:
            pass

    # -- synchronization helpers ---------------------------------------------

    def wait_for_received(self, count: int = 1, timeout: float = 5.0) -> bool:
        """Wait until at least `count` frames have been received."""
        with self._cv:
            return self._cv.wait_for(
                lambda: len(self.received) >= count, timeout=timeout
            )

    def wait_for_frame(self, predicate, timeout: float = 5.0) -> bool:
        """Wait until a received frame satisfies `predicate(frame)`."""
        with self._cv:
            return self._cv.wait_for(
                lambda: any(predicate(f) for f in self.received),
                timeout=timeout,
            )

    def wait_for_init(self, timeout: float = 5.0) -> dict | None:
        """Wait for the JSON init frame and return the parsed dictionary."""
        def is_init(f):
            if isinstance(f, str):
                try:
                    data = json.loads(f)
                    return isinstance(data, dict) and "uid" in data and "task" in data
                except Exception:
                    pass
            return False

        if self.wait_for_frame(is_init, timeout=timeout):
            with self._lock:
                for f in self.received:
                    if is_init(f):
                        return json.loads(f)
        return None

    def wait_for_eof(self, timeout: float = 5.0) -> bool:
        """Wait until b'END_OF_AUDIO' is received."""
        return self.wait_for_frame(lambda f: f == b"END_OF_AUDIO", timeout=timeout)

    # -- lifecycle -----------------------------------------------------------

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def _serve():
            async with ws_serve(self._handler, self.host, self.port) as server:
                self._server = server
                # Pick up the actual bound port (useful when port=0).
                self.port = server.sockets[0].getsockname()[1]
                self._ready.set()
                await server.wait_closed()

        self._loop.run_until_complete(_serve())

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)
        return self

    def stop(self):
        if self._server and self._loop:
            self._loop.call_soon_threadsafe(self._server.close)

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_wl():
    """Start a mock WhisperLive server for the duration of a test."""
    server = _MockWhisperLive().start()
    yield server
    server.stop()


@pytest.fixture
def live_client(mock_wl, monkeypatch):
    """TestClient with WHISPERLIVE_HOST pointing at the mock server."""
    monkeypatch.setenv("WHISPERLIVE_HOST", mock_wl.ws_url)
    monkeypatch.setenv("WHISPERLIVE_MODEL", "small")
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. WebSocket connection
# ---------------------------------------------------------------------------

class TestWebSocketConnection:

    def test_endpoint_exists(self, live_client):
        """Browser can open a WebSocket to /live-transcribe."""
        with live_client.websocket_connect("/live-transcribe") as ws:
            # Connection established — nothing needed.
            pass

    def test_endpoint_not_available_without_upstream(self, monkeypatch):
        """When WhisperLive is unreachable, the proxy sends an error and closes."""
        monkeypatch.setenv("WHISPERLIVE_HOST", "ws://127.0.0.1:19999")  # nothing there
        client = TestClient(app)
        with client.websocket_connect("/live-transcribe") as ws:
            msg = json.loads(ws.receive_text())
            assert "error" in msg
            assert "unavailable" in msg["error"].lower()


# ---------------------------------------------------------------------------
# 2. WhisperLive initialization frame
# ---------------------------------------------------------------------------

class TestInitFrame:

    def test_proxy_sends_init_on_connect(self, live_client, mock_wl):
        """First frame the mock server receives must be the JSON init message."""
        with live_client.websocket_connect("/live-transcribe") as ws:
            init = mock_wl.wait_for_init()

        assert init is not None, "Mock server did not receive init frame"
        assert "uid" in init
        assert init["task"] == "translate"
        assert init["use_vad"] is False
        assert init["audio_format"] == "int16"
        assert init["model"] == "small"
        # language must be None (null in JSON) for auto-detect.
        assert init["language"] is None

    def test_init_uses_configured_model(self, mock_wl, monkeypatch):
        """WHISPERLIVE_MODEL env var is reflected in the init frame."""
        monkeypatch.setenv("WHISPERLIVE_HOST", mock_wl.ws_url)
        monkeypatch.setenv("WHISPERLIVE_MODEL", "medium")
        client = TestClient(app)
        with client.websocket_connect("/live-transcribe") as ws:
            init = mock_wl.wait_for_init()

        assert init is not None, "Mock server did not receive init frame"
        assert init["model"] == "medium"

    def test_init_uid_is_unique_per_session(self, mock_wl, monkeypatch):
        """Each session generates a distinct UID."""
        monkeypatch.setenv("WHISPERLIVE_HOST", mock_wl.ws_url)
        monkeypatch.setenv("WHISPERLIVE_MODEL", "small")
        client = TestClient(app)

        uids = []
        for i in range(1, 3):
            with client.websocket_connect("/live-transcribe"):
                assert mock_wl.wait_for_received(i), f"Session {i} init not received"

        for frame in mock_wl.received:
            try:
                data = json.loads(frame)
                if "uid" in data:
                    uids.append(data["uid"])
            except (ValueError, TypeError):
                pass
        assert len(uids) >= 2
        assert len(set(uids)) == len(uids), "UIDs must be unique across sessions"


# ---------------------------------------------------------------------------
# 3. Binary audio forwarding
# ---------------------------------------------------------------------------

class TestAudioForwarding:

    def test_binary_frames_forwarded(self, live_client, mock_wl):
        """Binary PCM frames sent by the browser are forwarded to WhisperLive."""
        pcm_chunk = bytes(range(32))  # 32 bytes of dummy PCM

        with live_client.websocket_connect("/live-transcribe") as ws:
            assert mock_wl.wait_for_init() is not None
            ws.send_bytes(pcm_chunk)
            assert mock_wl.wait_for_frame(lambda f: f == pcm_chunk)

        binary_frames = [f for f in mock_wl.received if isinstance(f, bytes)]
        assert any(f == pcm_chunk for f in binary_frames)

    def test_multiple_audio_frames(self, live_client, mock_wl):
        """Multiple PCM chunks are all forwarded in order."""
        chunks = [bytes([i] * 16) for i in range(3)]

        with live_client.websocket_connect("/live-transcribe") as ws:
            assert mock_wl.wait_for_init() is not None
            for chunk in chunks:
                ws.send_bytes(chunk)
            assert mock_wl.wait_for_received(1 + len(chunks))

        binary_frames = [f for f in mock_wl.received if isinstance(f, bytes)]
        for chunk in chunks:
            assert chunk in binary_frames


# ---------------------------------------------------------------------------
# 4. END_OF_AUDIO
# ---------------------------------------------------------------------------

class TestEndOfAudio:

    def test_eof_marker_forwarded(self, live_client, mock_wl):
        """b'END_OF_AUDIO' sent by the browser is forwarded to WhisperLive."""
        with live_client.websocket_connect("/live-transcribe") as ws:
            assert mock_wl.wait_for_init() is not None
            ws.send_bytes(b"END_OF_AUDIO")
            assert mock_wl.wait_for_eof(), "Mock server did not receive b'END_OF_AUDIO'"
            binary_frames = [f for f in mock_wl.received if isinstance(f, bytes)]
            assert b"END_OF_AUDIO" in binary_frames

    def test_browser_ws_stays_open_after_eof(self, live_client, mock_wl):
        """The browser WebSocket must not be closed immediately after EOF.

        The mock server sends a partial then final segment after END_OF_AUDIO.
        The client must still be able to receive both.
        """
        partial_msg = json.dumps({
            "uid": "test",
            "segments": [{"text": "Hola mundo", "completed": False}],
        })
        final_msg = json.dumps({
            "uid": "test",
            "segments": [{"text": "Hello world", "completed": True}],
        })
        mock_wl.responses = [partial_msg, final_msg]

        received_from_server = []
        with live_client.websocket_connect("/live-transcribe") as ws:
            ws.send_bytes(b"dummy_pcm")
            ws.send_bytes(b"END_OF_AUDIO")
            # Receive messages until the server closes.
            for _ in range(5):
                try:
                    msg = ws.receive_text()
                    received_from_server.append(json.loads(msg))
                except Exception:
                    break

        texts = [
            seg["text"]
            for resp in received_from_server
            for seg in resp.get("segments", [])
        ]
        assert "Hello world" in texts, (
            "Final English translation must be relayed to the browser"
        )

    def test_finalization_timeout_sends_error_and_closes(self, mock_wl, monkeypatch):
        """If WhisperLive does not produce a final response within timeout, send error and close."""
        monkeypatch.setenv("WHISPERLIVE_HOST", mock_wl.ws_url)
        monkeypatch.setenv("WHISPERLIVE_MODEL", "small")
        monkeypatch.setenv("WHISPERLIVE_FINALIZATION_TIMEOUT", "0.2")

        # Mock server keeps connection open without sending a completed final response
        mock_wl.close_on_eof = False
        mock_wl.responses = []

        client = TestClient(app)
        with client.websocket_connect("/live-transcribe") as ws:
            assert mock_wl.wait_for_init() is not None
            ws.send_bytes(b"END_OF_AUDIO")
            assert mock_wl.wait_for_eof()

            # Proxy should send timeout error to browser
            msg = json.loads(ws.receive_text())
            assert "error" in msg
            assert "timed out" in msg["error"].lower()

            # Connection should be closed by proxy
            with pytest.raises(Exception):
                ws.receive_text()


# ---------------------------------------------------------------------------
# 5. Partial segment relay
# ---------------------------------------------------------------------------

class TestPartialSegmentRelay:

    def test_partial_segments_relayed(self, live_client, mock_wl):
        """WhisperLive partial segment messages are relayed to the browser."""
        partial_msg = json.dumps({
            "uid": "x",
            "segments": [{"text": "Bonjour le", "completed": False}],
        })
        mock_wl.responses = [partial_msg]

        received = []
        with live_client.websocket_connect("/live-transcribe") as ws:
            ws.send_bytes(bytes(16))  # one PCM chunk triggers the response
            try:
                received.append(json.loads(ws.receive_text()))
            except Exception:
                pass

        assert any(
            "Bonjour le" in seg["text"]
            for resp in received
            for seg in resp.get("segments", [])
        )


# ---------------------------------------------------------------------------
# 6. Final transcript
# ---------------------------------------------------------------------------

class TestFinalTranscript:

    def test_final_completed_segments_relayed(self, live_client, mock_wl):
        """Final WhisperLive message with completed=True is sent to the browser."""
        final_msg = json.dumps({
            "uid": "x",
            "segments": [{"text": "Structure fire on Main Street.", "completed": True}],
        })
        mock_wl.responses = [final_msg]

        received = []
        with live_client.websocket_connect("/live-transcribe") as ws:
            ws.send_bytes(b"END_OF_AUDIO")
            try:
                received.append(json.loads(ws.receive_text()))
            except Exception:
                pass

        texts = [
            seg["text"]
            for resp in received
            for seg in resp.get("segments", [])
        ]
        assert "Structure fire on Main Street." in texts


# ---------------------------------------------------------------------------
# 7. Connection failure
# ---------------------------------------------------------------------------

class TestConnectionFailure:

    def test_upstream_unreachable_sends_error(self, monkeypatch):
        """If WhisperLive is down, the browser receives an error JSON."""
        monkeypatch.setenv("WHISPERLIVE_HOST", "ws://127.0.0.1:29999")
        client = TestClient(app)
        with client.websocket_connect("/live-transcribe") as ws:
            msg = json.loads(ws.receive_text())
        assert "error" in msg

    def test_upstream_unreachable_does_not_crash_app(self, monkeypatch):
        """A bad WHISPERLIVE_HOST must not throw an uncaught exception."""
        monkeypatch.setenv("WHISPERLIVE_HOST", "ws://127.0.0.1:29998")
        client = TestClient(app)
        # Should not raise
        with client.websocket_connect("/live-transcribe") as ws:
            ws.receive_text()  # error message


# ---------------------------------------------------------------------------
# 8. Env-var configuration
# ---------------------------------------------------------------------------

class TestEnvVarConfiguration:

    def test_whisperlive_host_env_var(self, mock_wl, monkeypatch):
        """WHISPERLIVE_HOST env var controls where the proxy connects."""
        monkeypatch.setenv("WHISPERLIVE_HOST", mock_wl.ws_url)
        monkeypatch.setenv("WHISPERLIVE_MODEL", "small")
        client = TestClient(app)
        with client.websocket_connect("/live-transcribe") as ws:
            init = mock_wl.wait_for_init()
        # The mock server received traffic → correct host was used.
        assert init is not None
        assert len(mock_wl.received) >= 1

    def test_whisperlive_model_env_var(self, mock_wl, monkeypatch):
        """WHISPERLIVE_MODEL env var is passed in the init JSON."""
        monkeypatch.setenv("WHISPERLIVE_HOST", mock_wl.ws_url)
        monkeypatch.setenv("WHISPERLIVE_MODEL", "large-v3")
        client = TestClient(app)
        with client.websocket_connect("/live-transcribe") as ws:
            init = mock_wl.wait_for_init()
        assert init is not None
        assert init["model"] == "large-v3"


# ---------------------------------------------------------------------------
# 9. Regression — existing batch transcription
# ---------------------------------------------------------------------------

class TestBatchTranscriptionRegression:
    """/forms/transcribe must continue to work exactly as before."""

    def test_transcribe_success(self, monkeypatch):
        import io
        fake_resp = MagicMock()
        fake_resp.json.return_value = {"text": "structure fire on main street"}
        fake_resp.raise_for_status.return_value = None

        monkeypatch.setattr("api.routes.forms.requests.post", lambda *a, **k: fake_resp)

        client = TestClient(app)
        audio = ("audio", ("rec.wav", io.BytesIO(b"RIFF"), "audio/wav"))
        resp = client.post("/forms/transcribe", files=[audio])

        assert resp.status_code == 200
        assert resp.json()["text"] == "structure fire on main street"

    def test_transcribe_service_down_returns_503(self, monkeypatch):
        import io
        import requests as req

        def boom(*a, **k):
            raise req.exceptions.ConnectionError("down")

        monkeypatch.setattr("api.routes.forms.requests.post", boom)

        client = TestClient(app)
        audio = ("audio", ("rec.wav", io.BytesIO(b"data"), "audio/wav"))
        resp = client.post("/forms/transcribe", files=[audio])
        assert resp.status_code == 503

