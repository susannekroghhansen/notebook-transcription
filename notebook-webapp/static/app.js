/* ── State ─────────────────────────────────────────────────────────────────── */

const state = {
  // Tab 1
  selectedFile:      null,
  currentJobId:      null,
  eventSource:       null,
  // Shared context
  lastContent:       null,   // combined .md text from last processed job
  lastContentName:   null,
  // Tab 2
  chatContext:       null,
  chatHistory:       [],
  // Tab 3
  writeContext:      null,
  lastGeneratedText: '',
};

/* ── Tab switching ─────────────────────────────────────────────────────────── */

function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach((btn, i) => {
    const names = ['process', 'chat', 'write'];
    btn.classList.toggle('active', names[i] === name);
  });
  document.querySelectorAll('.tab').forEach(el => {
    const id = el.id.replace('tab-', '');
    el.hidden = id !== name;
  });
  if (name === 'chat')  refreshFileList('chat');
  if (name === 'write') refreshFileList('write');
}

/* ── Tab 1: Process ────────────────────────────────────────────────────────── */

function handleDrop(e) {
  e.preventDefault();
  document.getElementById('upload-area').classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file && file.name.endsWith('.pdf')) handleFileSelect(file);
}

function handleFileSelect(file) {
  if (!file) return;
  state.selectedFile = file;
  document.getElementById('upload-idle').hidden = true;
  document.getElementById('upload-ready').hidden = false;
  document.getElementById('selected-filename').textContent = file.name;
  document.getElementById('process-btn').disabled = false;
}

function clearPDF() {
  state.selectedFile = null;
  document.getElementById('upload-idle').hidden = false;
  document.getElementById('upload-ready').hidden = true;
  document.getElementById('pdf-input').value = '';
  document.getElementById('process-btn').disabled = true;
}

