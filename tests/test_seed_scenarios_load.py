import logging
from pathlib import Path

from cka_game.core.scenarios import load_scenarios

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


def test_all_seed_scenarios_load_without_warnings(caplog):
    with caplog.at_level(logging.WARNING):
        scenarios = load_scenarios(SCENARIOS_DIR)
    assert caplog.text == ""
    assert len(scenarios) == 9


def test_seed_scenario_ids_are_unique():
    scenarios = load_scenarios(SCENARIOS_DIR)
    ids = [s.id for s in scenarios]
    assert len(ids) == len(set(ids))


def test_seed_scenarios_cover_expected_categories():
    scenarios = load_scenarios(SCENARIOS_DIR)
    categories = {s.category for s in scenarios}
    assert categories == {"workloads", "networking", "storage", "security", "cluster"}
