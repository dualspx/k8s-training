from cka_game.core.scoring import compute_score


def test_full_score_with_no_hints():
    assert compute_score(points=10, hint_penalty=2, hints_used=0, answer_revealed=False) == 10


def test_deducts_per_hint():
    assert compute_score(points=10, hint_penalty=2, hints_used=2, answer_revealed=False) == 6


def test_floors_at_zero_not_negative():
    assert compute_score(points=10, hint_penalty=2, hints_used=10, answer_revealed=False) == 0


def test_answer_revealed_zeroes_score_regardless_of_hints():
    assert compute_score(points=10, hint_penalty=2, hints_used=0, answer_revealed=True) == 0
