"use strict";
const $ = (id) => document.getElementById(id);
const roles = {
  coordinator: "Координатор",
  consolidator: "Консолидатор",
  distributor: "Распределитель",
  transit: "Транзит",
  terminal: "Конечный получатель",
  peripheral: "Периферия",
};
const colors = {
  coordinator: "#c0392b",
  consolidator: "#e08e0b",
  distributor: "#7b4bc4",
  transit: "#1f6fb2",
  terminal: "#2e8753",
  peripheral: "#a0a8b5",
};
let result = null,
  network = null,
  chatHistory = [],
  selected = null;
function text(tag, value, parent, cls) {
  const e = document.createElement(tag);
  e.textContent = value;
  if (cls) e.className = cls;
  if (parent) parent.append(e);
  return e;
}
function notice(value, error = false) {
  $("status").textContent = value;
  $("status").className = error ? "error" : "success";
}
async function request(path, body, raw = false) {
  const headers = {};
  if (body && !(body instanceof FormData))
    headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method: body ? "POST" : "GET",
    headers,
    body:
      body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let message = "Ошибка сервера: " + response.status;
    try {
      const error = await response.json();
      message = typeof error.detail === "string" ? error.detail : message;
    } catch {}
    throw Error(message);
  }
  return raw ? response : response.json();
}
async function connect() {
  try {
    const s = await request("/api/status");
    $("connection").textContent =
      "● Помощник · " +
      (s.online_available ? s.model : "офлайн, ключ не задан");
    $("connection").className = "";
  } catch (e) {
    $("connection").textContent = e.message;
    $("connection").className = "error";
  }
}

