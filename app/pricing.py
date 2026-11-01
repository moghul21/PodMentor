"""Token pricing rate cards and cost calculation utilities for PodMentor."""

# Pricing rates per 1,000,000 tokens (USD)
# Source: Google Cloud / Gemini API official pricing
MODEL_PRICING_PER_MILLION = {
    "gemini-1.5-flash": {
        "input": 0.075,
        "output": 0.30,
    },
    "gemini-1.5-flash-8b": {
        "input": 0.0375,
        "output": 0.15,
    },
    "gemini-2.0-flash": {
        "input": 0.075,
        "output": 0.30,
    },
    "gemini-2.5-flash": {
        "input": 0.075,
        "output": 0.30,
    },
    "gemini-1.5-pro": {
        "input": 1.25,
        "output": 5.00,
    },
    "mock-primary": {
        "input": 0.075,
        "output": 0.30,
    },
    "mock-fallback": {
        "input": 0.0375,
        "output": 0.15,
    },
    "default": {
        "input": 0.075,
        "output": 0.30,
    },
}


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate the estimated cost in USD for a given model and token counts.

    Returns the total cost rounded to 8 decimal places.
    """
    rates = MODEL_PRICING_PER_MILLION.get(model, MODEL_PRICING_PER_MILLION["default"])
    input_cost = (prompt_tokens / 1_000_000.0) * rates["input"]
    output_cost = (completion_tokens / 1_000_000.0) * rates["output"]
    total = input_cost + output_cost
    return round(total, 8)
