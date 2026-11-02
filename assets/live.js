/* IdeaTaste: tab routing and the Live (Taste Tracker) view. No dependencies. */
(function () {
  "use strict";

  const VIEWS = ["idea", "experiments", "analysis", "live"];
  const LIVE_SUBS = ["trend", "watch"];
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const SVG = "http://www.w3.org/2000/svg";
  const svgEl = (tag, attrs = {}, text) => {
    const node = document.createElementNS(SVG, tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  /* ============================================================ routing */
  // Hash forms: #idea, #results, #analysis, #live, #live/watch. Other anchors (#citation) are left alone.
  const tabs = document.getElementById("tabs");
  function route(scroll) {
    const [view, sub] = location.hash.replace("#", "").split("/");
    if (!VIEWS.includes(view)) {
      if (!location.hash || location.hash === "#top") show("idea", null, scroll);
      return;
    }
    show(view, sub, scroll);
  }
  function show(view, sub, scroll) {
    document.querySelectorAll(".view").forEach((v) => { v.hidden = v.dataset.view !== view; });
    document.querySelectorAll("[data-tab]").forEach((a) => a.setAttribute("aria-selected", String(a.dataset.tab === view)));
    // Idea is the home page: the title block belongs to it and is hidden elsewhere.
    document.getElementById("hero").hidden = view !== "idea";
    if (view === "live") showSub(LIVE_SUBS.includes(sub) ? sub : currentSub);
    if (scroll) window.scrollTo(0, 0);
  }
  let currentSub = "trend";
  function showSub(sub) {
    currentSub = sub;
    document.querySelectorAll("#live-sub button").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.sub === sub)));
    document.querySelectorAll("[data-sub-panel]").forEach((p) => { p.hidden = p.dataset.subPanel !== sub; });
  }
  document.getElementById("live-sub").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    history.replaceState(null, "", `#live/${b.dataset.sub}`);
    showSub(b.dataset.sub);
  });
  document.querySelectorAll("[data-goto], [data-tab]").forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    const target = a.dataset.goto || a.dataset.tab;
    const hash = `#${target}${a.dataset.liveSub ? "/" + a.dataset.liveSub : ""}`;
    history.pushState(null, "", hash);
    route(true);
  }));
  document.querySelector(".brand").addEventListener("click", (e) => {
    e.preventDefault();
    history.pushState(null, "", location.pathname + location.search);
    show("idea", null, true);
  });
  window.addEventListener("popstate", () => route(true));
  window.addEventListener("hashchange", () => route(true));
  route(false);

  /* ============================================================ live data */
  Promise.all([
    fetch("assets/data/leaderboard.json").then((r) => r.json()),
    fetch("assets/data/live.json").then((r) => r.json()),
  ]).then(([board, live]) => {
    editions(live);
    trend(board);
    watch(live);
  }).catch((err) => {
    document.getElementById("edition-strip").textContent = `Could not load live data (${err.message}).`;
  });

  /* ------------------------------------------------------------ editions */
  function editions(live) {
    const strip = document.getElementById("edition-strip");
    const lastReleased = live.editions.filter((e) => e.status === "released").slice(-1)[0];
    const nextPlanned = live.editions.find((e) => e.status === "planned");
    const badge = (ed) => {
      if (ed === lastReleased) return '<span class="edition-badge now">current</span>';
      if (ed === nextPlanned) return '<span class="edition-badge next">next</span>';
      return ed.status === "planned" ? '<span class="edition-badge">planned</span>' : "";
    };
    strip.innerHTML = live.editions.map((ed, i) => `
      <div class="edition ${ed.status}">
        <span class="edition-dot"></span>
        <span class="edition-id">${esc(ed.id)}${badge(ed)}</span>
        <span class="edition-label">${esc(ed.label)}</span>
        <span class="edition-ref">human papers ${esc(ed.reference)}</span>
      </div>${i < live.editions.length - 1 ? '<span class="edition-line"></span>' : ""}`).join("");
    document.getElementById("changelog").innerHTML = live.editions.slice().reverse().map((ed) => `
      <li class="${ed.status}">
        <b>${esc(ed.id)}</b> <span class="muted">${esc(ed.date)}</span>
        <p>${esc(ed.note)}</p>
        ${ed.models_added.length ? `<p class="chips">${ed.models_added.map((m) => `<span>${esc(m)}</span>`).join("")}</p>` : ""}
      </li>`).join("");
  }

  /* ------------------------------------------------------------ model trend */
  function trend(data) {
    const metrics = { match_idea: "Match-Idea", match_cite: "Match-Cite", diversity_idea: "Diversity-Idea", diversity_cite: "Diversity-Cite" };
    const picker = document.getElementById("trend-metric");
    let metric = "match_idea";
    Object.entries(metrics).forEach(([k, name]) => {
      const b = document.createElement("button");
      b.type = "button"; b.dataset.value = k; b.textContent = name;
      b.setAttribute("aria-checked", String(k === metric));
      picker.append(b);
    });
    picker.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      metric = b.dataset.value;
      picker.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
      draw();
    });
    const rel = (model, method, m) => 100 * data.areas.reduce((s, a) =>
      s + data.scores[model][a.key][method][m] / data.human[a.key][m], 0) / data.areas.length;

    const container = document.getElementById("chart-trend");
    const tooltip = document.querySelector(".tooltip");
    function draw() {
      container.innerHTML = "";
      const points = data.models.map((m) => {
        const byMethod = data.methods.map((me) => ({ me, v: rel(m.key, me, metric) }));
        const best = byMethod.reduce((a, b) => (b.v > a.v ? b : a));
        return { ...m, t: new Date(m.release_date).getTime(), v: best.v, method: best.me };
      });
      const W = 560, H = 300, L = 44, R = 20, T = 16, B = 34;
      const t0 = new Date("2025-01-01").getTime(), t1 = new Date("2027-07-01").getTime();
      const vmax = Math.max(100, ...points.map((p) => p.v)) * 1.08;
      const x = (t) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
      const y = (v) => T + (1 - v / vmax) * (H - T - B);
      const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${metrics[metric]} against release date` });
      const ax = svgEl("g", { class: "axis" });
      const step = vmax > 150 ? 50 : 25;
      for (let v = 0; v <= vmax; v += step) {
        ax.append(svgEl("line", { x1: L, x2: W - R, y1: y(v), y2: y(v) }));
        ax.append(svgEl("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end" }, `${v}%`));
      }
      ["2025-01", "2025-07", "2026-01", "2026-07", "2027-01", "2027-07"].forEach((d) => {
        ax.append(svgEl("text", { x: x(new Date(d + "-01").getTime()), y: H - 10, "text-anchor": "middle" }, d));
      });
      svg.append(ax);
      // corpus cutoff + future region
      const cut = x(new Date("2026-01-01").getTime());
      svg.append(svgEl("line", { x1: cut, x2: cut, y1: T, y2: H - B, class: "cutoff-line" }));
      svg.append(svgEl("text", { x: cut + 5, y: T + 10, class: "label" }, "corpus cutoff"));
      const now = x(new Date("2026-11-01").getTime());
      svg.append(svgEl("rect", { x: now, y: T, width: W - R - now, height: H - T - B, class: "future-zone" }));
      svg.append(svgEl("text", { x: (now + W - R) / 2, y: (H - B) / 2 + 8, "text-anchor": "middle", class: "label future-label" }, "next editions"));
      // human level
      svg.append(svgEl("line", { x1: L, x2: W - R, y1: y(100), y2: y(100), class: "ref-line" }));
      svg.append(svgEl("text", { x: L + 4, y: y(100) - 6, class: "label" }, "Human level"));
      // trend line through points
      const sorted = points.slice().sort((a, b) => a.t - b.t);
      svg.append(svgEl("path", { class: "trend-path", d: sorted.map((p, i) => `${i ? "L" : "M"}${x(p.t)} ${y(p.v)}`).join("") }));
      sorted.forEach((p) => {
        const c = svgEl("circle", { cx: x(p.t), cy: y(p.v), r: 6, class: p.pre_2026 ? "pt pre" : "pt" });
        c.addEventListener("mousemove", (e) => {
          tooltip.innerHTML = `<b>${esc(p.name)}</b><br>released ${p.release_date}<br>${metrics[metric]}: ${p.v.toFixed(0)}% of human<br>best method: ${p.method}`;
          tooltip.hidden = false;
          tooltip.style.left = `${e.clientX + 14}px`; tooltip.style.top = `${e.clientY + 14}px`;
        });
        c.addEventListener("mouseleave", () => { tooltip.hidden = true; });
        svg.append(c);
        svg.append(svgEl("text", { x: x(p.t), y: y(p.v) - 11, "text-anchor": "middle", class: "value-label" }, p.name.split(" ")[0]));
      });
      container.append(svg);
    }
    draw();
    document.querySelector(".theme-toggle").addEventListener("click", () => setTimeout(draw, 0));
  }

  /* ------------------------------------------------------------ idea watch */
  function watch(live) {
    const filter = document.getElementById("watch-filter");
    const list = document.getElementById("watch-list");
    const counts = { all: live.watch.length, verified: 0, watching: 0 };
    live.watch.forEach((w) => { counts[w.status] += 1; });
    let state = "all";
    [["all", "All"], ["verified", "Verified"], ["watching", "Still watching"]].forEach(([k, name]) => {
      const b = document.createElement("button");
      b.type = "button"; b.dataset.value = k; b.setAttribute("aria-checked", String(k === state));
      b.innerHTML = `${name} <span class="count">${counts[k]}</span>`;
      filter.append(b);
    });
    filter.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      state = b.dataset.value;
      filter.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
      render();
    });
    function render() {
      list.innerHTML = live.watch.filter((w) => state === "all" || w.status === state).map((w) => `
        <article class="watch-card ${w.status}">
          <div class="watch-top">
            <span class="status">${w.status === "verified" ? "✓ Verified" : "◷ Watching"}</span>
            <span class="muted">${esc(w.area)}</span>
          </div>
          <p class="watch-problem">${esc(w.problem)}</p>
          <div class="doc ai"><span class="tag">${esc(w.model)} · ${esc(w.method)} · written from 2025 snapshot</span>${esc(w.proposal)}</div>
          ${w.paper
            ? `<div class="doc human"><span class="tag">Later human paper · ${esc(w.paper.date)}</span><a href="${esc(w.paper.url)}">${esc(w.paper.title)}</a> took the same approach. Verified in edition ${esc(w.verified_in)}.</div>`
            : `<div class="doc pending"><span class="tag">No matching human paper yet</span>Re-checked at every edition.</div>`}
          ${voteBar(w)}
        </article>`).join("");
      bindVotes(list);
    }
    render();
  }

  /* ------------------------------------------------------------ votes */
  // Votes: each visitor's own vote is kept in localStorage; aggregate counts come from
  // live.json ("votes": {"up": n, "down": n}), refreshed at each edition.
  const VOTE_KEY = "ideataste-votes";
  const loadVotes = () => { try { return JSON.parse(localStorage.getItem(VOTE_KEY)) || {}; } catch (e) { return {}; } };
  const saveVotes = (v) => { try { localStorage.setItem(VOTE_KEY, JSON.stringify(v)); } catch (e) { /* ignore */ } };
  const voteData = {};
  function voteBar(w) {
    voteData[w.id] = { up: (w.votes && w.votes.up) || 0, down: (w.votes && w.votes.down) || 0 };
    const q = w.status === "verified"
      ? "Would you have pursued this idea before the paper appeared?"
      : "Is this an approach a community would pursue?";
    return `<div class="vote-bar" data-id="${esc(w.id)}">
      <span class="vote-q">${q}</span>
      <button type="button" class="vote up" data-v="up" aria-pressed="false">👍 Yes <span class="n"></span></button>
      <button type="button" class="vote down" data-v="down" aria-pressed="false">👎 No <span class="n"></span></button>
      <span class="vote-split"><i></i><b></b></span>
    </div>`;
  }
  function bindVotes(scope) {
    const mine = loadVotes();
    scope.querySelectorAll(".vote-bar").forEach((bar) => {
      const id = bar.dataset.id;
      const paint = () => {
        const v = mine[id];
        const up = voteData[id].up + (v === "up" ? 1 : 0), down = voteData[id].down + (v === "down" ? 1 : 0);
        bar.querySelector(".up .n").textContent = up;
        bar.querySelector(".down .n").textContent = down;
        bar.querySelectorAll(".vote").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === v)));
        const total = up + down;
        bar.querySelector(".vote-split i").style.width = total ? `${(100 * up) / total}%` : "0";
        bar.querySelector(".vote-split b").style.width = total ? `${(100 * down) / total}%` : "0";
      };
      bar.querySelectorAll(".vote").forEach((b) => b.addEventListener("click", () => {
        mine[id] = mine[id] === b.dataset.v ? undefined : b.dataset.v;
        saveVotes(mine); paint();
      }));
      paint();
    });
  }

  /* ---------------------------------------------------- overview video */
  const vBox = document.getElementById("video-lang");
  const vEl = document.getElementById("overview-video");
  if (vBox && vEl) {
    const SRC = { en: "assets/video/overview-en.mp4", zh: "assets/video/overview-zh.mp4" };
    vBox.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-lang]");
      if (!b || b.getAttribute("aria-checked") === "true") return;
      const t = vEl.currentTime, playing = !vEl.paused;
      vBox.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
      vEl.src = SRC[b.dataset.lang];
      vEl.addEventListener("loadedmetadata", function once() {
        vEl.removeEventListener("loadedmetadata", once);
        if (t && t < vEl.duration) vEl.currentTime = t;
        if (playing) vEl.play().catch(() => {});
      });
    });
  }
})();
