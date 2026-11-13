"""Model prices (USD per 1M tokens, standard tier).

Source: https://developers.openai.com/api/docs/pricing, checked 2026-11-13.
Prices change: re-check before quoting numbers in the README.
"""

PRICES = {
    # model: (input, cached_input, output)
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-6.1-terra": (1.00, 0.05, 5.00),
    "gpt-6.1-sol": (2.00, 0.10, 10.00),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    inp, cached, out = PRICES[model]
    uncached = input_tokens - cached_tokens
    return (uncached * inp + cached_tokens * cached + output_tokens * out) / 1_000_000
