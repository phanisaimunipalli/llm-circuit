"""
FastAPI proxy server.

All requests from Claude Code hit this server.
/v1/messages is intercepted and routed based on circuit state.
All other paths are passed through to Anthropic unchanged.
"""

import json
import uuid
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

from .config import settings
from .circuit import circuit
from .health import health_check_loop
from .router import (
    anthropic_to_ollama,
    ollama_to_anthropic_response,
    stream_ollama_as_anthropic,
)

logger = logging.getLogger("llm_circuit.proxy")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    task = asyncio.create_task(health_check_loop())
    logger.info("=" * 55)
    logger.info("  llm-circuit proxy started")
    logger.info(f"  Listening : http://{settings.proxy_host}:{settings.proxy_port}")
    logger.info(f"  Upstream  : {settings.anthropic_upstream_url}")
    logger.info(f"  Fallback  : {settings.fallback_ollama_url} ({settings.fallback_model})")
    logger.info(f"  Threshold : {settings.failure_threshold} failures → OPEN")
    logger.info(f"  Recovery  : {settings.recovery_timeout}s timeout → HALF_OPEN")
    logger.info("=" * 55)
    yield
    task.cancel()


app = FastAPI(title="llm-circuit", version="0.1.0", lifespan=lifespan)


@app.get("/_llm_circuit/status")
async def status():
    """Health endpoint — inspect circuit state."""
    return {
        "circuit": circuit.status,
        "upstream": settings.anthropic_upstream_url,
        "fallback": {
            "url": settings.fallback_ollama_url,
            "model": settings.fallback_model,
        },
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    body_bytes = await request.body()

    # Only intercept the messages endpoint
    if path == "v1/messages" and request.method == "POST":
        body = json.loads(body_bytes) if body_bytes else {}
        is_streaming = body.get("stream", False)

        if circuit.use_fallback:
            logger.info(f"[proxy] Circuit OPEN — sending to Ollama fallback")
            return await route_to_ollama(body, is_streaming)

        return await route_to_anthropic(request, path, body_bytes, body, is_streaming)

    # All other paths: transparent passthrough
    return await passthrough(request, path, body_bytes)


async def route_to_anthropic(
    request: Request,
    path: str,
    body_bytes: bytes,
    body: dict,
    is_streaming: bool,
):
    headers = _forward_headers(request)
    url = f"{settings.anthropic_upstream_url}/{path}"

    try:
        if is_streaming:
            return StreamingResponse(
                _stream_anthropic(url, request.method, body_bytes, headers, body, is_streaming),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        else:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.request(
                    request.method, url, content=body_bytes, headers=headers
                )
                if resp.status_code >= 500:
                    await circuit.record_failure()
                    logger.warning(f"[proxy] Anthropic HTTP {resp.status_code} — recording failure")
                else:
                    await circuit.record_success()
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                )

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.warning(f"[proxy] Anthropic unreachable: {e} — switching to fallback")
        await circuit.record_failure()
        return await route_to_ollama(body, is_streaming)


async def _stream_anthropic(url, method, body_bytes, headers, body, is_streaming):
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(method, url, content=body_bytes, headers=headers) as resp:
                if resp.status_code >= 500:
                    await circuit.record_failure()
                    # Yield an Anthropic-shaped error event so Claude Code handles it gracefully
                    error = json.dumps({
                        "type": "error",
                        "error": {"type": "api_error", "message": "Upstream unavailable"},
                    })
                    yield f"event: error\ndata: {error}\n\n".encode()
                    return
                async for chunk in resp.aiter_bytes():
                    yield chunk
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        await circuit.record_failure()
        logger.warning(f"[proxy] Stream to Anthropic failed: {e} — falling back mid-stream")
        msg_id = f"msg_{uuid.uuid4().hex[:24]}"
        ollama_body = anthropic_to_ollama(body)
        original_model = body.get("model", "unknown")
        async for chunk in stream_ollama_as_anthropic(ollama_body, original_model, msg_id):
            yield chunk


async def route_to_ollama(body: dict, is_streaming: bool):
    original_model = body.get("model", "unknown")
    ollama_body = anthropic_to_ollama(body)
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    fallback_headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "X-LLM-Circuit-Fallback": "true",
        "X-LLM-Circuit-Model": settings.fallback_model,
    }

    if is_streaming:
        return StreamingResponse(
            stream_ollama_as_anthropic(ollama_body, original_model, msg_id),
            media_type="text/event-stream",
            headers=fallback_headers,
        )
    else:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.fallback_ollama_url}/api/chat",
                json={**ollama_body, "stream": False},
            )
        result = ollama_to_anthropic_response(resp.json(), original_model)
        return Response(
            content=json.dumps(result),
            status_code=200,
            media_type="application/json",
            headers=fallback_headers,
        )


async def passthrough(request: Request, path: str, body_bytes: bytes):
    headers = _forward_headers(request)
    url = f"{settings.anthropic_upstream_url}/{path}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.request(request.method, url, content=body_bytes, headers=headers)
    return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))


def _forward_headers(request: Request) -> dict:
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length", "transfer-encoding")
    }
    # Always inject the real API key
    headers["x-api-key"] = settings.anthropic_api_key
    return headers
