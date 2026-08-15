from __future__ import annotations

import re
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cka_game.core.identity import get_player_name
from cka_game.core.paths import PROGRESS_PATH, SCENARIOS_DIR
from cka_game.core.progress import ProgressStore
from cka_game.core.scenarios import (
    Scenario,
    delete_scenario,
    load_scenario,
    load_scenarios,
    save_scenario,
)

BASE_DIR = Path(__file__).resolve().parent

# Strict allowlist for check_value coercion: only trust yaml.safe_load's
# int/float parse when the ORIGINAL STRING is itself a plain decimal
# integer or float. This deliberately excludes strings YAML 1.1 also
# happens to parse as numbers via non-decimal readings -- e.g. "0755"
# (octal -> 493) and "12:30" (sexagesimal -> 750) -- which authors would
# only ever intend as literal strings.
_INT_RE = re.compile(r"-?(0|[1-9]\d*)")
_FLOAT_RE = re.compile(r"-?(0|[1-9]\d*)\.\d+")
_SCENARIO_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


def create_app() -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    store = ProgressStore(PROGRESS_PATH)

    def _mode(request: Request) -> str:
        return request.cookies.get("cka_game_mode", "junior")

    def _total_score() -> int:
        total = 0
        for scenario in load_scenarios(SCENARIOS_DIR):
            entry = store.get(scenario.id)
            if entry.status == "completed":
                total += entry.score
        return total

    @app.get("/")
    def dashboard(request: Request):
        scenarios = load_scenarios(SCENARIOS_DIR)
        rows = [{"scenario": s, "entry": store.get(s.id)} for s in scenarios]
        total_score = sum(r["entry"].score for r in rows if r["entry"].status == "completed")
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "rows": rows,
                "total_score": total_score,
                "mode": _mode(request),
                "player_name": get_player_name(),
            },
        )

    @app.get("/scenario/{scenario_id}")
    def scenario_detail(request: Request, scenario_id: str):
        scenario = load_scenario(SCENARIOS_DIR, scenario_id)
        if scenario is None:
            return templates.TemplateResponse(
                request,
                "not_found.html",
                {
                    "scenario_id": scenario_id,
                    "mode": _mode(request),
                    "total_score": _total_score(),
                    "player_name": get_player_name(),
                },
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
                "total_score": _total_score(),
                "player_name": get_player_name(),
            },
        )

    @app.get("/api/scenario/{scenario_id}/state")
    def scenario_state(scenario_id: str):
        scenario = load_scenario(SCENARIOS_DIR, scenario_id)
        if scenario is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        entry = store.get(scenario_id)
        return {
            "status": entry.status,
            "hints_revealed": scenario.hints[: entry.hints_used],
            "score": entry.score,
            "answer_revealed": entry.answer_revealed,
            "total_score": _total_score(),
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

    @app.get("/author")
    def author_list(request: Request):
        scenarios = load_scenarios(SCENARIOS_DIR)
        return templates.TemplateResponse(
            request,
            "author_list.html",
            {
                "scenarios": scenarios,
                "mode": _mode(request),
                "total_score": _total_score(),
                "player_name": get_player_name(),
            },
        )

    @app.get("/author/new")
    def author_new(request: Request):
        return templates.TemplateResponse(
            request,
            "author_form.html",
            {
                "scenario": None,
                "mode": _mode(request),
                "total_score": _total_score(),
                "player_name": get_player_name(),
            },
        )

    @app.get("/author/{scenario_id}/edit")
    def author_edit(request: Request, scenario_id: str):
        scenario = load_scenario(SCENARIOS_DIR, scenario_id)
        return templates.TemplateResponse(
            request,
            "author_form.html",
            {
                "scenario": scenario,
                "mode": _mode(request),
                "total_score": _total_score(),
                "player_name": get_player_name(),
            },
        )

    @app.post("/author/scenario")
    async def author_save(request: Request):
        form = await request.form()
        hints = [h.strip() for h in form.get("hints", "").splitlines() if h.strip()]
        check_types = form.getlist("check_type")
        verify = []
        for i, check_type in enumerate(check_types):
            check = {"type": check_type, "kind": form.getlist("check_kind")[i]}
            namespace = form.getlist("check_namespace")[i]
            if namespace:
                check["namespace"] = namespace
            name = form.getlist("check_name")[i]
            if name:
                check["name"] = name
            selector = form.getlist("check_selector")[i]
            if selector:
                check["selector"] = selector
            field_path = form.getlist("check_field")[i]
            if field_path:
                check["field"] = field_path
            value = form.getlist("check_value")[i]
            if value:
                # Coerce like YAML itself would (matching how hand-authored
                # scenario YAML types its values): "5" -> 5, "true" -> True,
                # bare strings like "NodePort" stay strings. This is an
                # intentional, narrow allowlist rather than "whatever YAML
                # 1.1 happens to parse" -- only a plain decimal int/float or
                # an explicit true/false literal is coerced. Everything else
                # (bare strings, a cron-schedule string like "*/2 * * * *",
                # or YAML 1.1 oddities like "0755" -> octal 493 or "12:30"
                # -> sexagesimal 750) is preserved verbatim as a string, so
                # authoring never 500s and non-numeric-looking values are
                # never silently reinterpreted.
                if value.lower() in ("true", "false"):
                    check["value"] = value.lower() == "true"
                elif _INT_RE.fullmatch(value) or _FLOAT_RE.fullmatch(value):
                    try:
                        coerced = yaml.safe_load(value)
                    except yaml.YAMLError:
                        coerced = value
                    check["value"] = coerced if isinstance(coerced, (int, float)) else value
                else:
                    check["value"] = value
            count = form.getlist("check_count")[i]
            if count:
                check["count"] = int(count)
            container = form.getlist("check_container")[i]
            if container:
                check["container"] = container
            verify.append(check)

        reset_namespace = form.get("reset_namespace", "")
        scenario_id = form.get("id", "").strip()

        if not _SCENARIO_ID_RE.fullmatch(scenario_id):
            return PlainTextResponse(
                "Invalid scenario id: must be lowercase letters, digits, and "
                "hyphens, starting with a letter or digit.",
                status_code=400,
            )

        # Preserve any non-Namespace reset steps (e.g. a PersistentVolume
        # deletion) already present on the existing scenario when editing,
        # since the form only ever exposes a single namespace field and
        # would otherwise silently discard them.
        existing = load_scenario(SCENARIOS_DIR, scenario_id)
        if existing is not None:
            other_steps = [step for step in existing.reset if step.get("kind") != "Namespace"]
            reset = ([{"kind": "Namespace", "name": reset_namespace}] if reset_namespace else []) + other_steps
        else:
            reset = [{"kind": "Namespace", "name": reset_namespace}] if reset_namespace else []

        scenario = Scenario(
            id=scenario_id,
            title=form.get("title", ""),
            description=form.get("description", ""),
            category=form.get("category", ""),
            difficulty=form.get("difficulty", ""),
            points=int(form.get("points", 0)),
            hint_penalty=int(form.get("hint_penalty", 0)),
            hints=hints,
            answer=form.get("answer", ""),
            verify=verify,
            reset=reset,
        )
        save_scenario(SCENARIOS_DIR, scenario)
        return RedirectResponse("/author", status_code=303)

    @app.post("/author/scenario/{scenario_id}/delete")
    def author_delete(scenario_id: str):
        delete_scenario(SCENARIOS_DIR, scenario_id)
        return RedirectResponse("/author", status_code=303)

    @app.post("/mode/{mode}")
    def set_mode(mode: str, request: Request):
        referer = request.headers.get("referer", "/")
        # Only redirect back to a same-origin, relative-looking path. A
        # Referer starting with "//" is browser-interpreted as
        # protocol-relative to an external host, and an absolute URL
        # (http://evil.com/...) is an open redirect -- fall back to "/".
        if not referer.startswith("/") or referer.startswith("//"):
            referer = "/"
        response = RedirectResponse(referer, status_code=303)
        response.set_cookie(
            "cka_game_mode", mode, samesite="lax", max_age=60 * 60 * 24 * 30
        )
        return response

    return app
