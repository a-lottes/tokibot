// Fills the highscore lists from /api/scores (netlify/functions/scores.mjs).
(function () {
  var status = document.getElementById("board-status");
  var buttons = document.querySelectorAll(".period button");
  var data = null;
  var period = "week";

  function fmt(value, unit) {
    if (unit === "food") {
      if (value >= 1e9) return (value / 1e9).toFixed(1) + "B";
      if (value >= 1e6) return (value / 1e6).toFixed(1) + "M";
      if (value >= 1e3) return Math.round(value / 1e3) + "k";
      return String(value);
    }
    if (unit === "xp/M") return value.toFixed(1);
    return value.toLocaleString("en") + " XP";
  }

  function fill(list, rows) {
    list.textContent = "";
    if (!rows || !rows.length) {
      var empty = document.createElement("li");
      empty.className = "empty";
      empty.textContent = "Nobody yet.";
      list.appendChild(empty);
      return;
    }
    rows.forEach(function (r) {
      var li = document.createElement("li");
      var who = document.createElement("span");
      who.className = "who";
      who.textContent = r.name;
      var meta = document.createElement("small");
      meta.textContent = "lv " + r.level + " · " + r.id;
      who.appendChild(meta);
      var val = document.createElement("span");
      val.className = "val";
      val.textContent = fmt(r.value, list.dataset.unit);
      li.appendChild(who);
      li.appendChild(val);
      list.appendChild(li);
    });
  }

  function render() {
    document.querySelectorAll(".ranks").forEach(function (list) {
      var board = data.boards[list.dataset.board];
      fill(list, Array.isArray(board) ? board : board[period]);
    });
    var since = period === "all" ? "" : " · since " + data.periods[period];
    status.textContent = data.gotchis + (data.gotchis === 1 ? " gotchi" : " gotchis") + " on the list" + since;
  }

  buttons.forEach(function (b) {
    b.addEventListener("click", function () {
      period = b.dataset.period;
      buttons.forEach(function (o) { o.setAttribute("aria-pressed", o === b ? "true" : "false"); });
      if (data) render();
    });
  });

  fetch("/api/scores")
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (d) { data = d; render(); })
    .catch(function () { status.textContent = "The lists are not reachable right now. Try again later."; });
})();
