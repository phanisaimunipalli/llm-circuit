# llm-circuit

**Circuit breaker pattern for agentic LLM workflows.**
Automatic failover from Claude/Anthropic to local Ollama when the API goes down.

[![PyPI version](https://img.shields.io/pypi/v/llm-circuit.svg)](https://pypi.org/project/llm-circuit/)
[![Python](https://img.shields.io/pypi/pyversions/llm-circuit.svg)](https://pypi.org/project/llm-circuit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## The problem

On March 2, 2026, Anthropic experienced a global outage. For development teams using Claude Code as their primary coding agent, work stopped.

> *"For a 25-person engineering team billing at £90/hour, even a 4-hour disruption represented over £9,000 in lost productive capacity."*
> — DeployFlow analysis of the March 2026 outage

The workaround? Manually reconfigure your environment and restart. No tooling automated this. No fallback was built-in.

**llm-circuit fixes this.**

---

## What it does

llm-circuit is a transparent proxy that sits between your AI coding agent (Claude Code, Cursor, etc.) and the Anthropic API. It implements the **LLM Circuit Breaker Pattern** — the first application of the distributed systems circuit breaker to agentic LLM workflows.

When Anthropic's API is healthy, requests pass through unchanged.
When failures are detected, the circuit trips and all requests route to your local Ollama instance — automatically, with no restart, no reconfiguration, and no interruption to your workflow.

```
Normal:   Claude Code → llm-circuit → Anthropic API
Outage:   Claude Code → llm-circuit → Ollama (local)
Recovery: Claude Code → llm-circuit → Anthropic API  ← automatic
```

---

## Quick start

**Prerequisites:** Python 3.9+, [Ollama](https://ollama.ai) running locally with a model pulled (`ollama pull qwen2.5:14b`)

```bash
# Install
pip install llm-circuit

# Start the proxy
export ANTHROPIC_API_KEY=sk-ant-...  # API key users only
# Max plan / OAuth users: skip the line above — auth passes through automatically
llm-circuit start

# Point Claude Code at the proxy (in a new shell or your .zshrc)
export ANTHROPIC_BASE_URL=http://127.0.0.1:8742
```

That's the entire setup. Claude Code now has automatic failover.

---

## How it works

llm-circuit implements a three-state finite state machine:

```
                    3 consecutive failures
  ┌──────────┐ ─────────────────────────────► ┌──────────┐
  │  CLOSED  │                                 │   OPEN   │
  │ (normal) │ ◄─────────────────────────────  │(fallback)│
  └──────────┘         success                 └──────────┘
       ▲                                            │
       │                                     30s timeout
       │                                            │
       │              ┌───────────┐                 │
       └── success ── │ HALF_OPEN │ ◄───────────────┘
                      │  (probe)  │
                      └───────────┘
                           │
                        failure
                           │
                           ▼
                        ┌──────────┐
                        │   OPEN   │
                        └──────────┘
```

**CLOSED** — Requests go to Anthropic. Failures are counted.
**OPEN** — Requests go to Ollama. Circuit stays open for 30 seconds.
**HALF_OPEN** — One probe request goes to Anthropic. Success closes the circuit; failure keeps it open.

A background health poller runs every 5 seconds to detect recovery proactively — you don't have to wait for your next request to trigger the HALF_OPEN check.

---

## Configuration

All configuration via environment variables or a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | optional | API key users only — Max plan / OAuth users omit this |
| `ANTHROPIC_UPSTREAM_URL` | `https://api.anthropic.com` | Upstream Anthropic endpoint |
| `FALLBACK_OLLAMA_URL` | `http://localhost:11434` | Your Ollama instance |
| `FALLBACK_MODEL` | `qwen2.5:14b` | Model to use during fallback |
| `FAILURE_THRESHOLD` | `3` | Failures before circuit opens |
| `RECOVERY_TIMEOUT` | `30` | Seconds before probing recovery |
| `HEALTH_CHECK_INTERVAL` | `5` | Seconds between health polls |
| `PROXY_PORT` | `8742` | Port the proxy listens on |

---

## Inspect circuit state

```bash
curl http://127.0.0.1:8742/_llm_circuit/status
```

```json
{
  "circuit": {
    "state": "open",
    "failure_count": 3,
    "failure_threshold": 3
  },
  "upstream": "https://api.anthropic.com",
  "fallback": {
    "url": "http://localhost:11434",
    "model": "qwen2.5:14b"
  }
}
```

Responses routed through the fallback include the header `X-LLM-Circuit-Fallback: true`.

---

## The pattern

This project introduces the **LLM Circuit Breaker Pattern** — a new reliability primitive for agentic AI workflows. It adapts the classical circuit breaker from distributed systems to the specific semantics of LLM API dependencies: multi-turn conversations, streaming token output, and model name translation across providers.

Read the full pattern documentation: [`docs/the-pattern.md`](docs/the-pattern.md)

---

## Comparison with existing tools

| Tool | What it does | Auto-failover on outage? |
|---|---|---|
| LiteLLM proxy | Multi-provider routing | No — static config |
| claude-code-ollama-proxy | Route all traffic to Ollama | No — not reactive |
| **llm-circuit** | Health-monitored circuit breaker | **Yes — automatic** |

The key difference: llm-circuit reacts to runtime conditions. Others require manual reconfiguration.

---

## Works with

- [Claude Code](https://claude.ai/code) (Claude Code CLI)
- [Cursor](https://cursor.sh) (via `ANTHROPIC_BASE_URL`)
- Any tool that uses the Anthropic Messages API

See [`examples/`](examples/) for setup guides.

---

## Development

```bash
git clone https://github.com/phanisaimunipalli/llm-circuit
cd llm-circuit
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs welcome — especially for additional fallback providers, context preservation, and observability.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Citation

If you use llm-circuit in research or reference the LLM Circuit Breaker Pattern, please cite:

```
Munipalli, Phani Sai Ram. "llm-circuit: Circuit Breaker Pattern for Agentic LLM Workflows."
GitHub, 2026. https://github.com/phanisaimunipalli/llm-circuit
```
