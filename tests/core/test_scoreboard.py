import pytest

import cka_game.core.scoreboard as sb

POINTS = {"a": 10, "b": 20}


def _entry(status="completed", score=10, hints=0, revealed=False):
    return {"status": status, "score": score, "hints_used": hints, "answer_revealed": revealed}


def _store(tmp_path):
    return sb.ScoreboardStore(tmp_path / "data" / "scoreboard.json")


def test_submit_then_ranking(tmp_path):
    store = _store(tmp_path)
    store.submit("alice", "id-a", "a", _entry(score=8, hints=1), POINTS)
    rows = store.ranking()
    assert len(rows) == 1
    row = rows[0]
    assert (row["rank"], row["player"], row["total"], row["completed"], row["hints_used"]) == (
        1, "alice", 8, 1, 1,
    )
    assert row["scenarios"]["a"]["score"] == 8
    assert "player_id" not in row


def test_resubmit_is_idempotent(tmp_path):
    store = _store(tmp_path)
    for _ in range(3):
        store.submit("alice", "id-a", "a", _entry(), POINTS)
    assert store.ranking()[0]["total"] == 10


def test_only_completed_scenarios_count_toward_total(tmp_path):
    store = _store(tmp_path)
    store.submit("alice", "id-a", "a", _entry(status="in_progress", score=0, hints=2), POINTS)
    store.submit("alice", "id-a", "b", _entry(score=20), POINTS)
    row = store.ranking()[0]
    assert row["total"] == 20
    assert row["completed"] == 1
    assert row["hints_used"] == 2


def test_ranking_order_and_tie_break(tmp_path):
    store = _store(tmp_path)
    store.submit("zed", "id-z", "a", _entry(score=10), POINTS)
    store.submit("amy", "id-m", "a", _entry(score=10), POINTS)
    store.submit("bob", "id-b", "b", _entry(score=20), POINTS)
    assert [r["player"] for r in store.ranking()] == ["bob", "amy", "zed"]
    assert [r["rank"] for r in store.ranking()] == [1, 2, 3]


def test_ties_on_total_prefer_more_completed(tmp_path):
    store = _store(tmp_path)
    store.submit("one", "id-1", "b", _entry(score=20), POINTS)
    store.submit("two", "id-2", "a", _entry(score=10), POINTS)
    store.submit("two", "id-2", "b", _entry(status="completed", score=10), POINTS)
    assert [r["player"] for r in store.ranking()] == ["two", "one"]


def test_name_taken_by_other_player_id(tmp_path):
    store = _store(tmp_path)
    store.submit("alice", "id-a", "a", _entry(), POINTS)
    with pytest.raises(sb.ScoreboardError) as exc:
        store.submit("alice", "someone-else", "a", _entry(), POINTS)
    assert exc.value.code == "name_taken"


def test_unknown_scenario(tmp_path):
    with pytest.raises(sb.ScoreboardError) as exc:
        _store(tmp_path).submit("alice", "id-a", "nope", _entry(), POINTS)
    assert exc.value.code == "unknown_scenario"


@pytest.mark.parametrize(
    "player,player_id,scenario_id,entry",
    [
        ("", "id", "a", _entry()),
        ("x" * 41, "id", "a", _entry()),
        (None, "id", "a", _entry()),
        ("alice", "", "a", _entry()),
        ("alice", 5, "a", _entry()),
        ("alice", "id", ["a"], _entry()),
        ("alice", "id", "a", "not-a-dict"),
        ("alice", "id", "a", _entry(status="won")),
        ("alice", "id", "a", _entry(score=11)),  # above scenario points (10)
        ("alice", "id", "a", _entry(score=-1)),
        ("alice", "id", "a", _entry(score=True)),
        ("alice", "id", "a", _entry(hints=-1)),
        ("alice", "id", "a", {**_entry(), "answer_revealed": "yes"}),
        ("alice", "id", "a", {"status": "completed"}),
    ],
)
def test_invalid_submissions_rejected(tmp_path, player, player_id, scenario_id, entry):
    with pytest.raises(sb.ScoreboardError) as exc:
        _store(tmp_path).submit(player, player_id, scenario_id, entry, POINTS)
    assert exc.value.code == "invalid"


def test_extra_entry_keys_are_dropped(tmp_path):
    store = _store(tmp_path)
    store.submit("alice", "id-a", "a", {**_entry(), "evil": "<script>"}, POINTS)
    assert "evil" not in store.ranking()[0]["scenarios"]["a"]


def test_corrupt_file_is_treated_as_empty(tmp_path):
    path = tmp_path / "scoreboard.json"
    path.write_text("{not json")
    assert sb.ScoreboardStore(path).ranking() == []


def test_data_persists_across_store_instances(tmp_path):
    _store(tmp_path).submit("alice", "id-a", "a", _entry(), POINTS)
    assert _store(tmp_path).ranking()[0]["player"] == "alice"


def test_token_from_env(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "HUB_TOKEN_PATH", tmp_path / "hub_token")
    monkeypatch.setenv("CKA_GAME_TOKEN", "secret")
    assert sb.get_hub_token() == "secret"
    assert not (tmp_path / "hub_token").exists()


def test_token_generated_once_and_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "HUB_TOKEN_PATH", tmp_path / "data" / "hub_token")
    monkeypatch.setenv("CKA_GAME_TOKEN", "")  # empty == unset (compose passes "")
    first = sb.get_hub_token()
    assert len(first) >= 16
    assert sb.get_hub_token() == first
    assert (tmp_path / "data" / "hub_token").read_text().strip() == first


def test_token_matches():
    assert sb.token_matches("abc", "abc") is True
    assert sb.token_matches("abd", "abc") is False
    assert sb.token_matches("", "abc") is False


def test_generated_token_file_is_private(tmp_path, monkeypatch):
    import stat

    path = tmp_path / "data" / "hub_token"
    monkeypatch.setattr(sb, "HUB_TOKEN_PATH", path)
    monkeypatch.setenv("CKA_GAME_TOKEN", "")
    sb.get_hub_token()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
