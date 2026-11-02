/* IdeaTaste project page: leaderboard and charts. No dependencies. */
(function () {
  "use strict";

  const METRICS = ["match_cite", "match_idea", "diversity_cite", "diversity_idea"];
  const METRIC_NAMES = { match_cite: "Match-Cite", match_idea: "Match-Idea",
                         diversity_cite: "Diversity-Cite", diversity_idea: "Diversity-Idea" };
  const METHOD_NAMES = { free: "Free", topic: "Topic", landscape: "Landscape", frontier: "Frontier" };
  const AREA_SHORT = { ml_systems: "ML systems", code_generation: "Code generation",
                       world_models: "World models", automated_research: "Automated research" };
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const methodColor = (m) => css(`--m-${m}`);
  const fmt = (x, digits = 1) => x.toFixed(digits);
  const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
  const el = (tag, attrs = {}, html = "") => {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
    node.innerHTML = html;
    return node;
  };
  const SVG = "http://www.w3.org/2000/svg";
  const svgEl = (tag, attrs = {}, text) => {
    const node = document.createElementNS(SVG, tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
    if (text !== undefined) node.textContent = text;
    return node;
  };

  /* ------------------------------------------------------------- theme */
  const root = document.documentElement;
  try {
    const saved = localStorage.getItem("ideataste-theme");
    if (saved) root.dataset.theme = saved;
  } catch (e) { /* storage unavailable: follow the system theme */ }
  const redrawers = [];
  document.querySelector(".theme-toggle").addEventListener("click", () => {
    const dark = root.dataset.theme
      ? root.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("ideataste-theme", root.dataset.theme); } catch (e) { /* ignore */ }
    redrawers.forEach((draw) => draw());
  });

  /* ------------------------------------------------------------- tooltip */
  const tooltip = document.querySelector(".tooltip");
  function showTip(event, html) {
    tooltip.innerHTML = html;
    tooltip.hidden = false;
    const pad = 14;
    const { innerWidth: w } = window;
    const rect = tooltip.getBoundingClientRect();
    let x = event.clientX + pad;
    if (x + rect.width > w - 8) x = event.clientX - rect.width - pad;
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${event.clientY + pad}px`;
  }
  const hideTip = () => { tooltip.hidden = true; };

  /* ------------------------------------------------------------- copy */
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const text = document.querySelector(button.dataset.copy).textContent;
      try { await navigator.clipboard.writeText(text); button.textContent = "Copied"; }
      catch (e) { button.textContent = "Select and copy"; }
      setTimeout(() => { button.textContent = "Copy"; }, 1600);
    });
  });

  /* =============================================================== charts */
  /** Horizontal bar chart. groups: row labels; series: [{name, color, values}];
   *  options: {max, ticks, reference: {value, label}, unit, height per row}. */
  function barChart(container, groups, series, options) {
    const draw = () => {
      container.innerHTML = "";
      if (series.length > 1) {
        const legend = el("div", { class: "legend" });
        series.forEach((s) => legend.append(el("span", {}, `<i style="background:${s.color()}"></i>${s.name}`)));
        if (options.reference) legend.append(el("span", {}, `<i class="line" style="background:${css("--human")}"></i>${options.reference.label}`));
        container.append(legend);
      }
      const labelWidth = options.labelWidth || 110;
      const width = 560, barH = Math.min(16, 22 - series.length * 2), gap = 3;
      const groupH = series.length * (barH + gap) + 14;
      const top = 6, height = top + groups.length * groupH + 24;
      const plotW = width - labelWidth - 44;
      const x = (v) => labelWidth + (Math.min(v, options.max) / options.max) * plotW;
      const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, role: "img",
                                 "aria-label": container.getAttribute("aria-label") || "" });
      const axis = svgEl("g", { class: "axis" });
      options.ticks.forEach((t) => {
        axis.append(svgEl("line", { x1: x(t), x2: x(t), y1: top, y2: height - 20 }));
        axis.append(svgEl("text", { x: x(t), y: height - 4, "text-anchor": "middle" }, `${t}${options.unit || ""}`));
      });
      svg.append(axis);
      groups.forEach((group, g) => {
        const y0 = top + g * groupH;
        svg.append(svgEl("text", { x: labelWidth - 10, y: y0 + (series.length * (barH + gap)) / 2 + 4,
                                   "text-anchor": "end", class: "label strong" }, group));
        series.forEach((s, i) => {
          const v = s.values[g];
          const y = y0 + i * (barH + gap);
          const w = Math.max(x(v) - labelWidth, 1.5);
          const r = Math.min(4, w / 2);
          svg.append(svgEl("path", { fill: s.color(),
            d: `M${labelWidth} ${y}h${w - r}a${r} ${r} 0 0 1 ${r} ${r}v${barH - 2 * r}a${r} ${r} 0 0 1 -${r} ${r}h-${w - r}z` }));
          if (options.labelBars !== false) {
            svg.append(svgEl("text", { x: labelWidth + w + 6, y: y + barH - 3, class: "value-label" },
                             `${fmt(v, options.digits ?? 1)}${options.unit || ""}`));
          }
          const hit = svgEl("rect", { x: labelWidth, y: y - 1, width: plotW + 40, height: barH + gap, class: "hit" });
          hit.addEventListener("mousemove", (e) => showTip(e, `<b>${group}</b><br>${s.name}: ${fmt(v, options.digits ?? 1)}${options.unit || ""}${options.tip ? options.tip(g, i) : ""}`));
          hit.addEventListener("mouseleave", hideTip);
          svg.append(hit);
        });
      });
      if (options.reference) {
        const rx = x(options.reference.value);
        svg.append(svgEl("line", { x1: rx, x2: rx, y1: top - 4, y2: height - 20, class: "ref-line" }));
        if (series.length === 1) {
          svg.append(svgEl("text", { x: rx + 5, y: top + 8, class: "label" }, options.reference.label));
        }
      }
      container.append(svg);
    };
    draw();
    redrawers.push(draw);
  }

  /** Small multiples: one bar panel per metric, methods as rows. */
  function methodPanels(container, data) {
    const draw = () => {
      container.innerHTML = "";
      const legend = el("div", { class: "legend" });
      data.methods.forEach((m) => legend.append(el("span", {}, `<i style="background:${methodColor(m)}"></i>${METHOD_NAMES[m]}`)));
      legend.append(el("span", {}, `<i class="line" style="background:${css("--human")}"></i>Human level (100%)`));
      container.append(legend);
      const width = 560, panelW = 130, gapX = 12, barH = 14, gapY = 6, top = 22, labelPad = 0;
      const height = top + data.methods.length * (barH + gapY) + 18;
      const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, role: "img",
                                 "aria-label": "Each metric as a share of the human level, by method, averaged over models and areas" });
      METRICS.forEach((metric, p) => {
        const values = data.methods.map((m) => relativeAverage(data, metric, { method: m }));
        const max = metric.startsWith("match") ? 40 : 160;
        const x0 = labelPad + p * (panelW + gapX);
        const x = (v) => x0 + (Math.min(v, max) / max) * panelW;
        svg.append(svgEl("text", { x: x0, y: 12, class: "label strong" }, METRIC_NAMES[metric]));
        svg.append(svgEl("line", { x1: x0, x2: x0, y1: top - 4, y2: height - 16, class: "gridline" }));
        values.forEach((v, i) => {
          const y = top + i * (barH + gapY);
          const w = Math.max(x(v) - x0, 1.5), r = Math.min(4, w / 2);
          svg.append(svgEl("path", { fill: methodColor(data.methods[i]),
            d: `M${x0} ${y}h${w - r}a${r} ${r} 0 0 1 ${r} ${r}v${barH - 2 * r}a${r} ${r} 0 0 1 -${r} ${r}h-${w - r}z` }));
          const hit = svgEl("rect", { x: x0, y: y - 2, width: panelW, height: barH + gapY, class: "hit" });
          hit.addEventListener("mousemove", (e) => showTip(e, `<b>${METRIC_NAMES[metric]}</b><br>${METHOD_NAMES[data.methods[i]]}: ${fmt(v)}% of human`));
          hit.addEventListener("mouseleave", hideTip);
          svg.append(hit);
        });
        if (100 <= max) {
          svg.append(svgEl("line", { x1: x(100), x2: x(100), y1: top - 4, y2: height - 16, class: "ref-line" }));
        }
        svg.append(svgEl("text", { x: x0, y: height - 2, class: "value-label" }, "0"));
        svg.append(svgEl("text", { x: x0 + panelW, y: height - 2, class: "value-label", "text-anchor": "end" }, `${max}%`));
      });
      container.append(svg);
    };
    draw();
    redrawers.push(draw);
  }

  /** Mean over models, areas (and methods unless fixed) of score / human level, in %. */
  function relativeAverage(data, metric, { method = null, model = null } = {}) {
    const ratios = [];
    data.models.forEach((m) => {
      if (model && m.key !== model) return;
      data.areas.forEach((a) => {
        data.methods.forEach((me) => {
          if (method && me !== method) return;
          ratios.push(data.scores[m.key][a.key][me][metric] / data.human[a.key][metric]);
        });
      });
    });
    return 100 * mean(ratios);
  }

  /* ---------------------------------------------- per-slot data (paper Table 3) */
  // Share of human papers matched on each slot (problem, motivation, approach, plan),
  // per area in the order ML systems, code generation, world models, automated research.
  const SLOTS = ["Problem", "Motivation", "Approach", "Research plan"];
  const SLOT_DATA = {
    human: [[28.32, 42.58, 3.99, 7.21], [24.74, 33.19, 4.21, 3.64], [25.12, 29.41, 7.12, 6.16], [19.10, 38.29, 4.49, 2.99]],
    llama: [ // free, topic, landscape, frontier per area
      [[7.09, 17.62, 0.81, 1.45], [10.00, 20.34, 0.87, 0.94], [8.54, 18.04, 0.87, 2.35], [12.10, 23.46, 1.29, 1.52]],
      [[6.73, 6.99, 1.87, 1.07], [6.13, 10.10, 1.63, 2.61], [2.93, 4.30, 1.13, 1.01], [7.50, 10.16, 1.63, 0.77]],
      [[4.02, 5.25, 1.18, 0.91], [7.02, 10.28, 2.09, 1.23], [1.71, 2.25, 0.37, 1.45], [5.52, 8.03, 2.25, 1.39]],
      [[6.95, 14.96, 3.35, 0.44], [5.28, 14.08, 1.58, 0.53], [5.99, 15.32, 2.38, 0.62], [4.23, 13.12, 1.41, 0.09]]],
    deepseek: [
      [[1.04, 1.12, 0.23, 0.08], [1.77, 3.01, 0.10, 0.04], [1.31, 2.18, 0.12, 0.12], [1.04, 2.04, 0.06, 0.02]],
      [[0.89, 1.21, 0.00, 0.00], [1.63, 1.69, 0.12, 0.00], [1.19, 1.60, 0.18, 0.00], [1.42, 2.04, 0.21, 0.00]],
      [[2.95, 1.98, 0.27, 0.00], [2.68, 3.00, 0.64, 0.21], [3.48, 4.18, 0.16, 0.05], [2.36, 2.73, 0.11, 0.00]],
      [[2.11, 3.43, 0.26, 0.00], [3.35, 4.75, 0.44, 0.09], [2.38, 3.43, 0.62, 0.09], [3.08, 4.23, 0.26, 0.00]]],
  };
  const slotMean = (rows, s) => mean(rows.map((area) => (Array.isArray(area[0]) ? mean(area.map((m) => m[s])) : area[s])));

  /* --------------------------------------------- human evaluation (paper Table 2) */
  const REVIEW_DIMS = ["Soundness", "Presentation", "Contribution", "Feasibility", "Success", "Overall rating"];
  const REVIEW = {
    human: [49.83, 62.50, 53.99, 75.39, 70.70, 49.48],
    matched: [40.62, 58.68, 45.49, 66.15, 54.17, 39.17],
    unmatched: [36.46, 57.64, 45.14, 61.46, 46.61, 37.92],
  };

  /* =============================================================== leaderboard */
  function leaderboard(data) {
    const state = { area: "all", scale: "raw", methods: new Set(data.methods), sort: null, dir: -1 };
    const tbody = document.querySelector("#board tbody");
    const areaFilter = document.getElementById("area-filter");
    const methodFilter = document.getElementById("method-filter");

    [{ key: "all", name: "All areas" }, ...data.areas].forEach((a) => {
      const b = el("button", { type: "button", role: "radio", "data-value": a.key,
                               "aria-checked": String(a.key === state.area) }, AREA_SHORT[a.key] || a.name);
      areaFilter.append(b);
    });
    data.methods.forEach((m) => {
      methodFilter.append(el("button", { type: "button", "data-value": m, "aria-pressed": "true" },
                             `<span class="method-key" style="background:var(--m-${m})"></span>${METHOD_NAMES[m]}`));
    });
    const radio = (group, key) => group.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      group.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
      state[key] = b.dataset.value; render();
    });
    radio(areaFilter, "area");
    radio(document.getElementById("scale-filter"), "scale");
    methodFilter.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      const m = b.dataset.value;
      if (state.methods.has(m) && state.methods.size > 1) state.methods.delete(m); else state.methods.add(m);
      b.setAttribute("aria-pressed", String(state.methods.has(m))); render();
    });
    document.querySelectorAll("#board th").forEach((th) => th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.sort === key) state.dir *= -1; else { state.sort = key; state.dir = key === "model" || key === "method" ? 1 : -1; }
      if (key === "model") state.sort = null;   // release order
      render();
    }));

    const areas = () => (state.area === "all" ? data.areas.map((a) => a.key) : [state.area]);
    const humanValue = (metric) => mean(areas().map((a) => data.human[a][metric]));
    function value(model, method, metric) {
      const xs = areas().map((a) => {
        const v = data.scores[model][a][method][metric];
        return state.scale === "raw" ? v : v / data.human[a][metric];
      });
      return 100 * mean(xs);
    }

    function render() {
      tbody.innerHTML = "";
      const rows = [];
      data.models.forEach((model, mi) => data.methods.forEach((method, ji) => {
        if (!state.methods.has(method)) return;
        const values = Object.fromEntries(METRICS.map((m) => [m, value(model.key, method, m)]));
        rows.push({ model, method, values, order: mi * 10 + ji });
      }));
      if (state.sort === "method") rows.sort((a, b) => state.dir * (data.methods.indexOf(a.method) - data.methods.indexOf(b.method)) || a.order - b.order);
      else if (state.sort) rows.sort((a, b) => state.dir * (a.values[state.sort] - b.values[state.sort]));
      else rows.sort((a, b) => a.order - b.order);

      const human = Object.fromEntries(METRICS.map((m) => [m, state.scale === "raw" ? 100 * humanValue(m) : 100]));
      const columnMax = Object.fromEntries(METRICS.map((m) => [m, Math.max(human[m], ...rows.map((r) => r.values[m]))]));
      const bestInGroup = {};
      rows.forEach((r) => METRICS.forEach((m) => {
        const k = `${r.model.key}/${m}`;
        bestInGroup[k] = Math.max(bestInGroup[k] ?? -Infinity, r.values[m]);
      }));

      const cell = (v, m, best) => {
        const width = (100 * v) / columnMax[m], ref = (100 * human[m]) / columnMax[m];
        const text = state.scale === "raw" ? fmt(v, 2) : `${fmt(v, 0)}%`;
        return `<td class="${best ? "best" : ""}"><div class="cell"><span class="bar"><i style="width:${width}%"></i><b style="left:calc(${ref}% - 1px)"></b></span><span class="value">${text}</span></div></td>`;
      };

      const humanRow = el("tr", { class: "human-row" },
        `<td class="left" colspan="2">Human level <span class="model-meta">2026 papers scored against one another</span></td>`
        + METRICS.map((m) => cell(human[m], m, false)).join(""));
      tbody.append(humanRow);

      let previous = null;
      rows.forEach((r) => {
        const grouped = !state.sort;
        const first = grouped && previous !== r.model.key;
        const tr = el("tr", { class: first ? "group-start" : "" });
        const modelCell = !grouped || first
          ? `<span class="model-name">${r.model.name}</span>${r.model.pre_2026 ? '<span class="badge" title="Released before 2026: cannot have seen any 2026 paper">pre-2026</span>' : ""}<span class="model-meta">released ${r.model.release_date}</span>`
          : "";
        tr.innerHTML = `<td class="left">${modelCell}</td>`
          + `<td class="left"><span class="method-cell"><span class="method-key" style="background:var(--m-${r.method})"></span>${METHOD_NAMES[r.method]}</span></td>`
          + METRICS.map((m) => cell(r.values[m], m, grouped && r.values[m] === bestInGroup[`${r.model.key}/${m}`])).join("");
        tbody.append(tr);
        previous = r.model.key;
      });

      document.querySelectorAll("#board th").forEach((th) => {
        const key = th.dataset.sort;
        th.setAttribute("aria-sort", state.sort === key ? (state.dir > 0 ? "ascending" : "descending") : "none");
      });
      document.getElementById("board-note").textContent =
        (state.scale === "raw" ? "Scores in %. " : "Each score divided by the human level of its area, in %. ")
        + (state.area === "all" ? "Averaged over the four areas. " : "")
        + "Bars are scaled per column; the amber tick marks the human level. Bold: best method within a model.";
    }
    render();
  }

  function areaTable(data) {
    const colors = ["--m-free", "--m-topic", "--m-landscape", "--m-frontier"];
    const tbody = document.querySelector("#area-table tbody");
    data.areas.forEach((a, i) => {
      tbody.append(el("tr", {}, `<td><span class="area-dot" style="background:var(${colors[i]})"></span>${a.name}</td>`
        + `<td>${a.corpus.toLocaleString("en-US")}</td><td>${a.reference.toLocaleString("en-US")}</td>`));
    });
  }

  /* =============================================================== boot */
  fetch("assets/data/leaderboard.json")
    .then((r) => r.json())
    .then((data) => {
      areaTable(data);
      leaderboard(data);
      barChart(document.getElementById("chart-gap"), METRICS.map((m) => METRIC_NAMES[m]),
        [{ name: "LLM agents", color: () => css("--ai"), values: METRICS.map((m) => relativeAverage(data, m)) }],
        { max: 120, ticks: [0, 25, 50, 75, 100], unit: "%", reference: { value: 100, label: "Human level" }, digits: 0 });
      barChart(document.getElementById("chart-slots"), SLOTS, [
        { name: "Human papers", color: () => css("--human"), values: SLOTS.map((_, s) => slotMean(SLOT_DATA.human, s)) },
        { name: "Llama 4 Scout (pre-2026)", color: () => css("--m-free"), values: SLOTS.map((_, s) => slotMean(SLOT_DATA.llama, s)) },
        { name: "DeepSeek-V4-Flash", color: () => css("--m-frontier"), values: SLOTS.map((_, s) => slotMean(SLOT_DATA.deepseek, s)) },
      ], { max: 40, ticks: [0, 10, 20, 30, 40], unit: "%", labelWidth: 104 });
      methodPanels(document.getElementById("chart-methods"), data);
      barChart(document.getElementById("chart-human"), REVIEW_DIMS, [
        { name: "2026 papers", color: () => css("--human"), values: REVIEW.human },
        { name: "AI, idea matches a paper", color: () => css("--ai"), values: REVIEW.matched },
        { name: "AI, no matching paper", color: () => css("--m-frontier"), values: REVIEW.unmatched },
      ], { max: 100, ticks: [0, 25, 50, 75, 100], labelWidth: 104, labelBars: false, digits: 1 });
    })
    .catch((error) => {
      document.getElementById("board-note").textContent = `Could not load the leaderboard data (${error.message}).`;
    });
})();
