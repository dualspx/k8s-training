def compute_score(
    points: int, hint_penalty: int, hints_used: int, answer_revealed: bool
) -> int:
    if answer_revealed:
        return 0
    return max(0, points - hints_used * hint_penalty)
