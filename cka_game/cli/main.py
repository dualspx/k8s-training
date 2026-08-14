from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cka_game.core.progress import ProgressEntry, ProgressStore
from cka_game.core.scenarios import load_scenario, load_scenarios
from cka_game.core.scoring import compute_score

app = typer.Typer(help="CKA scenario game")
console = Console()

SCENARIOS_DIR = Path("scenarios")
PROGRESS_PATH = Path("data/progress.json")


def _progress_store() -> ProgressStore:
    return ProgressStore(PROGRESS_PATH)


def _require_scenario(scenario_id: str):
    scenario = load_scenario(SCENARIOS_DIR, scenario_id)
    if scenario is None:
        console.print(f"[red]No scenario '{scenario_id}'[/red]")
        raise typer.Exit(code=1)
    return scenario


@app.command("list")
def list_scenarios():
    scenarios = load_scenarios(SCENARIOS_DIR)
    store = _progress_store()
    table = Table("ID", "Category", "Difficulty", "Points", "Status")
    for scenario in scenarios:
        entry = store.get(scenario.id)
        table.add_row(
            scenario.id, scenario.category, scenario.difficulty, str(scenario.points), entry.status
        )
    console.print(table)


@app.command()
def show(scenario_id: str):
    scenario = _require_scenario(scenario_id)
    entry = _progress_store().get(scenario_id)
    console.print(f"[bold]{scenario.title}[/bold] ({scenario.category}/{scenario.difficulty})")
    console.print(scenario.description)
    console.print(f"Status: {entry.status}")
    revealed = scenario.hints[: entry.hints_used]
    if revealed:
        console.print("\n[bold]Hints so far:[/bold]")
        for i, hint_text in enumerate(revealed, 1):
            console.print(f"  {i}. {hint_text}")
    potential = compute_score(
        scenario.points, scenario.hint_penalty, entry.hints_used, entry.answer_revealed
    )
    console.print(f"Potential score: {potential}")


@app.command()
def hint(scenario_id: str):
    scenario = _require_scenario(scenario_id)
    store = _progress_store()
    entry = store.get(scenario_id)
    if entry.hints_used >= len(scenario.hints):
        console.print("[yellow]No more hints for this scenario.[/yellow]")
        return
    next_hint = scenario.hints[entry.hints_used]
    entry.hints_used += 1
    if entry.status == "not_started":
        entry.status = "in_progress"
    store.save(scenario_id, entry)
    console.print(f"[cyan]Hint {entry.hints_used}:[/cyan] {next_hint}")
    potential = compute_score(
        scenario.points, scenario.hint_penalty, entry.hints_used, entry.answer_revealed
    )
    console.print(f"Potential score is now: {potential}")


@app.command()
def reveal(scenario_id: str):
    scenario = _require_scenario(scenario_id)
    store = _progress_store()
    entry = store.get(scenario_id)
    entry.answer_revealed = True
    if entry.status == "not_started":
        entry.status = "in_progress"
    store.save(scenario_id, entry)
    console.print("[bold]Answer:[/bold]")
    console.print(scenario.answer)
    console.print("[yellow]Potential score for this scenario is now 0.[/yellow]")


@app.command()
def score():
    scenarios = load_scenarios(SCENARIOS_DIR)
    store = _progress_store()
    total = 0
    completed = 0
    for scenario in scenarios:
        entry = store.get(scenario.id)
        if entry.status == "completed":
            total += entry.score
            completed += 1
    console.print(f"Score: {total}")
    console.print(f"Completed: {completed}/{len(scenarios)}")


def main():
    app()


if __name__ == "__main__":
    main()
