// @ts-nocheck — 본문은 타입 검사를 안 받는다.
//
// `graph_view.py` 에서 그대로 옮긴 바닐라 JS 라 클로저 인자가 서른 몇 개인데,
// 전부 `any` 로 적으면 아무것도 보장하지 않으면서 diff 만 커진다. 검사가 필요한
// 자리는 밖과의 접점 하나뿐이고, `mountGraph` 의 시그니처가 그것을 든다.
//
// 여기가 깨지면 지도가 안 그려진다. 조용히 틀리는 종류의 코드가 아니다.

/* 규칙 그래프. `tool/graph_view.py` 의 SCRIPT 를 그대로 옮겼다.

   바꾼 것은 셋뿐이다 — 데이터를 인자로 받고, DOM 을 문서가 아니라 뿌리에서
   찾고, 멈출 손잡이를 돌려준다. 물리와 그리기는 손대지 않았다. 다시 쓰면
   같은 화면을 두 번 만들게 되고, 두 벌은 어긋난다. */

export function mountGraph(root: HTMLElement, DATA: any): () => void {
  let stopped = false;

  const LAYER: Record<number, string> =
      Object.fromEntries(DATA.ladder.map((r: any) => [r.n, r.color]));
  const W = 900, H = 560;
  const svg = root.querySelector("#canvas")!;
  const view = root.querySelector("#view")!;
  const panel = root.querySelector("#panel")!;
  const search = root.querySelector("#search")!;
  const byId = Object.fromEntries(DATA.nodes.map(n => [n.id, n]));

  let project = "all";       // 어느 프로젝트 눈으로 보는가
  let selected: string | null = null;
  let hovered = null;
  let query = "";
  const layersOff = new Set();

  /* --- 크기와 시작 자리 -----------------------------------------------------
     크기는 주입 글자수다. 옵시디언은 링크 수로 재지만, 여기서 비싼 것은 많이
     이어진 페이지가 아니라 한 턴에 많이 실리는 페이지다. 안 실리는 규칙은 작은
     고정 크기다 — 비용이 0인 것이 커 보이면 뜻이 뒤집힌다. */
  const maxChars = Math.max(...DATA.nodes.map(n => n.injected ? n.chars : 0), 1);
  DATA.nodes.forEach((n, i) => {
    n.r = n.injected ? 13 + 21 * Math.sqrt(n.chars / maxChars) : 8.5;
    const a = (i / DATA.nodes.length) * Math.PI * 2;
    n.x = W / 2 + Math.cos(a) * 190;
    n.y = H / 2 + Math.sin(a) * 140;
    n.vx = n.vy = 0; n.fx = n.fy = null;
  });

  function edgesFor(key) {
    return DATA.links.filter((l: any) => l.kind === "link" || (l.by[key] || 0) > 0)
      .map(l => ({...l, weight: l.kind === "link" ? 0 : l.by[key]}));
  }
  let edges = edgesFor("all");
  let maxW = 1;

  /* --- 힘 계산. 옵시디언처럼 살아 있게 돌린다 ------------------------------ */
  const sim = {alpha: 1, running: false};
  function tick() {
    for (const a of DATA.nodes) {
      for (const b of DATA.nodes) {
        if (a === b) continue;
        const dx = a.x - b.x, dy = a.y - b.y;
        const d2 = dx * dx + dy * dy || 0.01, d = Math.sqrt(d2);
        const push = Math.min(30000 / d2, 40);
        a.vx += (dx / d) * push; a.vy += (dy / d) * push;
      }
    }
    for (const l of edges) {
      const a = byId[l.a], b = byId[l.b];
      if (!a || !b) continue;
      const dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.hypot(dx, dy) || 0.01;
      const rest = l.kind === "link" ? 165 : 125;
      const k = l.kind === "link" ? 0.013 : 0.006 + 0.016 * (l.weight / maxW);
      const f = (d - rest) * k;
      a.vx += (dx / d) * f; a.vy += (dy / d) * f;
      b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
    }
    for (const n of DATA.nodes) {
      if (n.fx !== null) { n.x = n.fx; n.y = n.fy; n.vx = n.vy = 0; continue; }
      n.vx += (W / 2 - n.x) * 0.0018; n.vy += (H / 2 - n.y) * 0.0026;
      n.x += (n.vx *= 0.80) * sim.alpha;
      n.y += (n.vy *= 0.80) * sim.alpha;
      n.x = Math.max(n.r + 64, Math.min(W - n.r - 64, n.x));
      n.y = Math.max(n.r + 26, Math.min(H - n.r - 26, n.y));
    }
  }
  function loop() {
    if (stopped) { sim.running = false; return; }
    for (let i = 0; i < 2; i++) tick();
    sim.alpha *= 0.986;
    place();
    if (sim.alpha > 0.004) requestAnimationFrame(loop);
    else sim.running = false;
  }
  function kick(a) {
    sim.alpha = Math.max(sim.alpha, a === undefined ? 0.55 : a);
    if (!sim.running) { sim.running = true; requestAnimationFrame(loop); }
  }

  /* --- 그리기 -------------------------------------------------------------- */
  const NS = "http://www.w3.org/2000/svg";
  const make = (tag, attrs) => {
    const el = document.createElementNS(NS, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    return el;
  };
  const gEdges = make("g", {}), gNodes = make("g", {});
  view.appendChild(gEdges); view.appendChild(gNodes);

  let edgeEls = [];
  function drawEdges() {
    gEdges.textContent = "";
    maxW = Math.max(...edges.map(l => l.weight), 1);
    edgeEls = edges.map(l => {
      if (!byId[l.a] || !byId[l.b]) return null;
      const el = make("line", {
        stroke: "currentColor",
        "stroke-opacity": l.kind === "link" ? 0.45 : 0.32,
        "stroke-width": l.kind === "link" ? 1.4 : 1 + 2.6 * (l.weight / maxW),
        "stroke-dasharray": l.kind === "link" ? "none" : "4 4",
      });
      el.style.color = "var(--ink-faint)";
      el.dataset.a = l.a; el.dataset.b = l.b; el.dataset.kind = l.kind;
      gEdges.appendChild(el);
      return el;
    }).filter(Boolean);
  }

  const nodeEls = DATA.nodes.map(n => {
    const g = make("g", {class: "node", tabindex: "0", role: "button"});
    g.dataset.id = n.id;
    g.setAttribute("aria-label", n.label);
    const circle = make("circle", {r: n.r});
    const label = make("text", {"text-anchor": "middle"});
    label.textContent = n.label;
    g.appendChild(circle); g.appendChild(label);
    gNodes.appendChild(g);
    g.addEventListener("click", e => { if (!dragged) select(n.id); e.stopPropagation(); });
    g.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(n.id); }
    });
    g.addEventListener("pointerenter", () => { hovered = n.id; paint(); });
    g.addEventListener("pointerleave", () => { hovered = null; paint(); });
    g.addEventListener("pointerdown", e => startDrag(e, n));
    return {g, circle, label, n};
  });

  /* 노드의 pointerleave 만 믿으면 안 된다. 배치가 살아 있어서 노드가 가만히 있는
     커서 밑으로 들어왔다 나가고, 그 사이에 enter 만 오고 leave 가 안 오는 일이
     생긴다. 실제로 탭을 바꾸자 강조가 한 노드에 붙어 안 풀렸다. 그래서 판 전체를
     벗어나면 무조건 푼다. */
  svg.addEventListener("pointerleave", () => { hovered = null; paint(); });

  function place() {
    for (const {g, circle, label, n} of nodeEls) {
      circle.setAttribute("cx", n.x); circle.setAttribute("cy", n.y);
      label.setAttribute("x", n.x); label.setAttribute("y", n.y + n.r + 15);
    }
    for (const el of edgeEls) {
      const a = byId[el.dataset.a], b = byId[el.dataset.b];
      el.setAttribute("x1", a.x); el.setAttribute("y1", a.y);
      el.setAttribute("x2", b.x); el.setAttribute("y2", b.y);
    }
  }

  const neighbours = {};
  function rebuildNeighbours() {
    DATA.nodes.forEach(n => neighbours[n.id] = new Set([n.id]));
    for (const l of edges) {
      if (!byId[l.a] || !byId[l.b]) continue;
      neighbours[l.a].add(l.b); neighbours[l.b].add(l.a);
    }
  }

  const hidden = n =>
    layersOff.has(n.layer) ||
    (query && !(n.id + " " + n.headline + " " + n.rule).toLowerCase().includes(query));

  function paint() {
    const focus = hovered || selected;
    const keep = focus ? neighbours[focus] : null;
    for (const {g, circle, n} of nodeEls) {
      const gone = hidden(n);
      g.classList.toggle("off", gone);
      g.classList.toggle("sel", n.id === selected);
      g.classList.toggle("dim", !gone && !!keep && !keep.has(n.id));
      const here = project === "all" ? "on" : n.status[project];
      const away = here === "none" || here === "foreign";
      circle.setAttribute("fill", LAYER[n.layer]);
      circle.setAttribute("fill-opacity", away ? 0.10 : n.injected ? 0.92 : 0.42);
      circle.setAttribute("stroke", n.severity === "landmine" ? "var(--ink)" : LAYER[n.layer]);
      circle.setAttribute("stroke-width", n.severity === "landmine" ? 2.5 : 1.5);
      circle.setAttribute("stroke-dasharray",
        away ? "2 3" : n.severity === "preference" ? "3 3" : "none");
    }
    for (const el of edgeEls) {
      const a = byId[el.dataset.a], b = byId[el.dataset.b];
      const gone = hidden(a) || hidden(b);
      el.classList.toggle("off", gone);
      el.classList.toggle("dim", !gone && !!keep && !(keep.has(a.id) && keep.has(b.id)));
    }
  }

  /* --- 끌기·확대·이동 ------------------------------------------------------ */
  let tx = 0, ty = 0, k = 1, dragged = false;
  const applyView = () => view.setAttribute("transform", `translate(${tx} ${ty}) scale(${k})`);
  function pointer(e) {
    const r = svg.getBoundingClientRect();
    return [
      ((e.clientX - r.left) / r.width * W - tx) / k,
      ((e.clientY - r.top) / r.height * H - ty) / k,
    ];
  }
  function startDrag(e, n) {
    e.stopPropagation(); dragged = false;
    const move = ev => {
      dragged = true;
      const [x, y] = pointer(ev);
      n.fx = x; n.fy = y; kick(0.35);
    };
    const up = () => {
      n.fx = n.fy = null;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setTimeout(() => { dragged = false; }, 0);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }
  svg.addEventListener("pointerdown", e => {
    if (e.target.closest(".node")) return;
    svg.classList.add("grabbing");
    const sx = e.clientX, sy = e.clientY, ox = tx, oy = ty;
    const r = svg.getBoundingClientRect();
    const move = ev => {
      tx = ox + (ev.clientX - sx) / r.width * W;
      ty = oy + (ev.clientY - sy) / r.height * H;
      applyView();
    };
    const up = () => {
      svg.classList.remove("grabbing");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });
  svg.addEventListener("wheel", e => {
    e.preventDefault();
    const [px, py] = pointer(e);
    const next = Math.max(0.4, Math.min(3.2, k * ((e as WheelEvent).deltaY < 0 ? 1.12 : 1 / 1.12)));
    tx += px * (k - next); ty += py * (k - next);
    k = next; applyView();
  }, {passive: false});

  root.querySelector("#reset")!.addEventListener("click", () => {
    tx = ty = 0; k = 1; applyView();
    DATA.nodes.forEach((n: any) => { n.fx = n.fy = null; });
    selected = null; panel.innerHTML = openingPanel(); kick(1); paint();
  });

  /* --- 옆 패널 ------------------------------------------------------------- */
  const esc = (s: unknown) =>
    String(s).replace(/[&<>]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;"})[c] ?? c);
  const TAG = {on: ["on", "붙음"], partial: ["partial", "일부만"], none: ["none", "안 붙음"],
               prose: ["none", "산문뿐"], foreign: ["none", "다른 저장소"]};

  function select(id: string) {
    selected = id;
    const n = byId[id];
    const key = project === "all" ? "all" : project;
    const co = DATA.links
      .filter(l => l.kind === "co" && (l.a === id || l.b === id) && (l.by[key] || 0) > 0)
      .map((l: any) => ({name: (l.a === id ? l.b : l.a).split("/")[1], w: l.by[key]}))
      .sort((x: any, y: any) => y.w - x.w)
      .map((o: any) => `<span class="pair">${esc(o.name)} <code>${o.w}회</code></span>`);

    const rows = [
      ["범위", esc(n.scope)],
      ["등급", `<code>${esc(n.severity)}</code>`],
      ["층", n.layers.map((x: number) => `<code>${x}</code>`).join(" ")],
      ["주입", n.injected ? `${n.chars.toLocaleString()}자 · 트리거 ${n.triggers.length}개` : "안 실림"],
    ];
    // 본문에 남은 `{빈칸}` 은 고장이 아니라 슬롯이다. 값은 어댑터가 채운다.
    const slots = [...new Set(n.rule.match(/\{[a-z_]+\}/g) || [])];
    if (slots.length) rows.push(["슬롯", slots.map(s => `<code>${esc(s)}</code>`).join(" ") + " — 어댑터가 채운다"]);
    if (n.deny.length) rows.push(["차단", n.deny.map((d: string) => `<code>${esc(d)}</code>`).join(" ")]);
    if (n.pretooluse) rows.push(["검사", `<code>${esc(n.pretooluse)}</code>`]);
    if (n.skills.length) rows.push(["스킬", n.skills.map((s: string) => `<code>${esc(s)}</code>`).join(" ")]);

    const where = DATA.projects.map((p: any) => {
      const [cls, text] = (TAG as Record<string, string[]>)[n.status[p.key]] || TAG.none;
      return `<span class="pair"><span class="tagline ${cls}">${text}</span> ${esc(p.short)}</span>`;
    });
    if (where.length) rows.push(["프로젝트", where.join("<br>")]);
    if (co.length) rows.push(["함께<br>실림", co.join("<br>")]);
    if (n.sources.length) rows.push(["근거", n.sources.map((s: string) => `<code>${esc(s)}</code>`).join("<br>")]);

    panel.innerHTML =
      `<h3>${esc(n.headline)}</h3><p class="path">${esc(n.id)}.md</p>` +
      (n.rule ? `<p>${esc(n.rule)}</p>` : "") +
      "<dl>" + rows.map(([a, b]) => `<dt>${a}</dt><dd>${b}</dd>`).join("") + "</dl>";
    paint();
  }

  function openingPanel() {
    if (project === "all") {
      return '<p class="hint">노드를 눌러 규칙을 편다. 끌어서 옮기고, 휠로 확대하고, ' +
        '위 탭으로 프로젝트를 바꾼다.</p>';
    }
    const p = DATA.projects.find((x: any) => x.key === project);
    const rows = [
      ["어댑터", p.adapter ? `<code>${esc(p.adapter)}</code>` : "없음"],
      ["주입 훅", p.inject ? "붙음" : "안 붙음"],
      ["deny", `${p.deny}개`],
      ["검사 훅", `${p.hooks}개`],
      ["코퍼스", p.corpus ? `${p.corpus.toLocaleString()}발화` : "없음"],
    ];
    if (p.missing.length) rows.push(["빈 슬롯", p.missing.map((s: string) => `<code>{${esc(s)}}</code>`).join(" ")]);
    return `<h3>${esc(p.short)}</h3><p class="path">${esc(p.path)}</p>` +
      `<p>${esc(p.note)}</p><dl>` +
      rows.map(([a, b]) => `<dt>${a}</dt><dd>${b}</dd>`).join("") + "</dl>";
  }

  /* --- 조작 ---------------------------------------------------------------- */
  root.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => {
      project = (btn as HTMLElement).dataset.project!;
      hovered = null;   // 배치가 다시 흔들리므로 들고 있던 강조는 뜻을 잃는다
      root.querySelectorAll(".tab").forEach(b =>
        b.setAttribute("aria-pressed", String(b === btn)));
      edges = edgesFor(project === "all" ? "all" : project);
      drawEdges(); rebuildNeighbours(); place();
      if (selected) select(selected); else panel.innerHTML = openingPanel();
      kick(0.5); paint();
    });
  });
  root.querySelectorAll(".legend .chip").forEach(btn => {
    btn.addEventListener("click", () => {
      const n = Number((btn as HTMLElement).dataset.layer);
      if (layersOff.has(n)) layersOff.delete(n); else layersOff.add(n);
      btn.setAttribute("aria-pressed", String(!layersOff.has(n)));
      paint();
    });
  });
  search.addEventListener("input", () => { query = (search as HTMLInputElement).value.trim().toLowerCase(); paint(); });

  drawEdges(); rebuildNeighbours(); place(); paint();
  panel.innerHTML = openingPanel();
  kick(1);
  return () => { stopped = true; };
}
