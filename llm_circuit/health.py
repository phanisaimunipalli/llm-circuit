"""
Background health poller.

Polls the Anthropic API every N seconds.
Updates circuit breaker state on success/failure.
"""

import asyncio
import logging
import httpx

from .config import settings
from .circuit import circuit

logger = logging.getLogger("llm_circuit.health")


async def health_check_loop():
    """Runs as a background asyncio task for the lifetime of the proxy."""
    logger.info(
        f"[health] Polling {settings.anthropic_upstream_url} "
        f"every {settings.health_check_interval}s"
    )

    while True:
        await asyncio.sleep(settings.health_check_interval)

        # Attempt OPEN → HALF_OPEN transition if timeout has elapsed
        await circuit.try_half_open()

        # Only probe when CLOSED or HALF_OPEN
        if circuit.use_fallback:
            continue

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    settings.anthropic_upstream_url,
                    headers={"anthropic-version": "2023-06-01"},
                    follow_redirects=True,
                )
                # Any HTTP response (even 401/404) means the server is reachable
                if resp.status_code < 500:
                    await circuit.record_success()
                    logger.debug(f"[health] OK (HTTP {resp.status_code})")
                else:
                    await circuit.record_failure()
                    logger.warning(f"[health] Server error: HTTP {resp.status_code}")

        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
            await circuit.record_failure()
            logger.warning(f"[health] Unreachable: {e}")
