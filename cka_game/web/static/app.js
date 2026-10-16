function pollScenario(url) {
  async function tick() {
    try {
      const res = await fetch(url);
      const data = await res.json();
      if (data.error) return;
      document.getElementById("status").textContent = data.status;
      document.getElementById("score").textContent = data.score;
      const potentialScoreEl = document.getElementById("potential-score");
      if (potentialScoreEl && typeof data.potential_score !== "undefined") {
        potentialScoreEl.textContent = data.potential_score;
      }
      if (typeof data.total_score !== "undefined") {
        const totalScoreEl = document.getElementById("total-score");
        if (totalScoreEl) totalScoreEl.textContent = "Score: " + data.total_score;
      }
      const hintsEl = document.getElementById("hints");
      hintsEl.innerHTML = "";
      data.hints_revealed.forEach((hint) => {
        const li = document.createElement("li");
        li.textContent = hint;
        hintsEl.appendChild(li);
      });
    } catch (err) {
      // network/cluster hiccup - keep last known state, retry next tick
    }
  }
  tick();
  setInterval(tick, 3000);
}

function pollDashboard(url) {
  async function tick() {
    try {
      const res = await fetch(url);
      const data = await res.json();
      const scoreEl = document.getElementById("total-score");
      if (scoreEl) scoreEl.textContent = "Score: " + data.total_score;
      data.scenarios.forEach((s) => {
        const cell = document.querySelector(`tr[data-scenario-id="${s.id}"] .status`);
        if (cell) cell.textContent = s.status;
      });
    } catch (err) {
      // ignore, retry next tick
    }
  }
  tick();
  setInterval(tick, 3000);
}

function pollScoreboard(url) {
  const expanded = new Set();
  let players = [];

  function addCell(tr, text) {
    const td = document.createElement("td");
    td.textContent = text;
    tr.appendChild(td);
  }

  function render() {
    const body = document.getElementById("scoreboard-body");
    document.getElementById("scoreboard-empty").hidden = players.length > 0;
    body.innerHTML = "";
    players.forEach((p) => {
      const tr = document.createElement("tr");
      tr.className = "scoreboard-row";
      const seen = p.last_seen ? p.last_seen.slice(0, 19).replace("T", " ") + " UTC" : "";
      [p.rank, p.player, p.total, p.completed, p.hints_used, seen].forEach((v) => addCell(tr, v));
      tr.addEventListener("click", () => {
        if (expanded.has(p.player)) expanded.delete(p.player);
        else expanded.add(p.player);
        render();
      });
      body.appendChild(tr);
      if (expanded.has(p.player)) {
        const detail = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 6;
        const ids = Object.keys(p.scenarios).sort();
        if (ids.length === 0) td.textContent = "No scenarios yet.";
        ids.forEach((id) => {
          const s = p.scenarios[id];
          const line = document.createElement("div");
          line.textContent =
            id + ": " + s.status + ", score " + s.score + ", hints " + s.hints_used +
            (s.answer_revealed ? ", answer revealed" : "");
          td.appendChild(line);
        });
        detail.appendChild(td);
        body.appendChild(detail);
      }
    });
  }

  async function tick() {
    try {
      const res = await fetch(url);
      players = (await res.json()).players;
      render();
    } catch (err) {
      // hub hiccup - keep last known state, retry next tick
    }
  }
  tick();
  setInterval(tick, 3000);
}
