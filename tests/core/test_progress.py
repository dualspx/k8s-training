from cka_game.core.progress import ProgressEntry, ProgressStore


def test_get_missing_scenario_returns_default_entry(tmp_path):
    store = ProgressStore(tmp_path / "progress.json")
    entry = store.get("does-not-exist")
    assert entry == ProgressEntry()


def test_save_then_get_round_trips(tmp_path):
    store = ProgressStore(tmp_path / "progress.json")
    store.save("web-scale", ProgressEntry(status="completed", hints_used=1, score=8))
    entry = store.get("web-scale")
    assert entry == ProgressEntry(status="completed", hints_used=1, score=8)


def test_save_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "progress.json"
    store = ProgressStore(path)
    store.save("web-scale", ProgressEntry(status="in_progress"))
    assert path.exists()


def test_save_preserves_other_entries(tmp_path):
    store = ProgressStore(tmp_path / "progress.json")
    store.save("a", ProgressEntry(status="completed", score=5))
    store.save("b", ProgressEntry(status="in_progress"))
    assert store.get("a").status == "completed"
    assert store.get("b").status == "in_progress"
