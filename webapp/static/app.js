const settlementSelect = document.getElementById("settlementSelect");
const orderInput = document.getElementById("orderInput");
const suggestionsEl = document.getElementById("orderSuggestions");
const calcBtn = document.getElementById("calcBtn");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const lineItemsBody = document.getElementById("lineItemsBody");
const listedTotalEl = document.getElementById("listedTotal");
const calculatedTotalEl = document.getElementById("calculatedTotal");

let autocompleteTimer = null;
let autocompleteItems = [];
let autocompleteIndex = -1;

function hideSuggestions() {
  autocompleteItems = [];
  autocompleteIndex = -1;
  suggestionsEl.innerHTML = "";
  suggestionsEl.classList.add("hidden");
}

function getActiveOrderSegment(rawText) {
  const text = String(rawText || "");
  const lastComma = text.lastIndexOf(",");
  const start = lastComma >= 0 ? lastComma + 1 : 0;
  const before = text.slice(0, start);
  const segment = text.slice(start);

  const qtyMatch = segment.match(/^(\s*\d+(?:\.\d+)?\s+)(.*)$/);
  const qtyPrefix = qtyMatch ? qtyMatch[1] : "";
  const query = (qtyMatch ? qtyMatch[2] : segment).trim().toLowerCase();

  return { before, segment, qtyPrefix, query };
}

function renderSuggestions(items) {
  autocompleteItems = items || [];
  autocompleteIndex = autocompleteItems.length ? 0 : -1;

  if (!autocompleteItems.length) {
    hideSuggestions();
    return;
  }

  suggestionsEl.innerHTML = autocompleteItems
    .map((item, idx) => `<button type="button" class="ac-item ${idx === autocompleteIndex ? "active" : ""}" data-index="${idx}">${item}</button>`)
    .join("");

  suggestionsEl.classList.remove("hidden");

  for (const btn of suggestionsEl.querySelectorAll(".ac-item")) {
    btn.addEventListener("mousedown", (e) => {
      e.preventDefault();
      const i = Number(btn.dataset.index);
      if (!Number.isNaN(i)) applySuggestionByIndex(i);
    });
  }
}

function updateSuggestionActiveState() {
  const nodes = suggestionsEl.querySelectorAll(".ac-item");
  nodes.forEach((n, i) => n.classList.toggle("active", i === autocompleteIndex));
}

function applySuggestionByIndex(index) {
  if (index < 0 || index >= autocompleteItems.length) return;
  const picked = autocompleteItems[index];
  const { before, qtyPrefix } = getActiveOrderSegment(orderInput.value);
  const insertion = `${qtyPrefix}${picked}`.trim();
  const next = `${before}${before && !before.endsWith(" ") ? " " : ""}${insertion}`;
  orderInput.value = next;
  hideSuggestions();
  orderInput.focus();
}

async function fetchSuggestions() {
  const { query } = getActiveOrderSegment(orderInput.value);
  if (query.length < 2) {
    hideSuggestions();
    return;
  }

  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    if (!res.ok) {
      hideSuggestions();
      return;
    }
    const data = await res.json();
    renderSuggestions((data.results || []).slice(0, 10));
  } catch {
    hideSuggestions();
  }
}

