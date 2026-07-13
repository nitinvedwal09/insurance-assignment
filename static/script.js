const form = document.getElementById("analyze-form");
const imageInput = document.getElementById("image-input");
const preview = document.getElementById("preview");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const emptyState = document.getElementById("empty-state");

const damageCard = document.getElementById("damage-card");
const damagePill = document.getElementById("damage-pill");
const damageSummary = document.getElementById("damage-summary");

const ocrCard = document.getElementById("ocr-card");
const ocrDetail = document.getElementById("ocr-detail");

const reasoningCard = document.getElementById("reasoning-card");
const reasoningSteps = document.getElementById("reasoning-steps");
const reasoningToggle = document.getElementById("reasoning-toggle");

const answerCard = document.getElementById("answer-card");
const answerText = document.getElementById("answer-text");
const txnIdEl = document.getElementById("txn-id");

const feedbackSection = document.getElementById("feedback-section");
const feedbackUpBtn = document.getElementById("feedback-up");
const feedbackDownBtn = document.getElementById("feedback-down");
const feedbackStatus = document.getElementById("feedback-status");

let currentTransactionId = null;

imageInput.addEventListener("change", () => {
  const file = imageInput.files[0];
  if (!file) {
    preview.hidden = true;
    return;
  }
  preview.src = URL.createObjectURL(file);
  preview.hidden = false;
});

function renderDamage(category) {
  if (!category) return;
  damageCard.hidden = false;
  damagePill.textContent = "";
  damageSummary.textContent = category;
}

function renderOcr(label) {
  if (!label) return;
  ocrCard.hidden = false;
  ocrDetail.innerHTML = "";
  if (label.vin) {
    const li = document.createElement("li");
    li.textContent = `Serial/VIN: ${label.vin}`;
    ocrDetail.appendChild(li);
  }
  if (label.year) {
    const li = document.createElement("li");
    li.textContent = `Year: ${label.year}`;
    ocrDetail.appendChild(li);
  }
}

function renderReasoning(steps) {
  if (!steps || !steps.length) return;
  reasoningCard.hidden = false;
  reasoningSteps.innerHTML = "";

  steps.forEach((step) => {
    const li = document.createElement("li");
    li.className = `reasoning-step step-${step.type}`;

    if (step.type === "thought") {
      li.innerHTML = `<span class="step-label">Thinking</span><p class="step-body">${escapeHtml(step.text)}</p>`;
    } else if (step.type === "tool_call") {
      const args = Object.keys(step.args || {}).length ? JSON.stringify(step.args) : "";
      li.innerHTML = `<span class="step-label">Tool call</span><p class="step-body"><code>${escapeHtml(step.tool)}</code>${args ? ` <code>${escapeHtml(args)}</code>` : ""}</p>`;
    } else if (step.type === "tool_result") {
      li.innerHTML = `<span class="step-label">Result</span><p class="step-body"><code>${escapeHtml(step.tool)}</code> → <code>${escapeHtml(JSON.stringify(step.result))}</code></p>`;
    } else {
      li.innerHTML = `<span class="step-label">${escapeHtml(step.type)}</span><p class="step-body">${escapeHtml(JSON.stringify(step))}</p>`;
    }

    reasoningSteps.appendChild(li);
  });
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

reasoningToggle.addEventListener("click", () => {
  const collapsed = reasoningSteps.hidden;
  reasoningSteps.hidden = !collapsed;
  reasoningToggle.textContent = collapsed ? "Hide" : "Show";
});

function resetResults() {
  emptyState.hidden = true;

  damageCard.hidden = true;
  damagePill.textContent = "";
  damageSummary.textContent = "";

  ocrCard.hidden = true;
  ocrDetail.innerHTML = "";

  reasoningCard.hidden = true;
  reasoningSteps.innerHTML = "";
  reasoningSteps.hidden = false;
  reasoningToggle.textContent = "Hide";

  answerCard.hidden = true;
  answerText.textContent = "";
  txnIdEl.textContent = "";

  currentTransactionId = null;
  feedbackSection.hidden = true;
  feedbackUpBtn.classList.remove("selected");
  feedbackDownBtn.classList.remove("selected");
  feedbackUpBtn.disabled = false;
  feedbackDownBtn.disabled = false;
  feedbackStatus.textContent = "";
}

async function sendFeedback(score) {
  feedbackUpBtn.disabled = true;
  feedbackDownBtn.disabled = true;
  feedbackUpBtn.classList.toggle("selected", score === 1);
  feedbackDownBtn.classList.toggle("selected", score === 0);
  feedbackStatus.textContent = "Sending…";

  try {
    const response = await fetch("/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transaction_id: currentTransactionId, score }),
    });
    if (!response.ok) throw new Error(`Request failed: ${response.status}`);
    feedbackStatus.textContent = "Thanks for your feedback!";
  } catch (err) {
    feedbackStatus.textContent = `Error: ${err.message}`;
    feedbackUpBtn.disabled = false;
    feedbackDownBtn.disabled = false;
  }
}

feedbackUpBtn.addEventListener("click", () => sendFeedback(1));
feedbackDownBtn.addEventListener("click", () => sendFeedback(0));

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const query = document.getElementById("query-input").value.trim();
  const imageFile = imageInput.files[0];
  if (!query && !imageFile) {
    statusEl.textContent = "Ask a question, upload a photo, or both.";
    return;
  }

  const formData = new FormData();
  if (query) {
    formData.append("query", query);
  }
  if (imageFile) {
    formData.append("image", imageFile);
  }

  submitBtn.disabled = true;
  statusEl.textContent = "Analyzing…";
  resetResults();

  try {
    const response = await fetch("/query", { method: "POST", body: formData });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.error || `Request failed: ${response.status}`);
    }

    currentTransactionId = body.transaction_id;
    txnIdEl.textContent = `Ref: ${currentTransactionId}`;

    renderDamage(body.damage_category);
    renderOcr(body.ocr_text);
    renderReasoning(body.agent_steps);

    answerCard.hidden = false;
    answerText.textContent = body.answer;
    feedbackSection.hidden = false;
    statusEl.textContent = "";
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  } finally {
    submitBtn.disabled = false;
  }
});
