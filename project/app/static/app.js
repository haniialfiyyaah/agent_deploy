const ownerId = "student-01";

const state = {
  threads: [],
  activeThreadId: null,
  mode: "stream",
  controller: null,
  busy: false,
};

const elements = {
  threadList: document.querySelector("#thread-list"),
  threadTitle: document.querySelector("#thread-title"),
  threadMeta: document.querySelector("#thread-meta"),
  transcript: document.querySelector("#transcript"),
  emptyState: document.querySelector("#empty-state"),
  newThread: document.querySelector("#new-thread"),
  emptyNewThread: document.querySelector("#empty-new-thread"),
  deleteThread: document.querySelector("#delete-thread"),
  composer: document.querySelector("#composer"),
  messageInput: document.querySelector("#message-input"),
  sendButton: document.querySelector("#send-button"),
  stopButton: document.querySelector("#stop-button"),
  composerStatus: document.querySelector("#composer-status"),
  modeStream: document.querySelector("#mode-stream"),
  modeComplete: document.querySelector("#mode-complete"),
  runtimeState: document.querySelector("#runtime-state"),
  runtimeLabel: document.querySelector("#runtime-label"),
  runtimeLine: document.querySelector("#runtime-line"),
  providerValue: document.querySelector("#provider-value"),
  modelValue: document.querySelector("#model-value"),
  readinessValue: document.querySelector("#readiness-value"),
  inputTokenValue: document.querySelector("#input-token-value"),
  outputTokenValue: document.querySelector("#output-token-value"),
  includedValue: document.querySelector("#included-value"),
  cursorValue: document.querySelector("#cursor-value"),
  compactionValue: document.querySelector("#compaction-value"),
  modeValue: document.querySelector("#mode-value"),
  ttftValue: document.querySelector("#ttft-value"),
  durationValue: document.querySelector("#duration-value"),
  eventValue: document.querySelector("#event-value"),
  toast: document.querySelector("#toast"),
};

function headers() {
  return {
    "Content-Type": "application/json",
    "X-User-ID": ownerId,
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...headers(), ...(options.headers || {}) },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {
      // Keep the bounded HTTP error when the body is not JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => {
    elements.toast.hidden = true;
  }, 5000);
}

function formatTime(timestamp) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

function setEvent(name) {
  elements.eventValue.textContent = name;
}

function setBusy(isBusy) {
  state.busy = isBusy;
  elements.messageInput.disabled = isBusy || !state.activeThreadId;
  elements.sendButton.disabled = isBusy || !state.activeThreadId;
  elements.deleteThread.disabled = isBusy || !state.activeThreadId;
  elements.modeStream.disabled = isBusy;
  elements.modeComplete.disabled = isBusy;
  elements.stopButton.hidden = !isBusy || state.mode !== "stream";
  elements.composerStatus.textContent = isBusy ? "Generating" : "Idle";
}

function renderThreadList() {
  elements.threadList.replaceChildren();
  if (!state.threads.length) {
    const empty = document.createElement("p");
    empty.className = "rail-empty";
    empty.textContent = "No threads";
    elements.threadList.append(empty);
    return;
  }

  for (const thread of state.threads) {
    const button = document.createElement("button");
    button.className = "thread-item";
    button.type = "button";
    button.setAttribute("role", "listitem");
    if (thread.id === state.activeThreadId) button.classList.add("is-active");

    const title = document.createElement("strong");
    title.textContent = thread.title;
    const meta = document.createElement("span");
    meta.textContent = `${formatTime(thread.updated_at)} · ${thread.summary ? "summarized" : "full context"}`;
    button.append(title, meta);
    button.addEventListener("click", () => selectThread(thread.id));
    elements.threadList.append(button);
  }
}

function createMessageElement(message) {
  const article = document.createElement("article");
  article.className = "message";
  article.dataset.role = message.role;
  article.dataset.status = message.status;
  article.dataset.messageId = message.id;

  const role = document.createElement("div");
  role.className = "message-role";
  role.textContent = message.role === "assistant" ? "Model" : "You";

  const body = document.createElement("div");
  const content = document.createElement("div");
  content.className = "message-content";
  content.textContent = message.content;
  body.append(content);

  if (message.status !== "completed") {
    const status = document.createElement("span");
    status.className = "message-status";
    status.textContent = message.status.replace("_", " ");
    body.append(status);
  }

  article.append(role, body);
  return article;
}

