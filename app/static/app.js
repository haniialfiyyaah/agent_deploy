const form = document.querySelector("#run-form");
const customer = document.querySelector("#customer");
const category = document.querySelector("#category");
const message = document.querySelector("#message");
const allowTicket = document.querySelector("#allow-ticket");
const runButton = document.querySelector("#run-button");
const cancelButton = document.querySelector("#cancel-button");
const runState = document.querySelector("#run-state");
const runIdView = document.querySelector("#run-id");
const answer = document.querySelector("#answer");
const timeline = document.querySelector("#timeline");
const health = document.querySelector("#health");
const modelView = document.querySelector("#model");
const versionView = document.querySelector("#version");
const latencyView = document.querySelector("#latency");
const tokensView = document.querySelector("#tokens");
const costView = document.querySelector("#cost");
const toast = document.querySelector("#toast");

let activeRunId = null;
let eventSource = null;

function notify(text) {
  toast.textContent = text;
  toast.hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => { toast.hidden = true; }, 6000);
}

function setState(state) {
  runState.textContent = state.toUpperCase();
  runState.dataset.state = state;
  const busy = ["queued", "running"].includes(state);
  runButton.disabled = busy;
  cancelButton.disabled = !busy;
}

function addEvent(item) {
  if (timeline.querySelector(".timeline-empty")) timeline.replaceChildren();
  const li = document.createElement("li");
  li.dataset.kind = item.event;
  const title = document.createElement("strong");
  title.textContent = `${String(item.id).padStart(2, "0")} · ${item.event}`;
  const body = document.createElement("pre");
  body.textContent = JSON.stringify(item.data, null, 2);
  li.append(title, body);
  timeline.append(li);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
    } catch {}
    throw new Error(detail);
  }
  return response.json();
}

async function loadHealth() {
  try {
    const payload = await api("/health/ready");
    health.textContent = `${payload.status} · ${payload.model}`;
    health.dataset.state = "ready";
    modelView.textContent = payload.model;
    versionView.textContent = payload.version;
  } catch (error) {
    health.textContent = "Not ready";
    health.dataset.state = "error";
    notify(`Readiness check failed: ${error.message}`);
  }
}

async function loadResult() {
  if (!activeRunId) return;
  const snapshot = await api(`/v1/runs/${activeRunId}`);
  setState(snapshot.status);
  if (!snapshot.result) return;
  const result = snapshot.result;
  answer.classList.remove("empty");
  answer.textContent = result.output;
  latencyView.textContent = `${Math.round(result.latency_ms)} ms`;
  tokensView.textContent = `${result.input_tokens} in / ${result.output_tokens} out`;
  costView.textContent = `$${Number(result.estimated_cost_usd).toFixed(6)}`;
}

function connectEvents(url) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(url);
  const names = [
    "run.queued", "run.started", "model.started", "model.completed",
    "tool.started", "tool.completed", "run.cancellation_requested",
    "run.completed", "run.failed", "run.cancelled",
  ];
  for (const name of names) {
    eventSource.addEventListener(name, async (event) => {
      const item = JSON.parse(event.data);
      addEvent(item);
      if (["run.completed", "run.failed", "run.cancelled"].includes(name)) {
        eventSource.close();
        await loadResult();
      } else if (name === "run.started") {
        setState("running");
      }
    });
  }
  eventSource.onerror = () => {
    if (!["completed", "failed", "cancelled"].includes(runState.dataset.state)) {
      notify("Event stream disconnected; the status endpoint is still available.");
    }
  };
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  timeline.innerHTML = '<li class="timeline-empty">Waiting for the run to start.</li>';
  answer.className = "answer empty";
  answer.textContent = "The live model and tools are working…";
  setState("queued");
  const customerId = customer.value || null;
  const authenticated = customerId !== null && customerId !== "CUST-300";
  try {
    const accepted = await api("/v1/runs", {
      method: "POST",
      body: JSON.stringify({
        message: message.value.trim(),
        customer_id: customerId,
        authenticated,
        category: category.value,
        allow_ticket_creation: allowTicket.checked,
      }),
    });
    activeRunId = accepted.run_id;
    runIdView.textContent = activeRunId;
    const finished = ["completed", "failed", "cancelled"].includes(accepted.status);
    if (finished && accepted.snapshot) {
      if (accepted.events) {
        timeline.replaceChildren();
        for (const item of accepted.events) addEvent(item);
      }
      setState(accepted.snapshot.status);
      if (accepted.snapshot.result) {
        const result = accepted.snapshot.result;
        answer.classList.remove("empty");
        answer.textContent = result.output;
        latencyView.textContent = `${Math.round(result.latency_ms)} ms`;
        tokensView.textContent = `${result.input_tokens} in / ${result.output_tokens} out`;
        costView.textContent = `$${Number(result.estimated_cost_usd).toFixed(6)}`;
      }
    } else {
      connectEvents(accepted.events_url);
    }
  } catch (error) {
    setState("failed");
    notify(`Run submission failed: ${error.message}`);
  }
});

cancelButton.addEventListener("click", async () => {
  if (!activeRunId) return;
  try {
    const response = await api(`/v1/runs/${activeRunId}/cancel`, { method: "POST" });
    if (!response.accepted) notify(`Run is already ${response.status}.`);
  } catch (error) {
    notify(`Cancellation failed: ${error.message}`);
  }
});

loadHealth();
