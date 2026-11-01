from app.pricing import calculate_cost


def test_calculate_cost_accuracy():
    """Verify pricing math for Gemini models against official rate cards."""
    # gemini-1.5-flash: $0.075 / 1M input, $0.30 / 1M output
    cost_flash = calculate_cost("gemini-1.5-flash", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost_flash == 0.375

    # gemini-1.5-flash-8b: $0.0375 / 1M input, $0.15 / 1M output
    cost_8b = calculate_cost("gemini-1.5-flash-8b", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost_8b == 0.1875

    # Smaller token amounts
    small_cost = calculate_cost("gemini-1.5-flash", prompt_tokens=1000, completion_tokens=2000)
    expected = (1000 / 1_000_000.0 * 0.075) + (2000 / 1_000_000.0 * 0.30)
    assert abs(small_cost - expected) < 1e-8


def test_usage_empty_state(client):
    """GET /usage returns empty totals when no chat calls have run."""
    r = client.get("/usage")
    assert r.status_code == 200
    data = r.json()
    assert data["total_requests"] == 0
    assert data["total_tokens"] == 0
    assert data["total_cost_usd"] == 0.0
    assert data["by_model"] == {}
    assert data["recent_requests"] == []


def test_usage_tracking_across_calls(client):
    """GET /usage accumulates tokens and costs across multiple chat and streaming requests."""
    # 1. Normal call (Primary model)
    r1 = client.post(
        "/chat",
        json={"message": "Where is the API server handler implemented?", "stream": False},
    )
    assert r1.status_code == 200
    cost1 = r1.json()["cost_usd"]
    tokens1 = r1.json()["tokens"]["total_tokens"]

    # 2. Fallback call (Fallback model)
    r2 = client.post(
        "/chat",
        json={"message": "Why does a pod stay in Pending? [trigger-fallback]", "stream": False},
    )
    assert r2.status_code == 200
    cost2 = r2.json()["cost_usd"]
    tokens2 = r2.json()["tokens"]["total_tokens"]

    # 3. Streaming call
    r3 = client.post(
        "/chat",
        json={"message": "How does Kubernetes handle node failure?", "stream": True},
    )
    assert r3.status_code == 200

    # 4. Check GET /usage
    r_usage = client.get("/usage")
    assert r_usage.status_code == 200
    usage = r_usage.json()

    assert usage["total_requests"] == 3
    assert usage["total_tokens"] >= tokens1 + tokens2
    assert usage["total_cost_usd"] >= cost1 + cost2

    # Verify breakdown by model
    assert "gemini-1.5-flash" in usage["by_model"]
    assert "gemini-1.5-flash-8b" in usage["by_model"]

    primary_stat = usage["by_model"]["gemini-1.5-flash"]
    assert primary_stat["requests"] == 2  # 1 normal + 1 stream
    assert primary_stat["total_tokens"] > 0
    assert primary_stat["cost_usd"] > 0.0

    fallback_stat = usage["by_model"]["gemini-1.5-flash-8b"]
    assert fallback_stat["requests"] == 1
    assert fallback_stat["total_tokens"] == tokens2
    assert fallback_stat["cost_usd"] == cost2

    # Verify recent requests list
    recent = usage["recent_requests"]
    assert len(recent) == 3
    # Check that fallback_used is preserved
    fallback_entries = [req for req in recent if req["fallback_used"]]
    assert len(fallback_entries) == 1
    assert fallback_entries[0]["model"] == "gemini-1.5-flash-8b"
