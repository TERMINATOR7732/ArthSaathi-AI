/**
 * app.js — ArthSaathi AI frontend behaviour.
 *
 * Responsibilities:
 *   - Tab navigation
 *   - Health check on load (sets LLM status badge)
 *   - Chat form: submit, display messages, show source label and passages
 *   - APR calculator: submit, display results
 *
 * No third-party dependencies. Vanilla ES2020+.
 */

"use strict";

/* =========================================================================
   Constants
   ========================================================================= */

const API = {
  HEALTH: "/api/health",
  CHAT:   "/api/chat",
  APR:    "/api/apr",
};

const MAX_QUERY = 1000;

/* =========================================================================
   Tab navigation
   ========================================================================= */

function initTabs() {
  const buttons = document.querySelectorAll(".tab-btn");
  const panels  = document.querySelectorAll(".panel");

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.panel;

      buttons.forEach((b) => {
        b.classList.toggle("active", b === btn);
        b.setAttribute("aria-selected", b === btn ? "true" : "false");
      });

      panels.forEach((panel) => {
        const active = panel.id === `panel-${target}`;
        panel.classList.toggle("panel-active", active);
        panel.hidden = !active;
      });
    });
  });
}

/* =========================================================================
   Health check — updates the status badge without exposing credentials
   ========================================================================= */

async function checkHealth() {
  const badge = document.getElementById("llm-status-badge");
  if (!badge) return;

  try {
    const res  = await fetch(API.HEALTH);
    const data = await res.json();

    if (data.llm_ready) {
      badge.textContent = "● IBM Granite live";
      badge.className   = "status-badge status-live";
    } else if (data.llm_configured) {
      badge.textContent = "⚠ AI configured but not ready";
      badge.className   = "status-badge status-error";
    } else {
      badge.textContent = "○ Offline knowledge base";
      badge.className   = "status-badge status-offline";
      showOfflineNotice();
    }
  } catch {
    badge.textContent = "⚠ Could not reach server";
    badge.className   = "status-badge status-error";
  }
}

function showOfflineNotice() {
  const notice = document.getElementById("offline-notice");
  if (notice) notice.hidden = false;
}

/* =========================================================================
   Markdown-lite renderer
   Converts the small subset of Markdown the agent produces into safe HTML.
   Does NOT use innerHTML on untrusted user input — only on server responses.
   ========================================================================= */

