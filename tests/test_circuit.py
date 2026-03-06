"""
Tests for the CircuitBreaker state machine.

Verifies all state transitions:
  CLOSED → OPEN → HALF_OPEN → CLOSED
  CLOSED → OPEN → HALF_OPEN → OPEN
"""

import asyncio
import time
import pytest

from llm_circuit.circuit import CircuitBreaker, CircuitState


@pytest.fixture
def breaker():
    return CircuitBreaker(failure_threshold=3, recovery_timeout=1)


# -- Initial state --

def test_initial_state_is_closed(breaker):
    assert breaker.state == CircuitState.CLOSED
    assert not breaker.use_fallback
    assert breaker.failure_count == 0


# -- CLOSED → OPEN --

@pytest.mark.asyncio
async def test_opens_after_failure_threshold(breaker):
    for _ in range(3):
        await breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.use_fallback


@pytest.mark.asyncio
async def test_stays_closed_below_threshold(breaker):
    await breaker.record_failure()
    await breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    assert not breaker.use_fallback


# -- OPEN → HALF_OPEN --

@pytest.mark.asyncio
async def test_no_half_open_before_timeout(breaker):
    for _ in range(3):
        await breaker.record_failure()
    await breaker.try_half_open()  # too soon
    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_transitions_to_half_open_after_timeout(breaker):
    for _ in range(3):
        await breaker.record_failure()
    await asyncio.sleep(1.1)
    await breaker.try_half_open()
    assert breaker.state == CircuitState.HALF_OPEN


# -- HALF_OPEN → CLOSED --

@pytest.mark.asyncio
async def test_closes_on_success_from_half_open(breaker):
    for _ in range(3):
        await breaker.record_failure()
    await asyncio.sleep(1.1)
    await breaker.try_half_open()
    await breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert not breaker.use_fallback
    assert breaker.failure_count == 0


# -- HALF_OPEN → OPEN --

@pytest.mark.asyncio
async def test_reopens_on_failure_from_half_open(breaker):
    for _ in range(3):
        await breaker.record_failure()
    await asyncio.sleep(1.1)
    await breaker.try_half_open()
    await breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.use_fallback


# -- Status dict --

@pytest.mark.asyncio
async def test_status_reflects_state(breaker):
    status = breaker.status
    assert status["state"] == "closed"
    assert status["failure_count"] == 0
    assert status["failure_threshold"] == 3
