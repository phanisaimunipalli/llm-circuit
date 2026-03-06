# Contributing to llm-circuit

## Getting started

```bash
git clone https://github.com/phanisaimunipalli/llm-circuit
cd llm-circuit
pip install -e ".[dev]"
```

## Running tests

```bash
pytest tests/ -v
```

## Project structure

- `llm_circuit/circuit.py` — Circuit breaker state machine (core logic)
- `llm_circuit/health.py` — Background health poller
- `llm_circuit/router.py` — Anthropic ↔ Ollama request/response translation
- `llm_circuit/proxy.py` — FastAPI app, routing logic
- `llm_circuit/config.py` — Environment variable configuration
- `docs/the-pattern.md` — Conceptual paper on the pattern

## How to contribute

1. Open an issue describing the problem or enhancement
2. Fork the repo and create a branch
3. Write tests for your change
4. Submit a PR referencing the issue

## Areas most needed

- Additional fallback providers (OpenAI, Gemini)
- Context preservation across provider switches
- Dashboard / status UI
- Cursor and Windsurf integration guides
- Benchmarks comparing fallback model performance
