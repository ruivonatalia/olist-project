function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Markdown bem mínimo: só **negrito**, suficiente pro que o agente escreve.
function formatAnswer(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

// ---------- gráfico (Plotly) ----------
// A figura já chega pronta do backend (rag/agent.py monta data+layout a
// partir do resultado real do SQL -- ver skill de dataviz: cor da série
// vem da paleta categórica validada, sempre o mesmo slot/série única).
let plotCounter = 0;

function chartCardHtml() {
  const id = `chart-${++plotCounter}`;
  return { id, html: `<div class="chart-card"><div class="chart-box" id="${id}"></div></div>` };
}

function renderChart(elId, chart) {
  const el = document.getElementById(elId);
  if (!el) return;
  Plotly.newPlot(el, chart.data, chart.layout, {
    responsive: true,
    displayModeBar: false,
  });
}

// ---------- tabela + CSV ----------
function csvEscape(value) {
  const s = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function toCsv(table) {
  const header = table.columns.map(csvEscape).join(",");
  const lines = table.rows.map((row) => table.columns.map((c) => csvEscape(row[c])).join(","));
  return [header, ...lines].join("\n");
}

function downloadCsv(table) {
  const blob = new Blob([toCsv(table)], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "olist-resultado.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

let tableCounter = 0;

function tableCardHtml(table) {
  const id = `table-${++tableCounter}`;
  const head = table.columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("");
  const body = table.rows
    .map((row) => `<tr>${table.columns.map((c) => `<td>${escapeHtml(row[c])}</td>`).join("")}</tr>`)
    .join("");
  return `
    <div class="table-card">
      <div class="table-card-head">
        <span>${table.rows.length} linha${table.rows.length === 1 ? "" : "s"} · ${table.columns.length} coluna${table.columns.length === 1 ? "" : "s"}</span>
        <button class="csv-btn" id="${id}-csv" type="button">⬇ CSV</button>
      </div>
      <div class="table-scroll">
        <table class="data-table">
          <thead><tr>${head}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
      ${table.truncated ? '<div class="table-truncated">Mostrando o limite de linhas retornadas pela consulta.</div>' : ""}
    </div>`;
}

function wireTableDownload(bubble, table) {
  const btn = bubble.querySelector(".csv-btn");
  if (btn) btn.addEventListener("click", () => downloadCsv(table));
}

// ---------- chat ----------
const chatScroll = document.getElementById("chat-scroll");
const emptyState = document.getElementById("empty-state");
const chatHistory = document.getElementById("chat-history");
const chatForm = document.getElementById("form-ask");
const input = document.getElementById("ask-question");
const submitBtn = document.getElementById("ask-submit");
const clearBtn = document.getElementById("clear-btn");

function scrollToBottom() {
  chatScroll.scrollTop = chatScroll.scrollHeight;
}

function addUserMessage(question) {
  const msg = document.createElement("div");
  msg.className = "msg user";
  msg.innerHTML = `<div class="msg-avatar">EU</div><div class="bubble">${escapeHtml(question)}</div>`;
  chatHistory.appendChild(msg);
  scrollToBottom();
}

function addTypingMessage() {
  const msg = document.createElement("div");
  msg.className = "msg assistant";
  msg.innerHTML = `<div class="msg-avatar">AI</div><div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div>`;
  chatHistory.appendChild(msg);
  scrollToBottom();
  return msg;
}

function fillAssistantMessage(msgEl, data) {
  const bubble = msgEl.querySelector(".bubble");
  const chartInfo = data.chart ? chartCardHtml() : null;
  const tableHtml = data.table ? tableCardHtml(data.table) : "";
  const toolsId = `tools-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const toolsHtml = data.tool_calls && data.tool_calls.length
    ? `
      <div class="tools-toggle" data-target="${toolsId}">⚙ ferramentas usadas (${data.tool_calls.length})</div>
      <div class="tools-list" id="${toolsId}" hidden>
        ${data.tool_calls.map((t) => `<code>${escapeHtml(t.tool)}</code>`).join("")}
      </div>`
    : "";
  bubble.innerHTML = `
    <div class="answer-text">${formatAnswer(data.answer)}</div>
    ${chartInfo ? chartInfo.html : ""}
    ${tableHtml}
    ${toolsHtml}
  `;
  if (chartInfo) renderChart(chartInfo.id, data.chart);
  if (data.table) wireTableDownload(bubble, data.table);
  const toggle = bubble.querySelector(".tools-toggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      const list = document.getElementById(toolsId);
      list.hidden = !list.hidden;
    });
  }
  scrollToBottom();
}

function fillErrorMessage(msgEl, message) {
  msgEl.querySelector(".bubble").innerHTML = `<div class="error-text">${escapeHtml(message)}</div>`;
}

async function submitQuestion(question) {
  if (!question) return;
  if (emptyState) emptyState.hidden = true;

  addUserMessage(question);
  const typingMsg = addTypingMessage();

  submitBtn.disabled = true;
  try {
    const resp = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Erro na requisição");
    fillAssistantMessage(typingMsg, data);
  } catch (err) {
    fillErrorMessage(typingMsg, err.message);
  } finally {
    submitBtn.disabled = false;
  }
}

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const question = input.value.trim();
  input.value = "";
  submitQuestion(question);
});

document.querySelectorAll(".example").forEach((btn) => {
  btn.addEventListener("click", () => submitQuestion(btn.textContent));
});

clearBtn.addEventListener("click", () => {
  chatHistory.innerHTML = "";
  if (emptyState) emptyState.hidden = false;
});
