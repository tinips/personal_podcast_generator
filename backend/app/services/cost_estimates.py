OPENAI_INPUT_COST_PER_1M_TOKENS = 0.15
OPENAI_OUTPUT_COST_PER_1M_TOKENS = 0.60
ELEVENLABS_MULTILINGUAL_COST_PER_1K_CHARS = 0.10


def estimate_openai_cost(input_tokens: int, output_tokens: int) -> float:
    cost = (
        (input_tokens / 1_000_000) * OPENAI_INPUT_COST_PER_1M_TOKENS
        + (output_tokens / 1_000_000) * OPENAI_OUTPUT_COST_PER_1M_TOKENS
    )
    return round(cost, 4)


def estimate_elevenlabs_cost(characters: int | float) -> float:
    cost = (characters / 1000) * ELEVENLABS_MULTILINGUAL_COST_PER_1K_CHARS
    return round(cost, 4)
