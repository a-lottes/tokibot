// The demo on friends.html: Pixel (you) meets Mochi at the next desk.
// Numbers follow app/claudegotchi/mood.py and life.py; the screens come from
// app/tools/site_social.py (make social-pics).
(function () {
  "use strict";
  var root = document.querySelector(".demo");
  if (!root) return;

  // Total XP needed for a level: 0, 50, 150, 300, 500, … (life.py)
  function xpFor(level) { return 25 * (level - 1) * level; }
  function levelFor(xp) { var l = 1; while (xp >= xpFor(l + 1)) l++; return l; }

  var log = document.getElementById("demo-log");
  var next = document.getElementById("demo-next");
  var reset = document.getElementById("demo-reset");
  var gotchis = { pixel: document.getElementById("g-pixel"), mochi: document.getElementById("g-mochi") };
  var state;

  // Each step: button label, the screens it shows, XP it awards, badges it adds, and the log
  var STEPS = [
    {
      button: "01 · Walk over to Mochi →",
      screen: "meet",
      xp: { pixel: 20, mochi: 20 },
      badges: { pixel: ["Hello world"], mochi: ["Hello world"] },
      log: [
        ["pixel", "mochi", "BEACON", "id 7f3a91 · Lv3 · working · no accessory"],
        ["mochi", "pixel", "BEACON", "id c2e04b · Lv4 · idle · cap"],
        ["mochi", "pixel", "CARD", "\"Mochi\" · Lv4 · public key · signature ✓"],
        [null, null, "ENCOUNTER", "30 s in range · new gotchi: +20 XP each · badge Hello world"]
      ]
    },
    {
      button: "02 · Press Befriend on Pixel's social page →",
      screen: "ask",
      log: [
        ["pixel", "mochi", "OFFER", "sign(Pixel key + Mochi key + today) · friend secret, encrypted for Mochi"],
        [null, null, "WAIT", "Mochi's display asks its owner"]
      ]
    },
    {
      button: "03 · Mochi's owner presses Accept →",
      screen: "friends",
      xp: { pixel: 30, mochi: 30 },
      log: [
        ["mochi", "pixel", "OFFER", "sign(Mochi key + Pixel key + today) · friend secret, encrypted for Pixel"],
        [null, null, "PROOF", "two signatures = friendship · +30 XP each"]
      ],
      after: {
        screen: "badge",
        badges: { pixel: ["First friend"], mochi: ["First friend"] },
        log: [[null, null, "BADGE", "First friend → bow unlocked for both"]]
      }
    },
    {
      button: "04 · Both start working →",
      screen: "cowork",
      ticks: 3,
      log: [
        ["pixel", "mochi", "BEACON", "friend tag ♥ · Lv4 · working · bow"],
        ["mochi", "pixel", "BEACON", "friend tag ♥ · Lv4 · working · bow"],
        [null, null, "BONUS", "a friend nearby is working too: +10 % XP"]
      ],
      after: {
        screen: "glasses",
        badges: { pixel: ["Co-working"], mochi: ["Co-working"] },
        log: [[null, null, "BADGE", "Co-working → glasses unlocked for both"]]
      }
    }
  ];

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function show(name) {
    var g = gotchis[name], s = state[name], lv = levelFor(s.xp);
    var lo = xpFor(lv), hi = xpFor(lv + 1);
    g.querySelector(".demo-lv").textContent = "Lv" + lv;
    g.querySelector(".demo-bar i").style.width = (100 * (s.xp - lo) / (hi - lo)).toFixed(1) + "%";
    g.querySelector(".demo-num").textContent = s.xp + " / " + hi + " xp";
    var box = g.querySelector(".demo-badges");
    box.textContent = "";
    s.badges.forEach(function (b) { box.appendChild(el("span", "demo-badge", b)); });
  }

  function screen(step) {
    ["pixel", "mochi"].forEach(function (n) {
      var img = gotchis[n].querySelector(".demo-screen img");
      img.src = "img/social/" + n + "-" + step + ".png";
      gotchis[n].classList.remove("demo-flash");
      void gotchis[n].offsetWidth;           // restart the animation
      gotchis[n].classList.add("demo-flash");
    });
  }

  function line(from, to, kind, text) {
    var row = el("span", "demo-row");
    if (from) {
      row.appendChild(el("span", "demo-dir", from === "pixel" ? "pixel → mochi " : "mochi → pixel "));
    } else {
      row.appendChild(el("span", "demo-dir", "             "));
    }
    row.appendChild(el("b", null, kind.padEnd(10)));
    row.appendChild(document.createTextNode(text + "\n"));
    log.appendChild(row);
  }

  function gain(name, xp, why) {
    var before = levelFor(state[name].xp);
    state[name].xp += xp;
    var after = levelFor(state[name].xp);
    if (after > before) line(null, null, "LEVEL UP", name + " is level " + after + " now (" + why + ")");
  }

  function apply(part) {
    if (part.screen) screen(part.screen);
    (part.log || []).forEach(function (l) { line.apply(null, l); });
    ["pixel", "mochi"].forEach(function (n) {
      if (part.xp && part.xp[n]) gain(n, part.xp[n], "friends");
      if (part.badges && part.badges[n]) state[n].badges = state[n].badges.concat(part.badges[n]);
      show(n);
    });
  }

  var timers = [];
  function later(fn, ms) { timers.push(setTimeout(fn, ms)); }

  function step() {
    var s = STEPS[state.step];
    if (!s) return;
    next.disabled = true;
    if (state.step === 0) log.textContent = "";
    apply(s);
    var wait = 0;
    for (var i = 0; i < (s.ticks || 0); i++) {
      wait += 900;
      later(function () {
        line(null, null, "REPLY", "both finish a reply: +10 XP, +1 co-working bonus");
        gain("pixel", 11, "co-working");
        gain("mochi", 11, "co-working");
        show("pixel"); show("mochi");
      }, wait);
    }
    if (s.after) later(function () { apply(s.after); }, wait + 1400);
    later(function () {
      state.step++;
      var n = STEPS[state.step];
      next.textContent = n ? n.button : "That's it: two friends, three badges each.";
      next.disabled = !n;
      root.setAttribute("data-step", state.step);
    }, wait + (s.after ? 1600 : 500));
  }

  function start() {
    timers.forEach(clearTimeout);
    timers = [];
    state = { step: 0, pixel: { xp: 270, badges: [] }, mochi: { xp: 420, badges: [] } };
    screen("start");
    show("pixel"); show("mochi");
    log.textContent = "";
    log.appendChild(el("span", "c", "# nothing yet: Pixel and Mochi are out of range\n"));
    next.textContent = STEPS[0].button;
    next.disabled = false;
    root.setAttribute("data-step", 0);
  }

  next.addEventListener("click", step);
  reset.addEventListener("click", start);
  start();
})();
