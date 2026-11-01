import json


def test_chat_basic_structured_json(client):
    """POST /chat returns structured JSON with model, tokens, cost, and latency."""
    payload = {
        "message": "Where is the pod eviction code implemented in the Kubernetes source?",
        "stream": False,
    }
    r = client.post("/chat", json=payload)
    assert r.status_code == 200
    data = r.json()

    assert "response" in data
    assert "eviction" in data["response"].lower() or "pkg/controller" in data["response"]
    assert data["model_used"] == "gemini-1.5-flash"
    assert data["fallback_used"] is False

    tokens = data["tokens"]
    assert tokens["prompt_tokens"] > 0
    assert tokens["completion_tokens"] > 0
    assert tokens["total_tokens"] == tokens["prompt_tokens"] + tokens["completion_tokens"]

    assert data["cost_usd"] > 0.0
    assert data["latency_ms"] >= 0.0
    assert "timestamp" in data


def test_chat_fallback_routing(client):
    """POST /chat routes to fallback model when primary model encounters failure."""
    payload = {
        "message": "Where is the scheduler defined? [trigger-fallback]",
        "stream": False,
    }
    r = client.post("/chat", json=payload)
    assert r.status_code == 200
    data = r.json()

    assert data["fallback_used"] is True
    assert data["model_used"] == "gemini-1.5-flash-8b"
    assert data["tokens"]["total_tokens"] > 0
    assert data["cost_usd"] > 0.0


def test_chat_streaming_sse(client):
    """POST /chat with stream=True returns Server-Sent Events stream."""
    payload = {
        "message": "How does the kubelet manage pods?",
        "stream": True,
    }
    r = client.post("/chat", json=payload)
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]

    lines = r.text.strip().split("\n\n")
    events = []
    for line in lines:
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))

    assert len(events) >= 2
    # Intermediate text chunks
    content_chunks = [e["chunk"] for e in events if not e.get("done", False)]
    assert len(content_chunks) > 0
    full_text = "".join(content_chunks)
    assert "kubelet" in full_text.lower()

    # Final metadata chunk
    final_event = events[-1]
    assert final_event.get("done") is True
    assert final_event["model_used"] == "gemini-1.5-flash"
    assert final_event["fallback_used"] is False
    assert final_event["tokens"]["total_tokens"] > 0
    assert final_event["cost_usd"] > 0.0


def test_chat_streaming_fallback(client):
    """POST /chat streaming triggers fallback when requested."""
    payload = {
        "message": "Explain scheduler scoring. [trigger-fallback]",
        "stream": True,
    }
    r = client.post("/chat", json=payload)
    assert r.status_code == 200

    lines = r.text.strip().split("\n\n")
    events = [json.loads(line[len("data: ") :]) for line in lines if line.startswith("data: ")]
    final_event = events[-1]

    assert final_event["done"] is True
    assert final_event["model_used"] == "gemini-1.5-flash-8b"
    assert final_event["fallback_used"] is True


def test_chat_empty_message_validation(client):
    """Empty message should return 422 Unprocessable Entity."""
    r = client.post("/chat", json={"message": "", "stream": False})
    assert r.status_code == 422
