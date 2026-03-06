# The LLM Circuit Breaker Pattern

*A new reliability primitive for agentic AI development workflows.*

---

## Background

The circuit breaker is a well-established pattern in distributed systems, first formalized by Michael Nygard in *Release It!* (2007). It prevents cascading failures by detecting when a downstream service is unhealthy and stopping requests from flowing to it — giving the service time to recover while keeping the caller functional.

Until now, this pattern has not been applied to the emerging class of **agentic LLM workflows** — developer tools like Claude Code, Cursor, and GitHub Copilot that depend on cloud-hosted language models as a real-time creative partner during active work sessions.

This document defines the **LLM Circuit Breaker Pattern**: a formal adaptation of the circuit breaker for LLM API dependencies.

---

## The Problem

Modern AI coding agents create a new class of infrastructure dependency. Unlike a traditional microservice dependency — where failure causes a degraded experience — failure of an LLM provider dependency **terminates the developer's ability to work**. The AI coding agent is not a feature; it is the primary tool.

This creates an asymmetric risk: LLM providers are operated by third parties, may experience outages (documented publicly), and cannot be replicated locally without significant effort. Meanwhile, a developer's workflow — their code context, their working memory, their active task — lives on the client side.

When the API goes down, the developer's environment is functional. Only the AI connectivity is broken. Yet no tooling exists to detect this and route around it.

---

## The Pattern

### States

The LLM Circuit Breaker operates as a finite state machine with three states:

```
  CLOSED ──[N failures]──► OPEN ──[timeout]──► HALF_OPEN
    ▲                                               │
    └───────────[success]──────────────────────────┘
```

**CLOSED** (normal operation)
All requests route to the primary LLM provider (e.g. Anthropic). Failures are counted. When N consecutive failures occur, the circuit trips to OPEN.

**OPEN** (outage mode)
All requests are immediately routed to the fallback provider (e.g. local Ollama). No requests are sent to the primary. The circuit remains open for a configurable recovery timeout.

**HALF_OPEN** (recovery probe)
After the timeout, one request is sent to the primary provider as a probe. Success → CLOSED (resume normal routing). Failure → OPEN (restart the timeout).

### Triggers

A failure is recorded when:
- The primary API returns HTTP 5xx
- A connection timeout or DNS resolution failure occurs
- The background health poller detects the host is unreachable

A success is recorded when:
- A request to the primary API returns HTTP < 500
- The background health poller receives a valid HTTP response

### Health Polling

Unlike classical circuit breakers that are purely reactive (triggered by actual requests), the LLM Circuit Breaker includes a **proactive health poller** — a background task that independently monitors the upstream API. This is important because:

1. Agentic workflows may have periods of silence between requests
2. Recovery should be detected as soon as it happens, not on the next user action
3. The OPEN → HALF_OPEN transition should be time-driven, not request-driven

---

## Why This Is Different From Existing Proxies

Static LLM proxies (LiteLLM, ollama-proxy) require manual configuration and do not react to runtime conditions. You configure them before you start and they do not change behavior based on what's happening.

The LLM Circuit Breaker is **reactive and automatic**:
- No manual intervention when Anthropic goes down
- No restart required
- No re-configuration
- Developer keeps working without knowing an outage occurred

---

## Implementation Considerations

### Request Translation

When routing to a fallback model, the request must be translated between API formats. The key challenge is **preserving semantic equivalence** — the fallback model must receive enough context to continue the task coherently.

Key translation points (Anthropic → Ollama):
- System prompt: top-level field → `{"role": "system"}` in messages array
- Model name: Claude identifier → local model identifier
- Streaming: Anthropic SSE event format → Ollama NDJSON → back to Anthropic SSE

### Streaming

Streaming is the primary consumption mode for AI coding agents. The circuit breaker must handle mid-stream failures gracefully. If Anthropic fails during an active stream:
1. The failure is recorded
2. The circuit may trip to OPEN
3. The client (Claude Code) receives an error event and retries
4. The retry is routed to the fallback

Full mid-stream fallover (transparent to the client) is a future enhancement.

### Model Fidelity

Local fallback models (e.g. `qwen2.5:14b`) have different capability profiles than frontier models. This is an intentional tradeoff: **partial capability during an outage is better than zero capability**. Developers can complete simpler tasks, review code, and maintain context while waiting for the primary provider to recover.

---

## Relation to Distributed Systems Patterns

The LLM Circuit Breaker Pattern is an application of:
- **Circuit Breaker** (Nygard, 2007) — state machine, failure threshold, recovery probe
- **Bulkhead** — routing to a separate pool (Ollama) when the primary fails
- **Health Endpoint Monitoring** — active probing rather than passive detection

It differs from prior art in its domain specificity: the pattern is designed for the **request/response semantics of language model APIs**, including multi-turn conversation context, streaming tokens, and model name translation.

---

## Future Work

1. **Context-preserving failover** — pass accumulated conversation context to the fallback model to maintain session continuity
2. **Multi-tier fallback chains** — Anthropic → OpenAI → Ollama, with automatic progression
3. **Per-model circuit breakers** — independent breakers for different Claude models
4. **Metrics and observability** — failover event history, latency distributions, token cost comparisons
