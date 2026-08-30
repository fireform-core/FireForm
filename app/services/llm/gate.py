"""A shared stop signal for one batch of prompts.

Ten retries ten seconds apart is a sensible wait for one call. It is a terrible
wait repeated across twenty prompts running four at a time, which is what an
extraction is: the first prompt waits its hundred seconds, and then so does
every prompt behind it, for a limit that is clearly not going to lift.

So the batch shares a gate. The first prompt to run out of retries trips it, and
everything still queued fails immediately with the same error instead of paying
the wait again. Callers that pass no gate are unaffected.
"""

from __future__ import annotations

import threading

from app.services.llm.errors import LLMRateLimitError


class RateLimitGate:
    """Trip once, and every later check through this gate fails the same way."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tripped: LLMRateLimitError | None = None

    @property
    def tripped(self) -> bool:
        with self._lock:
            return self._tripped is not None

    def trip(self, error: LLMRateLimitError) -> None:
        """Record the first rate limit failure. Later ones change nothing."""
        with self._lock:
            if self._tripped is None:
                self._tripped = error

    def check(self) -> None:
        """Raise straight away if this batch already gave up on rate limits."""
        with self._lock:
            tripped = self._tripped
        if tripped is not None:
            raise LLMRateLimitError(
                f"skipped, the provider is rate limiting this run: {tripped}",
                retry_after_seconds=tripped.retry_after_seconds,
            )
