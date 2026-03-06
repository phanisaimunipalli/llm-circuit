"""
Circuit Breaker state machine.

States:
  CLOSED   — Normal operation. Requests route to Anthropic.
  OPEN     — Outage detected. Requests route to Ollama fallback.
  HALF_OPEN — Recovery probe. One request goes to Anthropic.
               Success → CLOSED. Failure → OPEN.

Transitions:
  CLOSED   --[N consecutive failures]--> OPEN
  OPEN     --[recovery_timeout elapsed]--> HALF_OPEN
  HALF_OPEN --[success]--> CLOSED
  HALF_OPEN --[failure]--> OPEN
"""

import asyncio
import time
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger("llm_circuit.circuit")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 30):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.opened_at: Optional[float] = None
        self._lock = asyncio.Lock()

    async def record_failure(self):
        async with self._lock:
            self.failure_count += 1
            if self.state == CircuitState.CLOSED:
                if self.failure_count >= self.failure_threshold:
                    self._trip_open()
            elif self.state == CircuitState.HALF_OPEN:
                self._trip_open()

    async def record_success(self):
        async with self._lock:
            if self.state in (CircuitState.HALF_OPEN, CircuitState.CLOSED):
                self._close()

    async def try_half_open(self):
        """Called by health poller — transition OPEN → HALF_OPEN after timeout."""
        async with self._lock:
            if (
                self.state == CircuitState.OPEN
                and self.opened_at is not None
                and time.monotonic() - self.opened_at >= self.recovery_timeout
            ):
                self.state = CircuitState.HALF_OPEN
                logger.warning("[circuit] HALF_OPEN — probing Anthropic recovery")

    def _trip_open(self):
        self.state = CircuitState.OPEN
        self.opened_at = time.monotonic()
        logger.warning(
            f"[circuit] OPEN after {self.failure_count} failures — routing to Ollama fallback"
        )

    def _close(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.opened_at = None
        logger.info("[circuit] CLOSED — Anthropic recovered, resuming normal routing")

    @property
    def use_fallback(self) -> bool:
        return self.state == CircuitState.OPEN

    @property
    def status(self) -> dict:
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "opened_at": self.opened_at,
        }


# Singleton used across the app
circuit = CircuitBreaker()
