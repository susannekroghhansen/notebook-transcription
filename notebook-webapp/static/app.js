/* ── State ─────────────────────────────────────────────────────────────────── */

const state = {
  // Tab 1
  selectedFile:      null,
  currentJobId:      null,
  eventSource:       null,
  // Shared context
  lastContent:       null,
  lastContentName:   null,
  // Tab 2 – Chat
  chatContext:       null,
  chatHistory:       [],
  chatItems:         [],          // [{job_id, name, content}] currently loaded
  chatSelectedIds:   new Set(),   // checked in picker (before applying)
  // Tab 3 – Write
  writeContext:      null,
  lastGeneratedText: '',
  writeItems:        [],
  writeSelectedIds:  new Set(),
  // Shared picker
  libraryCache:      null,        // [{job_id, notebook, date, …}]
};

/* ── Tab switching ─────────────────────────────────────────────────────────── */

function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach((btn, i) => {
    const names = ['library', 'process', 'chat', 'write'];
    btn.classList.toggle('active', names[i] === name);
  });
  document.querySelectorAll('.tab').forEach(el => {
    const id = el.id.replace('tab-', '');
    el.hidden = id !== name;
  });
  if (name === 'library') loadLibrary();
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
        // Bust library cache so next picker open sees the new notebook
        state.libraryCache = null;
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
      break;
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

/* ── Notebook picker ───────────────────────────────────────────────────────── */

let _pickerOutsideHandler = null;

async function togglePicker(tab) {
  const panel = document.getElementById(`${tab}-picker-panel`);
  if (!panel.hidden) { closePicker(tab); return; }

  panel.hidden = false;
  document.getElementById(`${tab}-picker-trigger`).classList.add('open');

  const list = document.getElementById(`${tab}-picker-list`);
  list.innerHTML = '<p class="picker-loading">Loading…</p>';

  try {
    const res = await fetch('/api/library');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { notebooks } = await res.json();
    state.libraryCache = notebooks;
    populatePicker(tab);
  } catch (e) {
    list.innerHTML = `<p class="picker-loading">Failed to load: ${esc(e.message)}</p>`;
    return;
  }

  setTimeout(() => {
    _pickerOutsideHandler = (e) => {
      const wrap = document.getElementById(`${tab}-picker-wrap`);
      if (wrap && !wrap.contains(e.target)) closePicker(tab);
    };
    document.addEventListener('click', _pickerOutsideHandler);
  }, 0);
}

function closePicker(tab) {
  const panel = document.getElementById(`${tab}-picker-panel`);
  if (panel) panel.hidden = true;
  const trigger = document.getElementById(`${tab}-picker-trigger`);
  if (trigger) trigger.classList.remove('open');
  if (_pickerOutsideHandler) {
    document.removeEventListener('click', _pickerOutsideHandler);
    _pickerOutsideHandler = null;
  }
}

function populatePicker(tab) {
  const nbs = state.libraryCache || [];
  const ids = tab === 'chat' ? state.chatSelectedIds : state.writeSelectedIds;
  const list = document.getElementById(`${tab}-picker-list`);

  if (nbs.length === 0) {
    list.innerHTML = '<p class="picker-loading">No transcribed notebooks yet.</p>';
    return;
  }

  const allChecked  = nbs.every(nb => ids.has(nb.job_id));
  const someChecked = nbs.some(nb => ids.has(nb.job_id));

  list.innerHTML = `
    <label class="picker-row picker-row-all">
      <input type="checkbox" id="${tab}-all-check"
             ${allChecked ? 'checked' : ''}
             onchange="onSelectAll('${tab}', this.checked)">
      <span class="picker-row-name">Select all</span>
    </label>
    <hr class="picker-divider">
    ${nbs.map(nb => `
      <label class="picker-row">
        <input type="checkbox" value="${esc(nb.job_id)}"
               ${ids.has(nb.job_id) ? 'checked' : ''}
               onchange="onPickerCheck('${tab}', '${esc(nb.job_id)}', this.checked)">
        <span class="picker-row-name">${esc(nb.notebook)}</span>
        ${nb.date ? `<span class="picker-row-meta">${esc(nb.date)}</span>` : ''}
      </label>
    `).join('')}
  `;

  const allCheck = document.getElementById(`${tab}-all-check`);
  if (allCheck && someChecked && !allChecked) allCheck.indeterminate = true;
}

