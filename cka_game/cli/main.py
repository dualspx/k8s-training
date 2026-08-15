from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from cka_game.core.identity import get_player_name, is_player_name_set, set_player_name
from cka_game.core.kube import KindSafetyError, build_cluster_client
from cka_game.core.paths import PROGRESS_PATH, SCENARIOS_DIR
from cka_game.core.progress import ProgressEntry, ProgressStore
from cka_game.core.reset import run_reset
from cka_game.core.scenarios import load_scenario, load_scenarios
from cka_game.core.scoring import compute_score
from cka_game.core.verify import run_verify

app = typer.Typer(help="CKA scenario game")
console = Console()


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
    console.print(f"Player: {get_player_name()}")
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
    if entry.status == "completed":
        console.print("[yellow]This scenario is already completed.[/yellow]")
        return
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
    if entry.status == "completed":
        console.print("[yellow]This scenario is already completed.[/yellow]")
        return
    entry.answer_revealed = True
    if entry.status == "not_started":
        entry.status = "in_progress"
    store.save(scenario_id, entry)
    console.print("[bold]Answer:[/bold]")
    console.print(scenario.answer)
    console.print("[yellow]Potential score for this scenario is now 0.[/yellow]")


@app.command()
def score():
    console.print(f"Player: {get_player_name()}")
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


@app.command()
def whoami(name: str = typer.Option(None, "--set", help="Set your player name")):
    if name is not None:
        set_player_name(name)
        console.print(f"[green]Player name set to '{name}'.[/green]")
        return
    current = get_player_name()
    source = "manually set" if is_player_name_set() else "auto-detected from OS login"
    console.print(f"Player: {current} ({source})")


def _cluster_client_or_exit():
    try:
        return build_cluster_client()
    except KindSafetyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    except Exception:
        console.print(
            "[red]Cluster unreachable, is 'kind-cka-practice' running? "
            "(try: kind get clusters)[/red]"
        )
        raise typer.Exit(code=1)


@app.command()
def check(scenario_id: str):
    scenario = _require_scenario(scenario_id)
    client = _cluster_client_or_exit()
    results = run_verify(scenario, client)
    all_passed = True
    for result in results:
        icon = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        console.print(f"{icon} {escape(f'[{result.type}]')} {result.message}")
        all_passed = all_passed and result.passed

    store = _progress_store()
    entry = store.get(scenario_id)
    if all_passed:
        if entry.status != "completed":
            entry.score = compute_score(
                scenario.points, scenario.hint_penalty, entry.hints_used, entry.answer_revealed
            )
            entry.status = "completed"
            store.save(scenario_id, entry)
        console.print(f"[bold green]Completed! Score: {entry.score}[/bold green]")
    else:
        if entry.status == "not_started":
            entry.status = "in_progress"
            store.save(scenario_id, entry)
        console.print("[red]Not yet passing.[/red]")
        raise typer.Exit(code=1)


@app.command()
def reset(scenario_id: str):
    scenario = _require_scenario(scenario_id)
    client = _cluster_client_or_exit()
    messages = run_reset(scenario, client)
    for message in messages:
        console.print(message)
    _progress_store().save(scenario_id, ProgressEntry())
    console.print("[cyan]Lab reset. Progress for this scenario cleared.[/cyan]")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn

    from cka_game.web.app import create_app

    uvicorn.run(create_app(), host=host, port=port)


def main():
    app()


if __name__ == "__main__":
    main()
