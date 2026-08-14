from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cka_game.core.progress import ProgressStore
from cka_game.core.scenarios import load_scenario, load_scenarios

BASE_DIR = Path(__file__).resolve().parent
SCENARIOS_DIR = Path("scenarios")
PROGRESS_PATH = Path("data/progress.json")


def create_app() -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    store = ProgressStore(PROGRESS_PATH)

    def _mode(request: Request) -> str:
        return request.cookies.get("cka_game_mode", "junior")

    @app.get("/")
    def dashboard(request: Request):
        scenarios = load_scenarios(SCENARIOS_DIR)
        rows = [{"scenario": s, "entry": store.get(s.id)} for s in scenarios]
        total_score = sum(r["entry"].score for r in rows if r["entry"].status == "completed")
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {"rows": rows, "total_score": total_score, "mode": _mode(request)},
        )

    @app.get("/scenario/{scenario_id}")
    def scenario_detail(request: Request, scenario_id: str):
        scenario = load_scenario(SCENARIOS_DIR, scenario_id)
        if scenario is None:
            return templates.TemplateResponse(
                request,
                "not_found.html",
                {"scenario_id": scenario_id, "mode": _mode(request)},
                status_code=404,
            )
        entry = store.get(scenario_id)
        revealed_hints = scenario.hints[: entry.hints_used]
        return templates.TemplateResponse(
            request,
            "scenario.html",
            {
                "scenario": scenario,
                "entry": entry,
                "revealed_hints": revealed_hints,
                "mode": _mode(request),
            },
        )

    @app.get("/api/scenario/{scenario_id}/state")
    def scenario_state(scenario_id: str):
        scenario = load_scenario(SCENARIOS_DIR, scenario_id)
        if scenario is None:
            return {"error": "not found"}
        entry = store.get(scenario_id)
        return {
            "status": entry.status,
            "hints_revealed": scenario.hints[: entry.hints_used],
            "score": entry.score,
            "answer_revealed": entry.answer_revealed,
        }

    @app.get("/api/dashboard/state")
    def dashboard_state():
        scenarios = load_scenarios(SCENARIOS_DIR)
        items = []
        total = 0
        for scenario in scenarios:
            entry = store.get(scenario.id)
            items.append({"id": scenario.id, "status": entry.status, "score": entry.score})
            if entry.status == "completed":
                total += entry.score
        return {"scenarios": items, "total_score": total}

    return app