const names = {
  overview: "Обзор",
  graph: "Граф",
  priorities: "Приоритеты",
  clusters: "Кластеры",
  patterns: "Паттерны",
  resilience: "Устойчивость",
  gaps: "Белые пятна",
  assistant: "Ассистент",
};
function show(id) {
  document.querySelectorAll(".view").forEach((e) => (e.hidden = e.id !== id));
  document
    .querySelectorAll("nav button")
    .forEach((e) => e.classList.toggle("active", e.dataset.view === id));
  if (id === "graph" && network) {
    network.redraw();
    network.fit();
  }
}
Object.entries(names).forEach(([id, label]) => {
  const b = text("button", label, $("tabs"));
  b.dataset.view = id;
  b.onclick = () => show(id);
});
const labels = {
  gid: "ID клиента",
  role: "Роль",
  rank: "Место",
  priority_score: "Приоритет",
  why: "Обоснование",
  cluster_id: "Кластер",
  n_nodes: "Узлов",
  n_seed: "Seed",
  sum_kzt_internal: "Внутренний оборот",
  hypothesis: "Гипотеза",
  evidence: "Обоснование",
  path: "Маршрут",
  episodes: "Эпизодов",
  active_days: "Дней",
  src: "Отправитель",
  dst: "Получатель",
  day: "Дата",
  n_tx: "Операций",
  sum_kzt: "Сумма KZT",
  strategy: "Стратегия",
  n_removed: "Изъято",
  lcc_share: "Доля крупнейшей компоненты",
  flow_share: "Доля потока",
  request_type: "Запрос",
  gids: "Клиенты",
};
function table(parent, rows, columns) {
  parent.replaceChildren();
  if (!rows.length) {
    text("p", "Совпадений нет.", parent);
    return;
  }
  const wrap = text("div", "", parent, "table-wrap"),
    t = text("table", "", wrap),
    head = text("tr", "", text("thead", "", t));
  columns.forEach((k) => text("th", labels[k] || k, head));
  const body = text("tbody", "", t);
  rows.forEach((row) => {
    const tr = text("tr", "", body);
    columns.forEach((k) => {
      const td = text("td", "", tr);
      let v = row[k];
      if (k === "role") v = roles[v] || v;
      if (k === "priority_score" && typeof v === "number") v = v.toFixed(4);
      if (k === "gid") {
        const b = text("button", String(v), td, "id-link");
        b.onclick = () => findNode(String(v));
      } else td.textContent = v ?? "—";
    });
  });
}
function metric(label, value) {
  const m = text("div", "", $("metrics"), "metric");
  text("span", label, m);
  text("b", value, m);
}
function render() {
  chatHistory = [];
  $("chat").replaceChildren();
  $("node").replaceChildren();
  selected = null;
  $("gid").value = "";
  $("workspace").hidden = false;
  $("metrics").replaceChildren();
  metric("Участников", result.report.n_nodes.toLocaleString("ru"));
  metric("Связей", result.report.n_edges.toLocaleString("ru"));
  metric("Операций", result.n_transactions.toLocaleString("ru"));
  metric("Расчёт", result.report.elapsed_seconds.toFixed(1) + " с");
  renderCharts();
  const t = result.tables;
  table($("top-preview"), t.top_nodes.slice(0, 5), [
    "rank",
    "gid",
    "role",
    "priority_score",
    "why",
  ]);
  table($("top-table"), t.top_nodes, [
    "rank",
    "gid",
    "role",
    "priority_score",
    "why",
  ]);
  table($("cluster-table"), t.clusters, [
    "cluster_id",
    "n_nodes",
    "n_seed",
    "sum_kzt_internal",
    "hypothesis",
  ]);
  table($("resilience-table"), t.resilience || [], [
    "strategy",
    "n_removed",
    "lcc_share",
    "flow_share",
  ]);
  table($("gaps-table"), t.next_requests || [], [
    "request_type",
    "n_nodes",
    "gids",
    "why",
  ]);
  $("pattern-tables").replaceChildren();
  [
    [
      "repeated_routes",
      "Повторяющиеся цепочки",
      ["path", "episodes", "active_days", "evidence"],
    ],
    [
      "splitting",
      "Возможное дробление",
      ["src", "dst", "day", "n_tx", "sum_kzt", "evidence"],
    ],
    ["cycles", "Циклы", ["path", "length", "min_edge_kzt"]],
  ].forEach(([key, label, cols]) => {
    text("h3", label, $("pattern-tables"));
    table(text("div", "", $("pattern-tables")), t[key] || [], cols);
  });
  if (result.report.routes_search?.truncated)
    text(
      "p",
      "Поиск цепочек достиг лимита: показана только часть результатов.",
      $("pattern-tables"),
    );
  $("quality").textContent =
    result.quality + "\n\n" + JSON.stringify(result.report, null, 2);
  draw();
  show("overview");
}
$("upload").onsubmit = async (e) => {
  e.preventDefault();
  const files = [...$("files").files];
  if (files.length !== 3) return notice("Выберите ровно три файла.", true);
  if (files.reduce((s, f) => s + f.size, 0) > 3_000_000)
    return notice("Файлы превышают 3 МБ. Используйте локальный запуск.", true);
  const data = new FormData();
  files.forEach((f) => data.append("files", f));
  data.append("frontier", $("frontier").value);
  $("analyze").disabled = true;
  $("progress").hidden = false;
  notice(
    "Анализирую сеть. Обычно это занимает 1–3 минуты; не закрывайте вкладку.",
  );
  try {
    const next = await request("/api/analyze", data);
    result = next;
    render();
    notice(
      "Готово: " +
        result.report.n_nodes +
        " узлов. Все результаты относятся к загруженным файлам.",
    );
  } catch (error) {
    notice(
      error.message + (result ? " Ниже сохранён предыдущий результат." : ""),
      true,
    );
  } finally {
    $("analyze").disabled = false;
    $("progress").hidden = true;
  }
};
function draw() {
  if (!result) return;
  let nodes = result.graph.nodes,
    edges = result.graph.edges;
  if (selected) {
    const ids = new Set([selected]);
    edges.forEach((e) => {
      if (String(e.source) === selected) ids.add(String(e.target));
      if (String(e.target) === selected) ids.add(String(e.source));
    });
    nodes = nodes.filter((n) => ids.has(String(n.id)));
    edges = edges.filter(
      (e) => ids.has(String(e.source)) && ids.has(String(e.target)),
    );
  }
  const clustered = $("color").value === "cluster";
  const data = {
    nodes: nodes.map((n) => ({
      id: String(n.id),
      label: selected ? String(n.id) : "",
      title: String(n.id) + " · " + (roles[n.role] || n.role),
      color: clustered
        ? "hsl(" +
          (((Number(n.cluster ?? n.cluster_id) || 0) * 137.5) % 360) +
          ",55%,48%)"
        : colors[n.role],
      shape: n.is_seed ? "diamond" : "dot",
      size: 8 + 24 * (n.priority ?? n.priority_score ?? 0),
      x: selected ? undefined : n.x,
      y: selected ? undefined : n.y,
      borderWidth: String(n.id) === selected ? 4 : 1,
    })),
    edges: edges.map((e) => ({
      from: String(e.source),
      to: String(e.target),
      arrows: "to",
      title: Number(e.sum_kzt).toLocaleString("ru") + " KZT",
      width: 1.2,
    })),
  };
  if (network) network.destroy();
  network = new vis.Network($("network"), data, {
    physics: selected ? { stabilization: { iterations: 100 } } : false,
    interaction: { hover: true, navigationButtons: true },
    edges: {
      smooth: false,
      color: { color: "#647b8a", opacity: 1, inherit: false },
    },
    nodes: { font: { size: 11, color: "#d4eafa" } },
  });
  network.on("selectNode", (p) => {
    // Let vis finish processing the click before replacing its network instance.
    if (p.nodes.length) setTimeout(() => findNode(p.nodes[0]), 0);
  });
  $("graph-note").textContent =
    `Показано ${nodes.length} узлов и ${edges.length} направленных связей. Нажмите на узел для карточки.`;
  $("legend").replaceChildren();
  Object.entries(roles).forEach(([r, label]) => {
    const item = text("span", "", $("legend"));
    const dot = text("i", "", item);
    dot.style.background = colors[r];
    item.append(document.createTextNode(label));
  });
}
async function findNode(gid) {
  if (!result) return;
  gid = gid.trim();
  if (!result.graph.nodes.some((n) => String(n.id) === gid)) {
    notice("Узел не найден в текущей выборке.", true);
    return;
  }
  const snapshot = result;
  selected = gid;
  $("gid").value = gid;
  show("graph");
  draw();
  $("node").replaceChildren();
  text("p", "Загружаю карточку…", $("node"));
  try {
    const n = await request("/api/node", { token: result.token, gid });
    if (selected !== gid || result !== snapshot) return;
    $("node").replaceChildren();
    text("h2", "Клиент " + gid, $("node"));
    text(
      "p",
      (roles[n.role] || n.role) + " · приоритет " + n.priority_score,
      $("node"),
    );
    text("p", n.evidence, $("node"));
    text("h3", "Потоки", $("node"));
    text(
      "p",
      "Вход: " +
        (n.metrics.in_sum ?? 0).toLocaleString("ru") +
        " KZT · выход: " +
        (n.metrics.out_sum ?? 0).toLocaleString("ru") +
        " KZT",
      $("node"),
    );
    if (n.metrics.is_frontier)
      text("p", "Граница выборки: исходящие могут быть обрезаны.", $("node"));
    text("pre", n.rule_fired, $("node"));
    text("h3", "Баллы ролей", $("node"));
    Object.entries(n.scores || {}).forEach(([role, score]) =>
      text("p", (roles[role] || role) + ": " + (score ?? "—"), $("node")),
    );
    text("p", n.why || "", $("node"));
    [
      ["Входящие", n.incoming],
      ["Исходящие", n.outgoing],
    ].forEach(([label, rows]) => {
      text("h3", label, $("node"));
      table(text("div", "", $("node")), rows, [
        "gid",
        "role",
        "sum_kzt",
        "n_tx",
      ]);
    });
    const b = text("button", "AI-справка", $("node"));
    b.onclick = async () => {
      b.disabled = true;
      try {
        const a = await request("/api/brief", {
          token: snapshot.token,
          gid,
          online: true,
        });
        if (result !== snapshot || selected !== gid) return;
        text("p", a.text, $("node"));
        text("small", a.mode + " · " + (a.notice || ""), $("node"));
      } catch (error) {
        notice(error.message, true);
      } finally {
        b.disabled = false;
      }
    };
  } catch (error) {
    notice(error.message, true);
  }
}
$("search").onsubmit = (e) => {
  e.preventDefault();
  findNode($("gid").value);
};
$("color").onchange = draw;
$("reset-graph").onclick = () => {
  selected = null;
  $("gid").value = "";
  $("node").replaceChildren();
  draw();
};
document.querySelectorAll("[data-export]").forEach(
  (b) =>
    (b.onclick = async () => {
      if (!result) return;
      try {
        const response = await request(
          "/api/export",
          { token: result.token, filename: b.dataset.export },
          true,
        );
        const url = URL.createObjectURL(await response.blob());
        const a = document.createElement("a");
        a.href = url;
        a.download = b.dataset.export;
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (error) {
        notice(error.message, true);
      }
    }),
);
$("chat-form").onsubmit = async (e) => {
  e.preventDefault();
  if (!result) return;
  const snapshot = result;
  const question = $("question").value.trim();
  if (!question) return;
  $("send").disabled = true;
  text("div", question, $("chat"), "message user");
  $("question").value = "";
  try {
    const a = await request("/api/chat", {
      token: result.token,
      question,
      history: chatHistory.slice(-6),
      online: true,
    });
    if (result !== snapshot) return;
    const bubble = text("div", a.text, $("chat"), "message");
    text("p", a.mode + " · " + (a.notice || ""), bubble, "notice");
    const d = text("details", "", bubble);
    text("summary", "Факты и вызванные инструменты", d);
    text("pre", JSON.stringify(a.calls, null, 2), d);
    chatHistory.push(
      { role: "user", content: question },
      { role: "assistant", content: a.text },
    );
  } catch (error) {
    if (result === snapshot) text("div", error.message, $("chat"), "message");
  } finally {
    $("send").disabled = false;
  }
};
async function openContest(recalculate = false) {
  $("restore").disabled = $("recalculate").disabled = true;
  $("progress").hidden = false;
  notice(
    recalculate
      ? "Пересчитываю исходные Parquet-файлы…"
      : "Открываю рассчитанный конкурсный набор…",
  );
  try {
    const next = await request(
      recalculate ? "/api/recalculate" : "/api/default",
      recalculate ? {} : undefined,
    );
    result = next;
    render();
    notice(
      recalculate
        ? "Полный пересчёт завершён. Показаны свежие результаты."
        : "Конкурсный набор: сохранённый результат расчёта. Для живого прогона нажмите «Пересчитать конкурсный набор».",
    );
  } catch (e) {
    notice(e.message, true);
  } finally {
    $("restore").disabled = $("recalculate").disabled = false;
    $("progress").hidden = true;
  }
}
$("restore").onclick = () => openContest();
$("recalculate").onclick = () => openContest(true);
connect();
openContest();

function renderCharts() {
  const counts = Object.fromEntries(Object.keys(roles).map((r) => [r, 0]));
  result.tables.nodes_roles.forEach((n) => {
    if (n.role in counts) counts[n.role]++;
  });
  const total = result.report.n_nodes;
  const parent = $("role-chart");
  parent.replaceChildren();
  const ring = text("div", "", parent, "donut");
  let start = 0;
  const palette = [
    "#24e3db",
    "#349be5",
    "#7b8ef3",
    "#1e769c",
    "#9eeef1",
    "#415773",
  ];
  const stops = Object.entries(counts).map(([role, n], i) => {
    const end = start + (n / Math.max(total, 1)) * 100;
    const part = `${palette[i]} ${start}% ${end}%`;
    start = end;
    return part;
  });
  ring.style.background = `conic-gradient(${stops.join(",")})`;
  const core = text("div", "", ring, "donut-core");
  text("b", total.toLocaleString("ru"), core);
  text("small", "участников", core);
  const legend = text("div", "", parent, "role-list");
  Object.entries(counts).forEach(([role, n], i) => {
    const row = text("div", "", legend);
    const dot = text("i", "", row);
    dot.style.background = palette[i];
    text("span", roles[role], row);
    text("b", n.toLocaleString("ru"), row);
  });
  const cluster = $("cluster-chart");
  cluster.replaceChildren();
  const rows = [...result.tables.clusters]
    .sort((a, b) => b.n_nodes - a.n_nodes)
    .slice(0, 6);
  const max = Math.max(1, ...rows.map((r) => r.n_nodes));
  rows.forEach((r) => {
    const col = text("div", "", cluster, "bar-column");
    text("b", r.n_nodes, col);
    const bar = text("div", "", col, "bar");
    bar.style.height = (r.n_nodes / max) * 135 + 3 + "px";
    text("small", "№ " + r.cluster_id, col);
    col.title = "Кластер " + r.cluster_id + ": " + r.n_nodes + " участников";
  });
}
