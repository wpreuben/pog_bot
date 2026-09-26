"""상태에 저장 가능한 결정적 무작위 순서."""


def _next_u32(state: int) -> int:
    state ^= (state << 13) & 0xFFFFFFFF
    state ^= state >> 17
    state ^= (state << 5) & 0xFFFFFFFF
    return state & 0xFFFFFFFF


def shuffle_with_state(cards: list[str], rng_state: int) -> tuple[list[str], int]:
    """입력을 바꾸지 않고 Fisher-Yates 섞기와 다음 RNG 상태를 반환한다."""
    result = list(cards)
    state = rng_state & 0xFFFFFFFF or 0x6D2B79F5
    for index in range(len(result) - 1, 0, -1):
        state = _next_u32(state)
        chosen = state % (index + 1)
        result[index], result[chosen] = result[chosen], result[index]
    return result, state