function onPickerCheck(tab, jobId, checked) {
  const ids = tab === 'chat' ? state.chatSelectedIds : state.writeSelectedIds;
  if (checked) ids.add(jobId); else ids.delete(jobId);
  updateSelectAll(tab);
  updatePickerLabel(tab);
}

function onSelectAll(tab, checked) {
  const nbs = state.libraryCache || [];
  const ids = tab === 'chat' ? state.chatSelectedIds : state.writeSelectedIds;
  nbs.forEach(nb => checked ? ids.add(nb.job_id) : ids.delete(nb.job_id));
  populatePicker(tab);
  updatePickerLabel(tab);
}

function updateSelectAll(tab) {
  const nbs = state.libraryCache || [];
  const ids = tab === 'chat' ? state.chatSelectedIds : state.writeSelectedIds;
  const allCheck = document.getElementById(`${tab}-all-check`);
  if (!allCheck || nbs.length === 0) return;
  const allChecked  = nbs.every(nb => ids.has(nb.job_id));
  const someChecked = nbs.some(nb => ids.has(nb.job_id));
  allCheck.checked       = allChecked;
  allCheck.indeterminate = someChecked && !allChecked;
}

function updatePickerLabel(tab) {
  const ids   = tab === 'chat' ? state.chatSelectedIds : state.writeSelectedIds;
  const label = document.getElementById(`${tab}-picker-label`);
  if (!label) return;
  if (ids.size === 0) {
    label.textContent = 'Select notebooks…';
  } else if (ids.size === 1) {
    const nb = (state.libraryCache || []).find(n => n.job_id === [...ids][0]);
    label.textContent = nb ? nb.notebook : '1 notebook selected';
  } else {
    label.textContent = `${ids.size} notebooks selected`;
  }
}