async function startProcessing() {
  if (!state.selectedFile) return;

  const btn = document.getElementById('process-btn');
  btn.disabled = true;
  btn.textContent = 'Uploading…';

  const form = new FormData();
  form.append('file',     state.selectedFile);
  form.append('notebook', document.getElementById('nb-id').value    || 'NB');
  form.append('date',     document.getElementById('nb-date').value  || 'UnknownDate');
  form.append('topic',    document.getElementById('nb-topic').value || 'notebook');

  try {
    const res = await fetch('/api/process/upload', { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const { job_id } = await res.json();
    state.currentJobId = job_id;

    showProgressCard();
    btn.textContent = 'Processing…';
    connectSSE(job_id);
  } catch (err) {
    btn.disabled = false;
    btn.textContent = 'Start Processing';
    showErrorBanner(err.message);
  }
}

function showProgressCard() {
  const card = document.getElementById('progress-card');
  card.hidden = false;
  document.getElementById('done-section').hidden   = true;
  document.getElementById('error-banner').hidden   = true;
  document.getElementById('pages-list').innerHTML  = '';
  document.getElementById('status-msg').textContent = '';
  card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ── SSE ───────────────────────────────────────────────────────────────────── */

function connectSSE(jobId) {
  if (state.eventSource) state.eventSource.close();

  const es = new EventSource(`/api/process/stream/${jobId}`);
  state.eventSource = es;

  es.onmessage = (e) => {
    const event = JSON.parse(e.data);
    handleSSEEvent(event);
  };

  es.onerror = () => {
    // EventSource auto-reconnects; only close if job is terminal
    if (state.currentJobId) {
      // Will reconnect; snapshot event will bring us back up to date
    }
  };
}

function handleSSEEvent(event) {
  switch (event.type) {

    case 'snapshot': {
      const job = event.job;
      if (job.pages && job.pages.length > 0) renderPageList(job.pages);
      if (job.status === 'done') {
        fetchAndStoreCombined(job.id || state.currentJobId).then(() => showDoneSection());
        if (state.eventSource) state.eventSource.close();
      } else if (job.status === 'error') {
        showErrorBanner(job.error || 'Unknown error');
        if (state.eventSource) state.eventSource.close();
      }
      break;
    }

    case 'status':
      document.getElementById('status-msg').textContent = event.message || '';
      break;

    case 'pages_init':
      renderPageList(event.pages);
      break;

    case 'page_update':
      updatePageItem(event.index, event.status, event.error);
      break;

    case 'done':
      fetchAndStoreCombined(state.currentJobId).then(() => {
        showDoneSection();
        document.getElementById('process-btn').textContent = 'Start Processing';
        if (state.eventSource) state.eventSource.close();
      });
      break;

    case 'error':
      showErrorBanner(event.message || 'Processing failed');
      document.getElementById('process-btn').disabled = false;
      document.getElementById('process-btn').textContent = 'Start Processing';
      if (state.eventSource) state.eventSource.close();
      break;

    case 'heartbeat':
      break; // keep-alive, do nothing
  }
}

function renderPageList(pages) {
  const list = document.getElementById('pages-list');
  list.innerHTML = '';
  pages.forEach(p => {
    const li = document.createElement('li');
    li.id = `page-${p.index}`;
    li.className = `page-item status-${p.status}`;
    li.innerHTML = pageItemHTML(p.index, p.filename, p.status);
    list.appendChild(li);
  });
}

function updatePageItem(index, status, error) {
  const li = document.getElementById(`page-${index}`);
  if (!li) return;
  li.className = `page-item status-${status}`;
  const nameEl = li.querySelector('.page-name');
  const name = nameEl ? nameEl.textContent : `Page ${index}`;
  li.innerHTML = pageItemHTML(index, name, status, error);
}

function pageItemHTML(index, filename, status, error) {
  const icons = {
    waiting:    '○',
    processing: '<span class="spin">⟳</span>',
    retrying:   '<span class="spin">↻</span>',
    done:       '✓',
    error:      '✕',
  };
  const labels = {
    waiting:    'Waiting',
    processing: 'Processing…',
    retrying:   'Retrying…',
    done:       'Done',
    error:      error ? `Error: ${error}` : 'Error',
  };
  const icon  = icons[status]  || '○';
  const label = labels[status] || status;
  return `
    <span class="page-icon">${icon}</span>
    <span class="page-name">${filename}</span>
    <span class="page-status-label">${label}</span>
  `;
}

async function fetchAndStoreCombined(jobId) {
  try {
    const res = await fetch(`/api/process/content/${jobId}`);
    if (res.ok) {
      const data = await res.json();
      state.lastContent     = data.content;
      state.lastContentName = data.name;
    }
  } catch (_) {}
}

function showDoneSection() {
  document.getElementById('done-section').hidden = false;
  document.getElementById('status-msg').textContent = '';
}

function showErrorBanner(msg) {
  const el = document.getElementById('error-banner');
  el.hidden = false;
  el.textContent = `Error: ${msg}`;
}

function downloadCombined() {
  if (!state.currentJobId) return;
  window.location.href = `/api/process/download/${state.currentJobId}`;
}

function openInChat() {
  if (!state.lastContent) return;
  setChatContext(state.lastContent, state.lastContentName);
  switchTab('chat');
}

function openInWrite() {
  if (!state.lastContent) return;
  setWriteContext(state.lastContent, state.lastContentName);
  switchTab('write');
}

/* ── Shared file loading helpers ───────────────────────────────────────────── */

async function refreshFileList(tab) {
  const selectId = tab === 'chat' ? 'chat-file-select' : 'write-file-select';
  const sel = document.getElementById(selectId);
  try {
    const res = await fetch('/api/files/list');
    const { files } = await res.json();
    const current = sel.value;
    sel.innerHTML = '<option value="">— select a notebook file —</option>';
    files.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f.path;
      opt.textContent = `${f.name}  (${f.source})`;
      sel.appendChild(opt);
    });
    if (current) sel.value = current;
  } catch (_) {}
}

async function loadFileByPath(path) {
  const res = await fetch(`/api/files/content?path=${encodeURIComponent(path)}`);
  if (!res.ok) throw new Error(`Could not load file (HTTP ${res.status})`);
  return res.json(); // { content, name }
}

async function loadChatFile() {
  const path = document.getElementById('chat-file-select').value;
  if (!path) return;
  try {
    const data = await loadFileByPath(path);
    setChatContext(data.content, data.name);
  } catch (e) {
    alert(e.message);
  }
}

async function loadWriteFile() {
  const path = document.getElementById('write-file-select').value;
  if (!path) return;
  try {
    const data = await loadFileByPath(path);
    setWriteContext(data.content, data.name);
  } catch (e) {
    alert(e.message);
  }
}

async function uploadMdForChat(input) {
  const file = input.files[0];
  if (!file) return;
  try {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch('/api/files/upload', { method: 'POST', body: form });
    if (!res.ok) throw new Error(`Upload failed (HTTP ${res.status})`);
    const data = await res.json();
    setChatContext(data.content, data.filename);
    input.value = '';
  } catch (e) {
    alert(e.message);
  }
}

async function uploadMdForWrite(input) {
  const file = input.files[0];
  if (!file) return;
  try {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch('/api/files/upload', { method: 'POST', body: form });
    if (!res.ok) throw new Error(`Upload failed (HTTP ${res.status})`);
    const data = await res.json();
    setWriteContext(data.content, data.filename);
    input.value = '';
  } catch (e) {
    alert(e.message);
  }
}

function setChatContext(content, name) {
  state.chatContext  = content;
  state.chatHistory  = [];
  const ind = document.getElementById('chat-file-indicator');
  ind.hidden = false;
  ind.textContent = `📄 Loaded: ${name}`;
  document.getElementById('chat-panel').hidden = false;
  document.getElementById('chat-messages').innerHTML = '';
  appendSystemMessage(`Notebook loaded: **${name}**. Ask me anything about it.`);
}

function setWriteContext(content, name) {
  state.writeContext = content;
  const ind = document.getElementById('write-file-indicator');
  ind.hidden = false;
  ind.textContent = `📄 Loaded: ${name}`;
  document.getElementById('write-form').hidden = false;
}

/* ── Tab 2: Chat ───────────────────────────────────────────────────────────── */

function appendSystemMessage(text) {
  appendMessage('assistant', text);
}

function appendMessage(role, text) {
  const container = document.getElementById('chat-messages');

  const div = document.createElement('div');
  div.className = `msg ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = role === 'user' ? 'U' : '✦';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.textContent = text;

  div.appendChild(avatar);
  div.appendChild(bubble);
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

function appendThinking() {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'msg assistant';
  div.id = 'thinking-indicator';
  div.innerHTML = `
    <div class="msg-avatar">✦</div>
    <div class="msg-thinking">
      Thinking
      <span class="dots">
        <span></span><span></span><span></span>
      </span>
    </div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function removeThinking() {
  const el = document.getElementById('thinking-indicator');
  if (el) el.remove();
}

function handleChatKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChat();
  }
}