function renderTranscript(messages) {
  elements.transcript.replaceChildren();
  if (!messages.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const text = document.createElement("strong");
    text.textContent = "Thread is empty";
    empty.append(text);
    elements.transcript.append(empty);
    return;
  }
  for (const message of messages) {
    elements.transcript.append(createMessageElement(message));
  }
  elements.transcript.scrollTop = elements.transcript.scrollHeight;
}

function resetDiagnostics() {
  elements.inputTokenValue.textContent = "Pending";
  elements.outputTokenValue.textContent = "Pending";
  elements.includedValue.textContent = "Pending";
  elements.cursorValue.textContent = "Pending";
  elements.compactionValue.textContent = "None";
  elements.ttftValue.textContent = "Pending";
  elements.durationValue.textContent = "Pending";
  setEvent("standby");
}

function applyContext(context) {
  if (!context) return;
  elements.inputTokenValue.textContent = `${context.estimated_input_tokens} est.`;
  elements.includedValue.textContent = String(context.included_message_count);
  elements.cursorValue.textContent = String(context.summarized_through_position);
  elements.compactionValue.textContent = context.compacted ? "Triggered" : "None";
}

function applyUsage(usage) {
  if (!usage) return;
  elements.outputTokenValue.textContent = String(usage.output_tokens ?? "Pending");
  elements.durationValue.textContent = usage.duration_ms
    ? `${Math.round(usage.duration_ms)} ms`
    : "Pending";
  elements.ttftValue.textContent = usage.time_to_first_token_ms
    ? `${Math.round(usage.time_to_first_token_ms)} ms`
    : "Pending";
}

async function loadRuntime() {
  try {
    const response = await fetch("/health/ready");
    const payload = await response.json();
    elements.providerValue.textContent = payload.provider;
    elements.modelValue.textContent = payload.model;
    elements.readinessValue.textContent = payload.ready ? "Ready" : "Unavailable";
    elements.runtimeLine.textContent = `${payload.provider} · ${payload.model}`;
    elements.runtimeLabel.textContent = payload.ready ? "Ready" : "Unavailable";
    elements.runtimeState.dataset.state = payload.ready ? "ready" : "error";
  } catch {
    elements.readinessValue.textContent = "Unavailable";
    elements.runtimeLabel.textContent = "Disconnected";
    elements.runtimeState.dataset.state = "error";
  }
}

async function loadThreads(selectFirst = true) {
  state.threads = await api("/v1/threads");
  renderThreadList();
  if (selectFirst && !state.activeThreadId && state.threads.length) {
    await selectThread(state.threads[0].id);
  }
}

async function createThread() {
  try {
    const sequence = state.threads.length + 1;
    const thread = await api("/v1/threads", {
      method: "POST",
      body: JSON.stringify({ title: `Conversation ${sequence}` }),
    });
    state.activeThreadId = thread.id;
    await loadThreads(false);
    await selectThread(thread.id);
    elements.messageInput.focus();
  } catch (error) {
    showToast(`Thread creation failed: ${error.message}`);
  }
}

async function selectThread(threadId) {
  if (state.busy) return;
  try {
    const thread = await api(`/v1/threads/${threadId}`);
    state.activeThreadId = threadId;
    elements.threadTitle.textContent = thread.title;
    elements.threadMeta.textContent = `${thread.messages.length} messages · ${thread.id.slice(0, 8)}`;
    elements.deleteThread.disabled = false;
    elements.messageInput.disabled = false;
    elements.sendButton.disabled = false;
    renderTranscript(thread.messages);
    renderThreadList();
    elements.cursorValue.textContent = String(thread.summarized_through_position);
    elements.compactionValue.textContent = thread.summary ? "Stored" : "None";
  } catch (error) {
    showToast(`Thread loading failed: ${error.message}`);
  }
}

async function deleteThread() {
  if (!state.activeThreadId || state.busy) return;
  const confirmed = window.confirm("Delete this thread and all of its messages?");
  if (!confirmed) return;
  try {
    await api(`/v1/threads/${state.activeThreadId}`, { method: "DELETE" });
    state.activeThreadId = null;
    elements.threadTitle.textContent = "No thread selected";
    elements.threadMeta.textContent = "Create a thread to begin.";
    elements.deleteThread.disabled = true;
    elements.messageInput.disabled = true;
    elements.sendButton.disabled = true;
    renderTranscript([]);
    resetDiagnostics();
    await loadThreads(true);
  } catch (error) {
    showToast(`Thread deletion failed: ${error.message}`);
  }
}