function humanizeSettlement(value) {
  if (!value) return "";
  return String(value)
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function fmt(value) {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return "—";
  return n.toFixed(2);
}

function setStatus(msg, type = "info") {
  statusEl.textContent = msg || "";
  statusEl.className = `status ${type}`;
}

function clearResults() {
  lineItemsBody.innerHTML = "";
  listedTotalEl.textContent = "";
  calculatedTotalEl.textContent = "";
  resultsEl.classList.add("hidden");
}

function ingredientHtml(item) {
  if (!item.ingredients || !item.ingredients.length) return "<em>No ingredient breakdown</em>";
  const rows = item.ingredients
    .map(
      (ing) => `
      <tr>
        <td>${ing.code || ""}</td>
        <td>${fmt(ing.qty)}</td>
        <td>${fmt(ing.unit)}</td>
        <td>${fmt(ing.subtotal)}</td>
        <td>${ing.tool ? "Tool (not consumed)" : "Used up"}</td>
      </tr>
    `
    )
    .join("");

  return `
    <table class="ing-table">
      <thead>
        <tr>
          <th>Ingredient</th>
          <th>Qty</th>
          <th>Cost Each</th>
          <th>Subtotal</th>
          <th>Type</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderResults(payload) {
  lineItemsBody.innerHTML = "";

  for (const item of payload.line_items || []) {
    const tr = document.createElement("tr");
    const itemName = item.resolved_code || item.input;
    const err = item.error ? `<div class="error">${item.error}</div>` : "";
    const hasBreakdown = !!(item.ingredients && item.ingredients.length);
    const isLrLeaf = !hasBreakdown && item.unit_listed != null && item.unit_calculated != null && Number(item.unit_listed) === Number(item.unit_calculated);
    const actionCell = hasBreakdown
      ? `<button class="toggle-btn">Show Recipe</button>`
      : isLrLeaf
        ? `<span class="badge">Market Price ✓</span>`
        : "—";
    tr.innerHTML = `
      <td>${itemName}${err}</td>
      <td>${fmt(item.qty)}</td>
      <td>${fmt(item.unit_listed)}</td>
      <td>${fmt(item.unit_calculated)}</td>
      <td>${fmt(item.line_listed)}</td>
      <td>${fmt(item.line_calculated)}</td>
      <td>${actionCell}</td>
    `;

    const detail = document.createElement("tr");
    detail.className = "hidden detail-row";
    detail.innerHTML = `<td colspan="7">${ingredientHtml(item)}</td>`;

    const btn = tr.querySelector(".toggle-btn");
    if (btn) {
      btn.addEventListener("click", () => {
        detail.classList.toggle("hidden");
        btn.textContent = detail.classList.contains("hidden") ? "Show Recipe" : "Hide Recipe";
      });
    }

    lineItemsBody.appendChild(tr);
    if (hasBreakdown) {
      lineItemsBody.appendChild(detail);
    }
  }

  listedTotalEl.textContent = fmt(payload?.totals?.listed_total);
  calculatedTotalEl.textContent = fmt(payload?.totals?.calculated_total);
  resultsEl.classList.remove("hidden");
}

async function loadSettlements() {
  const res = await fetch("/api/settlements");
  const data = await res.json();
  settlementSelect.innerHTML = "";
  for (const s of data.settlements || []) {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = humanizeSettlement(s);
    settlementSelect.appendChild(opt);
  }
}

async function calculate() {
  const order = orderInput.value.trim();
  const settlement = settlementSelect.value;
  if (!order) {
    setStatus("Please enter an order.", "error");
    clearResults();
    return;
  }

  setStatus("Calculating...", "info");
  calcBtn.disabled = true;

  try {
    const res = await fetch("/api/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order, settlement }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "Calculation failed");
    }
    renderResults(data);
    setStatus("Done.", "success");
  } catch (err) {
    clearResults();
    setStatus(err.message || "Error", "error");
  } finally {
    calcBtn.disabled = false;
  }
}

calcBtn.addEventListener("click", calculate);

orderInput.addEventListener("input", () => {
  if (autocompleteTimer) {
    clearTimeout(autocompleteTimer);
  }
  autocompleteTimer = setTimeout(fetchSuggestions, 250);
});

orderInput.addEventListener("keydown", (e) => {
  if (suggestionsEl.classList.contains("hidden") || !autocompleteItems.length) return;

  if (e.key === "ArrowDown") {
    e.preventDefault();
    autocompleteIndex = (autocompleteIndex + 1) % autocompleteItems.length;
    updateSuggestionActiveState();
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    autocompleteIndex = (autocompleteIndex - 1 + autocompleteItems.length) % autocompleteItems.length;
    updateSuggestionActiveState();
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (autocompleteIndex >= 0) {
      applySuggestionByIndex(autocompleteIndex);
    }
  } else if (e.key === "Escape") {
    hideSuggestions();
  }
});

document.addEventListener("click", (e) => {
  if (e.target === orderInput || suggestionsEl.contains(e.target)) return;
  hideSuggestions();
});

loadSettlements().catch((e) => setStatus(e.message, "error"));
