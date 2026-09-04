const API_BASE = window.location.origin; // same-origin: FastAPI serves this file too

const form = document.getElementById("queryForm");
const input = document.getElementById("questionInput");
const submitBtn = document.getElementById("submitBtn");
const log = document.getElementById("log");
const logEmpty = document.getElementById("logEmpty");
const report = document.getElementById("report");
const symbolSelect = document.getElementById("symbolSelect");

let currentSymbol = "BTCUSDT";

symbolSelect.addEventListener("click", (e) => {
  const btn = e.target.closest(".symbol-btn");
  if (!btn) return;
  currentSymbol = btn.dataset.symbol;
  [...symbolSelect.children].forEach((b) => b.classList.toggle("is-active", b === btn));
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  await runInvestigation(question, currentSymbol);
});

async function runInvestigation(question, symbol) {
  submitBtn.disabled = true;
  submitBtn.textContent = "Investigating...";
  report.hidden = true;
  logEmpty.remove();
  log.innerHTML = "";

  try {
    const res = await fetch(`${API_BASE}/api/investigate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, symbol }),
    });

    if (!res.ok || !res.body) {
      renderError(`Request failed (${res.status}). Is the backend running?`);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop(); // keep the last (possibly incomplete) chunk in the buffer

      for (const chunk of chunks) {
        const dataLine = chunk.split("\n").find((l) => l.startsWith("data:"));
        if (!dataLine) continue;
        const jsonStr = dataLine.slice(5).trim();
        if (!jsonStr || jsonStr === "{}") continue;

        const step = JSON.parse(jsonStr);
        handleStep(step);
      }
    }
  } catch (err) {
    renderError(`Connection error: ${err.message}. Is the backend running on this origin?`);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Investigate";
    if (activeEntryEl) activeEntryEl.classList.remove("is-active");
  }
}

let activeEntryEl = null;

function handleStep(step) {
  if (activeEntryEl) activeEntryEl.classList.remove("is-active");

  if (step.type === "thought") {
    const entry = document.createElement("div");
    entry.className = "log-entry is-active";
    entry.innerHTML = `
      <div class="log-entry__dot"></div>
      <div class="log-entry__step">step ${step.step}</div>
      <div class="log-entry__thought">${escapeHtml(step.thought)}</div>
      ${step.tool_called ? `<div class="log-entry__tool">→ ${step.tool_called}</div>` : ""}
    `;
    log.appendChild(entry);
    activeEntryEl = entry;
  }

  if (step.type === "observation") {
    const dataEl = document.createElement("div");
    dataEl.className = "log-entry__data";
    dataEl.textContent = JSON.stringify(step.result, null, 2);
    if (activeEntryEl) activeEntryEl.appendChild(dataEl);
  }

  if (step.type === "error") {
    renderError(step.message);
  }

  if (step.type === "report") {
    renderReport(step.report);
  }
}

function renderReport(r) {
  report.hidden = false;
  document.getElementById("reportBadge").textContent = r.verdict.toUpperCase();
  document.getElementById("reportBadge").className = `report__badge ${r.verdict}`;
  document.getElementById("reportConfidence").textContent = `${r.confidence}% confidence`;
  document.getElementById("reportSummary").textContent = r.summary;
  document.getElementById("reportRisk").textContent = `Risk: ${r.risk_note}`;

  const evidenceEl = document.getElementById("reportEvidence");
  evidenceEl.innerHTML = "";
  (r.evidence_points || []).forEach((point) => {
    const div = document.createElement("div");
    div.className = "report__evidence-item";
    div.textContent = point;
    evidenceEl.appendChild(div);
  });

  report.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderError(message) {
  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.innerHTML = `
    <div class="log-entry__dot"></div>
    <div class="log-entry__thought" style="color: var(--bearish)">${escapeHtml(message)}</div>
  `;
  log.appendChild(entry);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