function renderMarkdown(text) {
  // Escape < and > in text before processing
  let s = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Bold (**text**)
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  // Inline code (`code`)
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Headers (## and ###)
  s = s.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  s = s.replace(/^## (.+)$/gm,  "<h2>$1</h2>");

  // Horizontal rule
  s = s.replace(/^---$/gm, "<hr />");

  // Unordered list items (* item or - item)
  s = s.replace(/^[*\-] (.+)$/gm, "<li>$1</li>");
  s = s.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`);

  // Ordered list items (1. item)
  s = s.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

  // Line breaks → <p> tags
  const paragraphs = s.split(/\n{2,}/);
  s = paragraphs
    .map((p) => {
      p = p.trim();
      if (!p) return "";
      if (/^<(h[23]|ul|ol|hr|li)/.test(p)) return p;
      // Single newlines within a paragraph become <br>
      return `<p>${p.replace(/\n/g, "<br>")}</p>`;
    })
    .filter(Boolean)
    .join("\n");

  return s;
}

/* =========================================================================
   Source label → CSS class mapping
   ========================================================================= */

function sourceClass(source) {
  if (!source) return "source-system";
  if (source.startsWith("provider_error")) return "source-provider_error";
  return `source-${source}`;
}

function sourceLabel(source) {
  if (!source) return "system";
  if (source === "granite") return "IBM Granite";
  if (source === "offline_kb" || source === "not_configured") return "offline KB";
  if (source.startsWith("provider_error")) return "AI error";
  return source;
}

/* =========================================================================
   Chat
   ========================================================================= */

function appendMessage({ role, body, source, fraudAlerts, passages, loading }) {
  const history = document.getElementById("chat-history");
  if (!history) return null;

  const wrapper = document.createElement("div");
  wrapper.className = `message message-${role}${loading ? " message-loading" : ""}`;

  // Meta row
  const meta = document.createElement("div");
  meta.className = "message-meta";

  const roleEl = document.createElement("span");
  roleEl.className = "message-role";
  roleEl.textContent = role === "user" ? "You" : "ArthSaathi";
  meta.appendChild(roleEl);

  if (source) {
    const srcEl = document.createElement("span");
    srcEl.className = `message-source ${sourceClass(source)}`;
    srcEl.textContent = sourceLabel(source);
    meta.appendChild(srcEl);
  }
  wrapper.appendChild(meta);

  // Body
  const bodyEl = document.createElement("div");
  bodyEl.className = "message-body";

  // Fraud alerts (prepended as highlighted boxes)
  if (fraudAlerts && fraudAlerts.length > 0) {
    const alertsDiv = document.createElement("div");
    alertsDiv.className = "fraud-alerts";
    fraudAlerts.forEach((alert) => {
      const a = document.createElement("div");
      a.className = "fraud-alert";
      a.textContent = alert;
      alertsDiv.appendChild(a);
    });
    bodyEl.appendChild(alertsDiv);
  }

  // Main answer content
  const content = document.createElement("div");
  content.className = "message-content";
  if (loading) {
    content.textContent = body;
  } else {
    content.innerHTML = renderMarkdown(body);
  }
  bodyEl.appendChild(content);

  // Knowledge base passages (collapsed by default)
  if (passages && passages.length > 0) {
    const toggleBtn = document.createElement("button");
    toggleBtn.className = "passages-toggle";
    toggleBtn.setAttribute("aria-expanded", "false");
    toggleBtn.textContent = `View ${passages.length} knowledge base passage(s) used`;
    bodyEl.appendChild(toggleBtn);

    const passList = document.createElement("div");
    passList.className = "passages-list";
    passages.forEach((p) => {
      const item = document.createElement("div");
      item.className = "passage-item";
      item.innerHTML = `<span class="passage-id">${escapeHtml(p.id)}</span> — ${escapeHtml(p.text)}`;
      passList.appendChild(item);
    });
    bodyEl.appendChild(passList);

    toggleBtn.addEventListener("click", () => {
      const expanded = passList.classList.toggle("visible");
      toggleBtn.setAttribute("aria-expanded", expanded.toString());
    });
  }

  wrapper.appendChild(bodyEl);
  history.appendChild(wrapper);

  // Scroll into view
  wrapper.scrollIntoView({ behavior: "smooth", block: "end" });
  return wrapper;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function setSubmitting(submitting) {
  const btn     = document.getElementById("chat-submit");
  const label   = btn ? btn.querySelector(".btn-label") : null;
  const spinner = btn ? btn.querySelector(".btn-spinner") : null;
  if (btn)     btn.disabled = submitting;
  if (label)   label.textContent = submitting ? "Sending…" : "Send";
  if (spinner) spinner.hidden = !submitting;
}

function initChat() {
  const form  = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const count = document.getElementById("chat-char-count");

  if (!form || !input) return;

  // Character counter
  input.addEventListener("input", () => {
    const len = input.value.length;
    count.textContent = `${len} / ${MAX_QUERY}`;
    count.style.color = len > MAX_QUERY * 0.9 ? "var(--color-danger)" : "";
  });

  // Ctrl+Enter / Cmd+Enter submits
  input.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = input.value.trim();
    if (!query) return;
    if (query.length > MAX_QUERY) return;

    // Show user message
    appendMessage({ role: "user", body: query, source: null });
    input.value = "";
    count.textContent = `0 / ${MAX_QUERY}`;

    // Show loading indicator
    const loadingMsg = appendMessage({
      role: "assistant",
      body: "Thinking…",
      source: null,
      loading: true,
    });
    setSubmitting(true);

    try {
      const res  = await fetch(API.CHAT, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ query }),
      });
      const data = await res.json();

      // Remove loading message
      if (loadingMsg) loadingMsg.remove();

      if (data.status === "error") {
        appendMessage({
          role:   "assistant",
          body:   `Error: ${data.message || "Unknown error."}`,
          source: "provider_error",
        });
      } else {
        // Update offline notice if not configured
        if (data.status === "not_configured") {
          showOfflineNotice();
        }
        appendMessage({
          role:        "assistant",
          body:        data.answer || "(No response text)",
          source:      data.source || data.status,
          fraudAlerts: data.fraud_alerts || [],
          passages:    data.passages || [],
        });
      }
    } catch (err) {
      if (loadingMsg) loadingMsg.remove();
      appendMessage({
        role:   "assistant",
        body:   "Could not reach the server. Please ensure the application is running.",
        source: "provider_error",
      });
    } finally {
      setSubmitting(false);
      input.focus();
    }
  });
}

/* =========================================================================
   APR Calculator
   ========================================================================= */

function initCalculator() {
  const form   = document.getElementById("apr-form");
  const result = document.getElementById("apr-result");
  if (!form || !result) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const principal = parseFloat(document.getElementById("apr-principal").value);
    const repayment = parseFloat(document.getElementById("apr-repayment").value);
    const days      = parseInt(document.getElementById("apr-days").value, 10);

    // Basic client-side validation before hitting the server
    if (!Number.isFinite(principal) || !Number.isFinite(repayment) || !Number.isFinite(days)) {
      showAprError(result, "Please enter valid numbers in all fields.");
      return;
    }

    try {
      const res  = await fetch(API.APR, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ principal, repayment, days }),
      });
      const data = await res.json();
      renderAprResult(result, data);
    } catch {
      showAprError(result, "Could not reach the server.");
    }
  });
}

function renderAprResult(container, data) {
  container.hidden = false;

  if (data.status === "error") {
    const msgs = (data.errors || [data.message || "Invalid input."]).join(" ");
    showAprError(container, msgs);
    return;
  }

  const pct       = data.annualized_cost_pct;
  const predatory = data.is_predatory;

  container.className = `apr-result ${predatory ? "result-predatory" : "result-ok"}`;
  container.innerHTML = `
    <div class="apr-number">${pct.toLocaleString("en-IN", { maximumFractionDigits: 2 })}%</div>
    <div class="apr-verdict">
      ${predatory
        ? `🚨 Predatory rate — exceeds ${data.threshold_pct}% regulated threshold`
        : `✅ Within typical regulated lending range (below ${data.threshold_pct}%)`
      }
    </div>
    <div class="apr-label">${escapeHtml(data.label)}</div>
  `;
}

function showAprError(container, message) {
  container.hidden = false;
  container.className = "apr-result result-predatory";
  container.innerHTML = `<div class="apr-verdict">⚠ ${escapeHtml(message)}</div>`;
}

/* =========================================================================
   Init
   ========================================================================= */

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  checkHealth();
  initChat();
  initCalculator();
});