async function applyPicker(tab) {
  const ids = tab === 'chat' ? state.chatSelectedIds : state.writeSelectedIds;
  if (ids.size === 0) { closePicker(tab); return; }

  const btn      = document.querySelector(`#${tab}-picker-panel .picker-apply-btn`);
  const origText = btn.textContent;
  btn.disabled   = true;
  btn.textContent = 'Loading…';

  try {
    const items = await Promise.all([...ids].map(async jobId => {
      const res = await fetch(`/api/library/${encodeURIComponent(jobId)}/content`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const { content } = await res.json();
      const nb = (state.libraryCache || []).find(n => n.job_id === jobId);
      return { job_id: jobId, name: nb ? nb.notebook : jobId, content };
    }));

    const combined = items.map(i => i.content).join('\n\n---\n\n');

    if (tab === 'chat') {
      state.chatItems   = items;
      state.chatContext = combined;
      state.chatHistory = [];
      document.getElementById('chat-messages').innerHTML = '';
      document.getElementById('chat-panel').hidden = false;
      const label = items.length === 1
        ? `**${items[0].name}**`
        : `${items.length} notebooks`;
      appendSystemMessage(`Loaded ${label}. Ask me anything about it.`);
    } else {
      state.writeItems   = items;
      state.writeContext = combined;
      document.getElementById('write-form').hidden = false;
    }

    renderPills(tab);
    closePicker(tab);
  } catch (e) {
    alert(`Failed to load: ${e.message}`);
    btn.disabled    = false;
    btn.textContent = origText;
  }
}

function renderPills(tab) {
  const items = tab === 'chat' ? state.chatItems : state.writeItems;
  const row   = document.getElementById(`${tab}-pills`);
  if (!row) return;
  if (items.length === 0) {
    row.hidden   = true;
    row.innerHTML = '';
    return;
  }
  row.hidden = false;
  row.innerHTML = items.map(item => {
    const safeId = esc(item.job_id || '');
    return `<span class="nb-pill">${esc(item.name)}<button class="nb-pill-remove" onclick="removePill('${tab}','${safeId}')" aria-label="Remove">×</button></span>`;
  }).join('');
}

function removePill(tab, jobId) {
  const id = jobId || null;
  if (tab === 'chat') {
    state.chatItems      = state.chatItems.filter(i => i.job_id !== id);
    state.chatSelectedIds.delete(id);
    state.chatContext    = state.chatItems.map(i => i.content).join('\n\n---\n\n') || null;
    if (state.chatItems.length === 0) {
      document.getElementById('chat-panel').hidden = true;
      state.chatHistory = [];
    }
  } else {
    state.writeItems      = state.writeItems.filter(i => i.job_id !== id);
    state.writeSelectedIds.delete(id);
    state.writeContext    = state.writeItems.map(i => i.content).join('\n\n---\n\n') || null;
    if (state.writeItems.length === 0) {
      document.getElementById('write-form').hidden = true;
    }
  }
  renderPills(tab);
  updatePickerLabel(tab);
}

/* ── Shared context setters (used by Process tab + Library card actions) ───── */

function setChatContext(content, name) {
  state.chatItems   = [{ job_id: null, name, content }];
  state.chatContext = content;
  state.chatHistory = [];
  document.getElementById('chat-messages').innerHTML = '';
  document.getElementById('chat-panel').hidden = false;
  appendSystemMessage(`Notebook loaded: **${name}**. Ask me anything about it.`);
  renderPills('chat');
}

function setWriteContext(content, name) {
  state.writeItems   = [{ job_id: null, name, content }];
  state.writeContext = content;
  document.getElementById('write-form').hidden = false;
  renderPills('write');
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

/* ── Tab 0: Library ────────────────────────────────────────────────────────── */

function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function loadLibrary() {
  const grid  = document.getElementById('library-grid');
  const empty = document.getElementById('library-empty');
  grid.innerHTML = '<p class="library-loading">Loading…</p>';
  empty.hidden   = true;

  try {
    const res = await fetch('/api/library');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { notebooks } = await res.json();

    grid.innerHTML = '';
    if (notebooks.length === 0) {
      empty.hidden = false;
      return;
    }

    notebooks.forEach(nb => {
      grid.appendChild(buildLibraryCard(nb));
    });
  } catch (e) {
    grid.innerHTML = `<p class="library-loading">Failed to load library: ${esc(e.message)}</p>`;
  }
}

function buildLibraryCard(nb) {
  const card = document.createElement('div');
  card.className = 'library-card';

  const metaParts = [];
  if (nb.pages > 0) metaParts.push(`${nb.pages} page${nb.pages !== 1 ? 's' : ''}`);
  if (nb.date)      metaParts.push(nb.date);
  const metaLine = metaParts.join(' · ');

  const tagsHTML = (nb.tags && nb.tags.length > 0)
    ? nb.tags.map(t => `<span class="tag-pill">${esc(t)}</span>`).join('')
    : '';

  const jobEnc = encodeURIComponent(nb.job_id);

  card.innerHTML = `
    <div class="library-card-header">
      <div>
        <div class="library-title">${esc(nb.notebook)}</div>
        ${metaLine ? `<div class="library-meta">${esc(metaLine)}</div>` : ''}
      </div>
      <div class="library-actions">
        <button class="btn-secondary" data-action="chat" data-job="${esc(nb.job_id)}">Open in Chat</button>
        <button class="btn-secondary" data-action="write" data-job="${esc(nb.job_id)}">Open in Write</button>
        <a class="btn-secondary" href="/api/library/${jobEnc}/download" download="${esc(nb.combined_md)}">Download .md</a>
      </div>
    </div>
    <div class="library-tags" id="tags-${esc(nb.job_id)}">${tagsHTML}</div>
  `;

  card.querySelector('[data-action="chat"]').addEventListener('click', () =>
    libraryOpenIn(nb.job_id, 'chat')
  );
  card.querySelector('[data-action="write"]').addEventListener('click', () =>
    libraryOpenIn(nb.job_id, 'write')
  );

  return card;
}

async function libraryOpenIn(jobId, tab) {
  try {
    const res = await fetch(`/api/library/${encodeURIComponent(jobId)}/content`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { content, name } = await res.json();
    const nb          = (state.libraryCache || []).find(n => n.job_id === jobId);
    const displayName = nb ? nb.notebook : name;

    if (tab === 'chat') {
      state.chatSelectedIds = new Set([jobId]);
      setChatContext(content, displayName);
      state.chatItems[0].job_id = jobId;   // enable pill × removal
    } else {
      state.writeSelectedIds = new Set([jobId]);
      setWriteContext(content, displayName);
      state.writeItems[0].job_id = jobId;
    }
    renderPills(tab);
    switchTab(tab);
  } catch (e) {
    alert(`Could not load notebook: ${e.message}`);
  }
}
