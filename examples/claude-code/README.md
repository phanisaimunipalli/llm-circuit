# Using llm-circuit with Claude Code

## Setup (60 seconds)

**1. Install and start the proxy**

```bash
pip install llm-circuit

export ANTHROPIC_API_KEY=sk-ant-...
export FALLBACK_OLLAMA_URL=http://localhost:11434  # default
export FALLBACK_MODEL=qwen2.5:14b                 # default

llm-circuit start
# Proxy is now listening on http://127.0.0.1:8742
```

**2. Point Claude Code at the proxy**

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8742
claude  # or claude-code, depending on your install
```

That's it. Claude Code now routes through llm-circuit.

---

## What happens during an outage

Normal operation (circuit CLOSED):
```
Claude Code → llm-circuit → Anthropic API → response
```

During an outage (circuit OPEN):
```
Claude Code → llm-circuit → Ollama (local) → response
```

You keep coding. The proxy handles the switch automatically.

---

## Check circuit status

```bash
curl http://127.0.0.1:8742/_llm_circuit/status
```

```json
{
  "circuit": {
    "state": "closed",
    "failure_count": 0,
    "failure_threshold": 3
  },
  "upstream": "https://api.anthropic.com",
  "fallback": {
    "url": "http://localhost:11434",
    "model": "qwen2.5:14b"
  }
}
```

When the circuit is OPEN, `state` will be `"open"` and responses will include the header `X-LLM-Circuit-Fallback: true`.

---

## Make it permanent (add to shell profile)

```bash
# ~/.zshrc or ~/.bashrc
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_BASE_URL=http://127.0.0.1:8742
```

Start llm-circuit as a background service and it runs silently all day.

---

## Ollama model recommendations

| Use case | Recommended model |
|---|---|
| General coding | `qwen2.5:14b` |
| Faster responses | `qwen2.5:7b` |
| Complex reasoning | `qwen2.5:32b` |
| Code-focused | `deepseek-coder-v2:16b` |

Pull a model:
```bash
ollama pull qwen2.5:14b
```