function setMode(mode) {
  if (state.busy) return;
  state.mode = mode;
  const streaming = mode === "stream";
  elements.modeStream.classList.toggle("is-active", streaming);
  elements.modeComplete.classList.toggle("is-active", !streaming);
  elements.modeStream.setAttribute("aria-pressed", String(streaming));
  elements.modeComplete.setAttribute("aria-pressed", String(!streaming));
  elements.modeValue.textContent = streaming ? "Stream" : "Complete";
  elements.ttftValue.textContent = "Pending";
}

function appendOptimisticMessage(role, content, status = "completed") {
  if (elements.transcript.querySelector(".empty-state")) {
    elements.transcript.replaceChildren();
  }
  const message = {
    id: `local-${crypto.randomUUID()}`,
    role,
    content,
    status,
  };
  const node = createMessageElement(message);
  if (status === "in_progress") node.classList.add("is-streaming");
  elements.transcript.append(node);
  elements.transcript.scrollTop = elements.transcript.scrollHeight;
  return node;
}

function parseSseBlock(block) {
  let event = "message";
  const data = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  return { event, data: data.length ? JSON.parse(data.join("\n")) : {} };
}

async function sendStream(content) {
  state.controller = new AbortController();
  const assistantNode = appendOptimisticMessage("assistant", "", "in_progress");
  const output = assistantNode.querySelector(".message-content");
  const started = performance.now();
  let firstDelta = null;

  const response = await fetch(
    `/v1/threads/${state.activeThreadId}/messages/stream`,
    {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ content }),
      signal: state.controller.signal,
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `${response.status} ${response.statusText}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      if (!block.trim()) continue;
      const event = parseSseBlock(block);
      setEvent(event.event);
      if (event.event === "message.start") {
        applyContext(event.data.context);
      } else if (event.event === "message.delta") {
        if (firstDelta === null) {
          firstDelta = performance.now();
          elements.ttftValue.textContent = `${Math.round(firstDelta - started)} ms`;
        }
        output.textContent += event.data.delta;
        elements.transcript.scrollTop = elements.transcript.scrollHeight;
      } else if (event.event === "context.compacted") {
        applyContext(event.data);
      } else if (event.event === "usage") {
        applyUsage(event.data);
      } else if (event.event === "error") {
        assistantNode.dataset.status = "error";
        showToast(event.data.message || "Provider stream failed.");
      } else if (event.event === "message.completed") {
        assistantNode.dataset.status = "completed";
      }
    }
    if (done) break;
  }
  assistantNode.classList.remove("is-streaming");
}

async function sendComplete(content) {
  const response = await api(`/v1/threads/${state.activeThreadId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
  appendOptimisticMessage("assistant", response.assistant_message.content);
  applyContext(response.context);
  applyUsage(response.usage);
  setEvent("message.completed");
}

async function submitMessage(event) {
  event.preventDefault();
  const content = elements.messageInput.value.trim();
  if (!content || !state.activeThreadId || state.busy) return;

  elements.messageInput.value = "";
  appendOptimisticMessage("user", content);
  resetDiagnostics();
  elements.modeValue.textContent = state.mode === "stream" ? "Stream" : "Complete";
  setBusy(true);
  try {
    if (state.mode === "stream") {
      await sendStream(content);
    } else {
      await sendComplete(content);
    }
  } catch (error) {
    if (error.name === "AbortError") {
      setEvent("cancelled");
      elements.composerStatus.textContent = "Cancelled";
    } else {
      setEvent("error");
      showToast(`Request failed: ${error.message}`);
    }
  } finally {
    state.controller = null;
    setBusy(false);
    await loadThreads(false).catch(() => {});
    await selectThread(state.activeThreadId).catch(() => {});
    elements.messageInput.focus();
  }
}

elements.newThread.addEventListener("click", createThread);
elements.emptyNewThread.addEventListener("click", createThread);
elements.deleteThread.addEventListener("click", deleteThread);
elements.modeStream.addEventListener("click", () => setMode("stream"));
elements.modeComplete.addEventListener("click", () => setMode("complete"));
elements.stopButton.addEventListener("click", () => state.controller?.abort());
elements.composer.addEventListener("submit", submitMessage);
elements.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.composer.requestSubmit();
  }
});

Promise.all([loadRuntime(), loadThreads(true)]).catch((error) => {
  showToast(`Gateway initialization failed: ${error.message}`);
});
