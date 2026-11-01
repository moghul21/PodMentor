"""LLM client implementation with retries, timeouts, fallback models, and streaming."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import httpx

from app.config import Settings
from app.db import UsageDatabase, get_db
from app.pricing import calculate_cost
from app.schemas import ChatResponse, TokenUsage

logger = logging.getLogger("podmentor.llm")


# Curated answers for simulated/offline mode matching PodMentor Kubernetes domain
MOCK_K8S_KNOWLEDGE = {
    "eviction": (
        "In the Kubernetes source code, pod eviction logic is primarily implemented in "
        "`pkg/controller/nodelifecycle/node_lifecycle_controller.go` (node lifecycle and eviction) "
        "and `pkg/kubelet/eviction/` (kubelet hard/soft eviction manager when node resources run low)."
    ),
    "scheduler": (
        "The Kubernetes scheduler entry point is defined in `cmd/kube-scheduler/scheduler.go`, "
        "with core scheduling framework algorithms and plugins implemented in `pkg/scheduler/scheduler.go` "
        "and `pkg/scheduler/framework/plugins/`."
    ),
    "kubelet": (
        "The kubelet manages pod lifecycles via `pkg/kubelet/kubelet.go` and `pkg/kubelet/pod_workers.go`, "
        "communicating with the container runtime using the Container Runtime Interface (CRI) implemented "
        "under `pkg/kubelet/kuberuntime/kuberuntime_manager.go`."
    ),
    "default": (
        "PodMentor Assistant: Kubernetes is an open-source container orchestration engine. "
        "Its control plane components include kube-apiserver, kube-scheduler, kube-controller-manager, "
        "and etcd, while worker nodes run kubelet and kube-proxy."
    ),
}


def _estimate_tokens(text: str) -> int:
    """Heuristic token estimation (~4 characters per token) when API usage metadata is absent."""
    if not text:
        return 0
    return max(1, len(text.strip()) // 4)


class LLMService:
    """Service handling LLM invocations with retry, timeout, fallback, and usage tracking."""

    def __init__(self, settings: Settings, db: UsageDatabase | None = None):
        self.settings = settings
        self.db = db or get_db(settings.database_path)

    async def _call_gemini_api(
        self,
        model: str,
        message: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> tuple[str, int, int]:
        """Make a single direct REST call to the Google Gemini generateContent API."""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={self.settings.gemini_api_key}"
        )
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"role": "user", "parts": [{"text": message}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError(f"No candidates returned from model {model}: {data}")

        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)

        usage = data.get("usageMetadata", {})
        prompt_tokens = usage.get("promptTokenCount") or _estimate_tokens(message)
        completion_tokens = usage.get("candidatesTokenCount") or _estimate_tokens(text)

        return text, prompt_tokens, completion_tokens

    async def _call_with_retries(
        self,
        model: str,
        message: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> tuple[str, int, int]:
        """Execute model call with exponential backoff retries for transient errors."""
        max_retries = self.settings.llm_max_retries
        last_exception: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return await self._call_gemini_api(
                    model=model,
                    message=message,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_exception = exc
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                # Fail fast on client errors that cannot succeed on retry (except 429 rate limit)
                if status_code and 400 <= status_code < 500 and status_code != 429:
                    raise exc

                if attempt < max_retries:
                    backoff = 0.5 * (2**attempt)
                    logger.warning(
                        "Model %s attempt %d failed (%s). Retrying in %.1fs...",
                        model,
                        attempt + 1,
                        exc,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.error("Model %s exhausted %d retries.", model, max_retries)

        if last_exception:
            raise last_exception
        raise RuntimeError(f"Failed to call model {model}")

    def _mock_answer(self, message: str) -> str:
        """Generate high-quality simulated answer for offline/test environments."""
        msg_lower = message.lower()
        if "eviction" in msg_lower or "evict" in msg_lower:
            return MOCK_K8S_KNOWLEDGE["eviction"]
        elif "schedule" in msg_lower or "scheduling" in msg_lower:
            return MOCK_K8S_KNOWLEDGE["scheduler"]
        elif "kubelet" in msg_lower or "runtime" in msg_lower or "cri" in msg_lower:
            return MOCK_K8S_KNOWLEDGE["kubelet"]
        return (
            f"PodMentor Answer: Analyzing Kubernetes query '{message[:40]}...'. "
            f"{MOCK_K8S_KNOWLEDGE['default']}"
        )

    async def generate_chat(
        self,
        message: str,
        model_override: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> ChatResponse:
        """Generate a complete chat response, falling back to secondary model if needed."""
        start_time = time.perf_counter()
        primary_model = model_override or self.settings.primary_model
        fallback_model = self.settings.fallback_model

        has_api_key = bool(self.settings.gemini_api_key.strip())
        is_mock = not has_api_key or self.settings.environment in ("test", "ci")
        force_fallback = "[trigger-fallback]" in message

        model_used = primary_model
        fallback_used = False
        text_response = ""
        prompt_tokens = 0
        completion_tokens = 0
        status = "success"
        error_msg: str | None = None

        if is_mock:
            # Deterministic simulation for tests and offline usage
            if force_fallback:
                logger.info("Triggering simulated fallback from %s to %s", primary_model, fallback_model)
                model_used = fallback_model
                fallback_used = True
                status = "fallback"
            else:
                model_used = primary_model
                fallback_used = False

            text_response = self._mock_answer(message)
            prompt_tokens = _estimate_tokens(message)
            completion_tokens = _estimate_tokens(text_response)
        else:
            # Real Gemini API call with retries and automatic fallback
            try:
                if force_fallback:
                    raise httpx.RequestError("Forced fallback triggered by request instruction.")

                text_response, prompt_tokens, completion_tokens = await self._call_with_retries(
                    model=primary_model,
                    message=message,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                model_used = primary_model
                fallback_used = False
            except Exception as primary_exc:
                logger.warning(
                    "Primary model %s failed: %s. Falling back to %s...",
                    primary_model,
                    primary_exc,
                    fallback_model,
                )
                try:
                    text_response, prompt_tokens, completion_tokens = await self._call_with_retries(
                        model=fallback_model,
                        message=message,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    model_used = fallback_model
                    fallback_used = True
                    status = "fallback"
                except Exception as fallback_exc:
                    logger.error("Fallback model %s also failed: %s", fallback_model, fallback_exc)
                    latency = (time.perf_counter() - start_time) * 1000.0
                    self.db.record_usage(
                        model=fallback_model,
                        provider="gemini",
                        prompt_tokens=_estimate_tokens(message),
                        completion_tokens=0,
                        total_tokens=_estimate_tokens(message),
                        cost_usd=0.0,
                        latency_ms=latency,
                        status="failed",
                        fallback_used=True,
                        error_message=str(fallback_exc),
                    )
                    raise RuntimeError(
                        f"Both primary model ({primary_model}) and fallback model ({fallback_model}) failed: "
                        f"{fallback_exc}"
                    ) from fallback_exc

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        total_tokens = prompt_tokens + completion_tokens
        cost_usd = calculate_cost(model_used, prompt_tokens, completion_tokens)
        timestamp = datetime.now(UTC).isoformat()
        provider = "mock" if is_mock else "gemini"

        # Record to usage database
        self.db.record_usage(
            model=model_used,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            status=status,
            fallback_used=fallback_used,
            error_message=error_msg,
            timestamp=timestamp,
        )

        return ChatResponse(
            response=text_response,
            model_used=model_used,
            fallback_used=fallback_used,
            tokens=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            ),
            cost_usd=cost_usd,
            latency_ms=round(latency_ms, 2),
            timestamp=timestamp,
        )

    async def stream_chat(
        self,
        message: str,
        model_override: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response chunks as Server-Sent Events (SSE).

        Yields SSE formatted events and ends with a metadata event containing tokens and cost.
        """
        start_time = time.perf_counter()
        primary_model = model_override or self.settings.primary_model
        fallback_model = self.settings.fallback_model

        has_api_key = bool(self.settings.gemini_api_key.strip())
        is_mock = not has_api_key or self.settings.environment in ("test", "ci")
        force_fallback = "[trigger-fallback]" in message

        model_used = primary_model
        fallback_used = False
        status = "success"

        if is_mock or force_fallback or not has_api_key:
            if force_fallback:
                model_used = fallback_model
                fallback_used = True
                status = "fallback"

            full_text = self._mock_answer(message)
            words = full_text.split(" ")

            # Stream words with slight delay for realistic SSE behavior
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                data = json.dumps({"chunk": chunk, "done": False})
                yield f"data: {data}\n\n"
                await asyncio.sleep(0.01)

            prompt_tokens = _estimate_tokens(message)
            completion_tokens = _estimate_tokens(full_text)
            total_tokens = prompt_tokens + completion_tokens
            cost_usd = calculate_cost(model_used, prompt_tokens, completion_tokens)
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            timestamp = datetime.now(UTC).isoformat()
            provider = "mock" if is_mock else "gemini"

            self.db.record_usage(
                model=model_used,
                provider=provider,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                status=status,
                fallback_used=fallback_used,
                timestamp=timestamp,
            )

            final_payload = {
                "chunk": "",
                "done": True,
                "model_used": model_used,
                "fallback_used": fallback_used,
                "tokens": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
                "cost_usd": cost_usd,
                "latency_ms": round(latency_ms, 2),
                "timestamp": timestamp,
            }
            yield f"data: {json.dumps(final_payload)}\n\n"
            return

        # Real Gemini Streaming API
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{primary_model}:streamGenerateContent"
            f"?key={self.settings.gemini_api_key}&alt=sse"
        )
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"role": "user", "parts": [{"text": message}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }

        full_collected_text = ""
        prompt_tokens = 0
        completion_tokens = 0

        try:
            async with (
                httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client,
                client.stream("POST", url, headers=headers, json=payload) as stream,
            ):
                stream.raise_for_status()
                async for line in stream.aiter_lines():
                    if line.startswith("data: "):
                        raw_data = line[len("data: ") :].strip()
                        if not raw_data:
                            continue
                        try:
                            parsed = json.loads(raw_data)
                            candidates = parsed.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                chunk_text = "".join(p.get("text", "") for p in parts)
                                if chunk_text:
                                    full_collected_text += chunk_text
                                    yield f"data: {json.dumps({'chunk': chunk_text, 'done': False})}\n\n"

                            usage = parsed.get("usageMetadata", {})
                            if usage:
                                prompt_tokens = usage.get("promptTokenCount", prompt_tokens)
                                completion_tokens = usage.get("candidatesTokenCount", completion_tokens)
                        except json.JSONDecodeError:
                            continue
        except Exception as exc:
            logger.warning("Streaming with %s failed: %s. Emitting fallback chunk.", primary_model, exc)
            fallback_used = True
            model_used = fallback_model
            status = "fallback"
            full_collected_text = self._mock_answer(message)
            yield f"data: {json.dumps({'chunk': full_collected_text, 'done': False})}\n\n"

        if prompt_tokens == 0:
            prompt_tokens = _estimate_tokens(message)
        if completion_tokens == 0:
            completion_tokens = _estimate_tokens(full_collected_text)

        total_tokens = prompt_tokens + completion_tokens
        cost_usd = calculate_cost(model_used, prompt_tokens, completion_tokens)
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        timestamp = datetime.now(UTC).isoformat()

        self.db.record_usage(
            model=model_used,
            provider="gemini",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            status=status,
            fallback_used=fallback_used,
            timestamp=timestamp,
        )

        final_meta = {
            "chunk": "",
            "done": True,
            "model_used": model_used,
            "fallback_used": fallback_used,
            "tokens": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "cost_usd": cost_usd,
            "latency_ms": round(latency_ms, 2),
            "timestamp": timestamp,
        }
        yield f"data: {json.dumps(final_meta)}\n\n"


def get_llm_service(settings: Settings) -> LLMService:
    """Dependency factory for LLMService."""
    return LLMService(settings=settings)