function askQuick(question) {
  document.getElementById('chat-input').value = question;
  sendChat();
}

async function sendChat() {
  if (!state.chatContext) return;

  const input = document.getElementById('chat-input');
  const text  = input.value.trim();
  if (!text) return;

  input.value = '';
  const sendBtn = document.getElementById('send-btn');
  sendBtn.disabled = true;

  appendMessage('user', text);
  state.chatHistory.push({ role: 'user', content: text });

  appendThinking();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        context:  state.chatContext,
        messages: state.chatHistory,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const { reply } = await res.json();
    removeThinking();
    appendMessage('assistant', reply);
    state.chatHistory.push({ role: 'assistant', content: reply });
  } catch (e) {
    removeThinking();
    appendMessage('assistant', `Error: ${e.message}`);
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

/* ── Tab 3: Write ──────────────────────────────────────────────────────────── */

async function generateContent() {
  if (!state.writeContext) return;

  const btn = document.getElementById('generate-btn');
  btn.disabled    = true;
  btn.textContent = 'Generating…';

  const topic      = document.getElementById('write-topic').value.trim();
  const outputType = document.getElementById('write-type').value;
  const tone       = document.getElementById('write-tone').value;

  try {
    const res = await fetch('/api/write', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        context:     state.writeContext,
        topic,
        output_type: outputType,
        tone,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const { content } = await res.json();
    state.lastGeneratedText = content;

    const card = document.getElementById('write-output-card');
    card.hidden = false;
    document.getElementById('write-output').textContent = content;
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    alert(`Generation failed: ${e.message}`);
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Generate';
  }
}

function copyOutput() {
  if (!state.lastGeneratedText) return;
  navigator.clipboard.writeText(state.lastGeneratedText).then(() => {
    const btn = event.target;
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  });
}

function downloadOutput() {
  if (!state.lastGeneratedText) return;
  const blob = new Blob([state.lastGeneratedText], { type: 'text/markdown' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = 'notebook-output.md';
  a.click();
  URL.revokeObjectURL(url);
}
