function pollScenario(url) {
  async function tick() {
    try {
      const res = await fetch(url);
      const data = await res.json();
      if (data.error) return;
      document.getElementById("status").textContent = data.status;
      document.getElementById("score").textContent = data.score;
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
