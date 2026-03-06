"""
Request/response translation between Anthropic and Ollama API formats.

Anthropic Messages API  →  Ollama Chat API
  POST /v1/messages          POST /api/chat

Key differences:
  - Anthropic: system prompt is a top-level field
  - Ollama:    system prompt goes as {"role": "system"} in messages array
  - Anthropic streaming: SSE with typed events (message_start, content_block_delta, ...)
  - Ollama streaming:    newline-delimited JSON
"""

import json
import uuid
import logging
from typing import AsyncIterator

import httpx

from .config import settings

logger = logging.getLogger("llm_circuit.router")

# Maps Claude model names → Ollama model names
MODEL_MAP: dict[str, str] = {
    "claude-opus-4-6": settings.fallback_model,
    "claude-sonnet-4-6": settings.fallback_model,
    "claude-haiku-4-5": settings.fallback_model,
    "claude-haiku-4-5-20251001": settings.fallback_model,
    # Legacy names
    "claude-3-opus-20240229": settings.fallback_model,
    "claude-3-5-sonnet-20241022": settings.fallback_model,
    "claude-3-haiku-20240307": settings.fallback_model,
}


def map_model(anthropic_model: str) -> str:
    return MODEL_MAP.get(anthropic_model, settings.fallback_model)


def anthropic_to_ollama(body: dict) -> dict:
    """Translate Anthropic /v1/messages request body → Ollama /api/chat body."""
    messages = list(body.get("messages", []))

    # Anthropic top-level system field → Ollama system message
    if system := body.get("system"):
        messages = [{"role": "system", "content": system}] + messages

    return {
        "model": map_model(body.get("model", "")),
        "messages": messages,
        "stream": body.get("stream", False),
        "options": {
            "num_predict": body.get("max_tokens", 4096),
            "temperature": body.get("temperature", 1.0),
        },
    }


def ollama_to_anthropic_response(ollama_resp: dict, original_model: str) -> dict:
    """Translate Ollama non-streaming response → Anthropic response shape."""
    content = ollama_resp.get("message", {}).get("content", "")
    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content}],
        "model": original_model,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": ollama_resp.get("prompt_eval_count", 0),
            "output_tokens": ollama_resp.get("eval_count", 0),
        },
    }


async def stream_ollama_as_anthropic(
    ollama_body: dict,
    original_model: str,
    msg_id: str,
) -> AsyncIterator[bytes]:
    """
    Stream Ollama's NDJSON response translated into Anthropic SSE format.

    Anthropic SSE event sequence:
      message_start → content_block_start → ping →
      content_block_delta* → content_block_stop →
      message_delta → message_stop
    """

    def sse(event: str, data: dict) -> bytes:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()

    # message_start
    yield sse("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": original_model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
    })

    # content_block_start
    yield sse("content_block_start", {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "text", "text": ""},
    })

    yield sse("ping", {"type": "ping"})

    output_tokens = 0
    input_tokens = 0

    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream(
            "POST",
            f"{settings.fallback_ollama_url}/api/chat",
            json=ollama_body,
        ) as resp:
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not chunk.get("done"):
                    text = chunk.get("message", {}).get("content", "")
                    if text:
                        output_tokens += 1
                        yield sse("content_block_delta", {
                            "type": "content_block_delta",
                            "index": 0,
                            "delta": {"type": "text_delta", "text": text},
                        })
                else:
                    input_tokens = chunk.get("prompt_eval_count", 0)
                    output_tokens = chunk.get("eval_count", output_tokens)

    # content_block_stop
    yield sse("content_block_stop", {"type": "content_block_stop", "index": 0})

    # message_delta
    yield sse("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": output_tokens},
    })

    # message_stop
    yield sse("message_stop", {"type": "message_stop"})

    logger.info(
        f"[fallback] Ollama stream complete — "
        f"in={input_tokens} out={output_tokens} tokens"
    )
