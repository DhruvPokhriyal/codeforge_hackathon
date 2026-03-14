// frontend/app.js
// ARIA — All renderer UI logic (Electron renderer).
"use strict";

// ── Config & State ─────────────────────────────────────────────────────────────

const DEFAULT_CONFIG = {
  polling: {
    queueMs: 3000,
    volunteersMs: 3000,
    timersMs: 1000,
  },
  audio: {
    acceptedExtensions: [".wav", ".mp3", ".flac", ".ogg", ".m4a"],
  },
  uiText: {
    upload: {
      dropHint: "Click to upload or drag & drop",
      invalidFile: "Invalid file. Please drop a supported audio file.",
      noFileSelected: "Please select an audio file first.",
    },
    processing: {
      starting: "⏳ Denoising audio...",
      steps: [
        "⏳ Transcribing speech...",
        "⏳ Running triage analysis...",
        "⏳ Allocating resources...",
      ],
      done: "✓ Processing complete.",
    },
  },
};

// Live configuration (overridden by backend /settings/frontend if available)
let DL_CONFIG = { ...DEFAULT_CONFIG };

// Live data — populated from backend.
let INVENTORY = [];
let QUEUE = [];
let VOLUNTEERS = [];

// Latest unapproved pipeline response (for HITL panel)
let CURRENT_PIPELINE = null;

// Local per-request timers (seconds since assignment) keyed by request_id
const REQUEST_TIMERS = {};

// ── State ──────────────────────────────────────────────────────────────────────
let activeTaskId = null;      // request currently in "Returned" modal
let selectedTaskId = null;    // request selected in queue panel
let aiPanelMode = 'queue';    // 'queue' | 'incoming'

function updateAiActionsVisibility() {
  const actions = document.querySelector('.ai-actions');
  if (!actions) return;
  const showActions = aiPanelMode === 'incoming' && !!CURRENT_PIPELINE;
  actions.classList.toggle('hidden', !showActions);
}

function updateAiModeUi() {
  const queueBtn = document.getElementById('ai-mode-queue');
  const incomingBtn = document.getElementById('ai-mode-incoming');
  if (!queueBtn || !incomingBtn) return;

  queueBtn.classList.toggle('active', aiPanelMode === 'queue');
  incomingBtn.classList.toggle('active', aiPanelMode === 'incoming');
  incomingBtn.disabled = !CURRENT_PIPELINE;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatTimer(s) {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${String(sec).padStart(2, '0')}`;
}

// ── Theme Switcher ──────────────────────────────────────────────────────────────
(function initTheme() {
  const saved = localStorage.getItem('dl-theme') || 'light';
  document.documentElement.setAttribute('data-theme', saved);

  document.querySelectorAll('.theme-btn').forEach(btn => {
    if (btn.dataset.theme === saved) btn.classList.add('active');

    btn.addEventListener('click', () => {
      const theme = btn.dataset.theme;
      document.documentElement.setAttribute('data-theme', theme);
      document.querySelectorAll('.theme-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      localStorage.setItem('dl-theme', theme);
    });
  });
})();

// ── NPU/CPU Switcher ────────────────────────────────────────────────────────────
let currentNpuMode = false;
(function initNpuMode() {
  const savedMode = localStorage.getItem('dl-npu') || 'cpu';
  currentNpuMode = savedMode === 'npu';

  document.querySelectorAll('.npu-btn').forEach(btn => {
    btn.classList.remove('active');
    if (btn.dataset.mode === savedMode) btn.classList.add('active');

    btn.addEventListener('click', () => {
      const mode = btn.dataset.mode;
      currentNpuMode = mode === 'npu';
      document.querySelectorAll('.npu-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      localStorage.setItem('dl-npu', mode);
    });
  });
})();



// ── Render: Inventory ──────────────────────────────────────────────────────────
function renderInventory() {
  const el = document.getElementById('inventory-list');
  el.innerHTML = INVENTORY.map(item => {
    const available = item.Available ?? item.qty ?? 0;
    const total = item.Total ?? item.total ?? 0;
    const pct = total > 0 ? Math.round((available / total) * 100) : 0;
    const isCrit = pct < 20;
    const countCls = isCrit ? 'inv-count critical-text' : 'inv-count';
    return `
      <div class="inv-item">
        <div class="inv-item-header">
          <span class="inv-name">${item.Item ?? item.name}</span>
          <span class="${countCls}">${available}/${total}</span>
        </div>
        <div class="inv-bar-track">
          <div class="inv-bar-fill${isCrit ? ' inv-bar-low' : ''}" style="width:${pct}%"></div>
        </div>
        <div class="inv-pct-row">
          <span class="inv-pct">${pct}%</span>
          ${isCrit ? '<span class="critical-low-label">CRITICAL LOW</span>' : ''}
        </div>
      </div>`;
  }).join('');
}

// ── Render: Task Cards ─────────────────────────────────────────────────────────
function renderTasks() {
  const el = document.getElementById('task-list');
  const active = QUEUE.filter(t => t.status !== 'RESOLVED');
  document.getElementById('incident-count').textContent = active.length;

  el.innerHTML = active.map(task => {
    const p = (task.priority || task.severity || (task.situations?.[0]?.severity) || 'HIGH').toString().toLowerCase();
    const status = task.status || 'PENDING';
    const stateClass = status === 'IN_PROGRESS' || status === 'ASSIGNED' ? 'in-progress' : 'pending';
    const statusLabel = stateClass === 'in-progress' ? (status || 'IN PROGRESS') : 'PENDING';
    const escalIcon = task.escalated
      ? '<span class="escalated-icon" title="Priority escalated">&#x26A0;</span>'
      : '';
    const hasVolunteer = !!(task.assigned_volunteer);
    const completeBtn = hasVolunteer
      ? `<button class="btn btn-complete" data-id="${task.request_id}">BACK AT BASE</button>`
      : '';
    const volunteerId = task.volunteer || task.assigned_volunteer;
    const volunteerLine = volunteerId
      ? `<div class="card-volunteer">&#x1F464; ${volunteerId}</div>`
      : '';
    const timerSec = REQUEST_TIMERS[task.request_id] ?? 0;
    const timer = formatTimer(timerSec);
    const timerCls = timerSec > 600 ? 'card-timer overdue' : 'card-timer';
    const selCls = task.request_id === selectedTaskId ? ' card-selected' : '';

    return `
      <div class="task-card priority-${p} ${stateClass}${selCls}" data-task-id="${task.request_id}">
        <div class="card-top">
          <div class="card-badges">
            <span class="priority-badge badge-${p}">[${task.priority || task.severity || (task.situations?.[0]?.severity) || 'HIGH'}]</span>
            ${escalIcon}
            <span class="status-badge status-${stateClass}">${statusLabel}</span>
          </div>
          <span class="${timerCls}">T-${timer}</span>
        </div>
        <div class="card-title">${task.title || (task.situations?.[0]?.label) || 'Emergency Request'}</div>
        ${volunteerLine}
        <div class="card-footer">
          <div class="card-location">&#x1F4CD; ${task.location || task.request_id}</div>
          ${completeBtn}
        </div>
      </div>`;
  }).join('');

  // Card click -> select and populate AI panel
  el.querySelectorAll('.task-card').forEach(card => {
    card.addEventListener('click', () => {
      selectedTaskId = card.dataset.taskId;
      el.querySelectorAll('.task-card').forEach(c => c.classList.remove('card-selected'));
      card.classList.add('card-selected');
      renderAiPanel();
    });
  });

  // COMPLETE button — stop click from bubbling to card
  el.querySelectorAll('.btn-complete').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      openCompleteModal(btn.dataset.id);
    });
  });
}

// ── Render: AI Review Panel (Human-in-the-Loop) ───────────────────────────────
function renderAiPanel() {
  const content = document.getElementById('ai-panel-content');
  if (!content) return;


  updateAiModeUi();
  updateAiActionsVisibility();

  if (aiPanelMode === 'incoming') {
    if (!CURRENT_PIPELINE) {
      content.innerHTML = '<div class="ai-no-selection">No incoming task awaiting approval.</div>';
      return;
    }


    const sit = CURRENT_PIPELINE.situations?.[0];
    if (!sit) {
      content.innerHTML = '<div class="ai-no-selection">No situations returned from pipeline.</div>';
      return;
    }
    const priority = sit.severity || 'HIGH';
    const severityCls = priority === 'CRITICAL' ? 'critical-text' : 'high-text';

    const steps = sit.instructions || [];
    const stepsHtml = steps.map((s, i) => `
    <div class="step-row">
      <span class="step-num">${i + 1}</span>
      <span class="step-text">${s}</span>
    </div>`).join('');

    const sources = sit.source_chunks || [];
    const uniqueSources = [...new Set(sources)];
    const sourcesHtml = uniqueSources.map(s => `
    <li class="source-item">
      <span class="source-icon">&#x1F4C4;</span>
      <span class="source-name">${s}</span>
    </li>`).join('');

    const items = (sit.materials || []).map(m => ({
      name: m.item,
      qty: m.quantity,
    }));
    const itemsHtml = items.map(item => {
      const inv = INVENTORY.find(i => (i.Item ?? i.name) === item.name);
      const avail = inv ? (inv.Available ?? inv.qty) : '?';
      const total = inv ? (inv.Total ?? inv.total) : '?';
      const pct = (inv && inv.Total > 0) ? (inv.Available / inv.Total) * 100 : 100;
      const cls = pct >= 80 ? 'green-text' : pct >= 40 ? 'orange-text' : 'critical-text';
      return `
      <div class="material-row">
        <span class="material-name">${item.name} &times;${item.qty}</span>
        <span class="material-qty ${cls}">${avail}/${total}</span>
      </div>`;
    }).join('');

    content.innerHTML = `
    <div class="ai-task-id">${CURRENT_PIPELINE.request_id}</div>
    <div class="ai-task-title">${sit.label || 'Emergency Request'}</div>
    <div class="ai-meta-chips">
      <span class="ai-chip ${severityCls}">${priority}</span>
      <span class="ai-chip">&#x23F1; ~${sit.resolution_time_min ?? '?'} min</span>
    </div>
    <hr class="divider" />

    <div class="ai-section-label">TRANSCRIPT</div>
    <div class="ai-transcript">${CURRENT_PIPELINE.transcript}</div>
    <hr class="divider" />

    <div class="ai-section-label">STEPS TO TAKE</div>
    <div class="steps-list">${stepsHtml}</div>
    <hr class="divider" />

    <div class="ai-section-label">SOURCES</div>
    <ul class="sources-list">${sourcesHtml}</ul>
    <hr class="divider" />

    <div class="ai-section-label">REQUIRED MATERIALS</div>
    <div class="materials-list">${itemsHtml}</div>
    `;
    return;
  }

  if (!selectedTaskId) {
    content.innerHTML = '<div class="ai-no-selection">&#x25B6;&nbsp; Select a task to view AI analysis</div>';
    return;
  }

  const task = QUEUE.find(t => t.request_id === selectedTaskId);
  if (!task) return;

  const sit0 = task.situations?.[0];
  const priority = task.priority || task.severity || sit0?.severity || 'HIGH';
  const severityCls = priority === 'CRITICAL' ? 'critical-text' : 'high-text';

  const steps = task.steps || task.instructions || sit0?.instructions || [];
  const stepsHtml = steps.map((s, i) => `
    <div class="step-row">
      <span class="step-num">${i + 1}</span>
      <span class="step-text">${s}</span>
    </div>`).join('');

  const handoff = task.handoff || task.handoff_logs || [];
  const handoffHtml = handoff.map((entry, i) => {
    const isLast = i === handoff.length - 1;
    return `
      <div class="handoff-entry">
        <div class="handoff-dot${entry.done ? ' done' : ''}"></div>
        ${!isLast ? '<div class="handoff-line"></div>' : '<div></div>'}
        <div class="handoff-content">
          <div class="handoff-agent">${entry.agent || entry.step || 'Agent'}</div>
          <div class="handoff-time">${entry.time || ''}</div>
          <div class="handoff-note">${entry.note || entry.reason || ''}</div>
        </div>
      </div>`;
  }).join('');

  const sources = task.sources || task.source_chunks || sit0?.source_chunks || [];
  const uniqueSources = [...new Set(sources)];
  const sourcesHtml = uniqueSources.map(s => `
    <li class="source-item">
      <span class="source-icon">&#x1F4C4;</span>
      <span class="source-name">${s}</span>
    </li>`).join('');

  const items = task.items || (task.materials || sit0?.materials || []).map(m => ({
    name: m.item,
    qty: m.quantity,
  }));
  const itemsHtml = items.map(item => {
    const inv = INVENTORY.find(i => (i.Item ?? i.name) === item.name);
    const avail = inv ? (inv.Available ?? inv.qty) : '?';
    const total = inv ? (inv.Total ?? inv.total) : '?';
    const baseAvail = inv ? (inv.Available ?? inv.qty) : 0;
    const baseTotal = inv ? (inv.Total ?? inv.total) : 0;
    const pct = baseTotal > 0 ? (baseAvail / baseTotal) * 100 : 100;
    const cls = pct >= 80 ? 'green-text' : pct >= 40 ? 'orange-text' : 'critical-text';
    return `
      <div class="material-row">
        <span class="material-name">${item.name} &times;${item.qty}</span>
        <span class="material-qty ${cls}">${avail}/${total}</span>
      </div>`;
  }).join('');

  content.innerHTML = `
    <div class="ai-task-id">${task.id || task.request_id}</div>
    <div class="ai-task-title">${task.title || (task.situations && task.situations[0]?.label) || 'Emergency Request'}</div>
    <div class="ai-meta-chips">
      <span class="ai-chip ${severityCls}">${priority}</span>
      <span class="ai-chip">&#x23F1; ~${task.estTimeMins ?? (sit0?.resolution_time_min ?? '?')} min</span>
      <span class="ai-chip">&#x1F465; ${task.estVictims ?? ''}</span>
    </div>
    <hr class="divider" />

    <div class="ai-section-label">TRANSCRIPT</div>
    <div class="ai-transcript">${task.transcript}</div>
    <hr class="divider" />

    <div class="ai-section-label">STEPS TO TAKE</div>
    <div class="steps-list">${stepsHtml}</div>
    <hr class="divider" />

    <div class="ai-section-label">AGENT HANDOFF</div>
    <div class="handoff-timeline">${handoffHtml}</div>
    <hr class="divider" />

    <div class="ai-section-label">SOURCES</div>
    <ul class="sources-list">${sourcesHtml}</ul>
    <hr class="divider" />

    <div class="ai-section-label">REQUIRED MATERIALS</div>
    <div class="materials-list">${itemsHtml}</div>
  `;
}

// ── Countdown Timers ──────────────────────────────────────────────────────────
function tickTimers() {
  QUEUE.forEach(task => {
    if (task.status !== 'ASSIGNED') return;
    const id = task.request_id;
    REQUEST_TIMERS[id] = (REQUEST_TIMERS[id] ?? 0) + 1;
    const card = document.querySelector(`.task-card[data-task-id="${id}"]`);
    if (card) {
      const timerEl = card.querySelector('.card-timer');
      if (timerEl) {
        const secs = REQUEST_TIMERS[id];
        timerEl.textContent = `T-${formatTimer(secs)}`;
        if (secs > 600) timerEl.classList.add('overdue');
      }
    }
  });
}

// ── Upload Zone ────────────────────────────────────────────────────────────────
(function initUpload() {
  const zone = document.getElementById('upload-zone');
  const fileInput = document.getElementById('audio-file');
  const uploadLabel = document.getElementById('upload-label');

  // Apply configured accepted extensions to the file input
  if (fileInput && DL_CONFIG.audio?.acceptedExtensions) {
    fileInput.accept = DL_CONFIG.audio.acceptedExtensions.join(',');
  }

  if (uploadLabel && DL_CONFIG.uiText?.upload?.dropHint) {
    uploadLabel.innerHTML = DL_CONFIG.uiText.upload.dropHint.replace(/\n/g, '<br>');
  }

  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('dragging');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragging'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dragging');
    const f = e.dataTransfer.files[0];
    const exts = DL_CONFIG.audio.acceptedExtensions || [];
    const re = new RegExp(`\\.(${exts.map(x => x.replace('.', '')).join('|')})$`, 'i');
    if (f && re.test(f.name)) {
      uploadLabel.textContent = f.name;
      zone.classList.add('has-file');
    } else {
      const msg = DL_CONFIG.uiText.upload.invalidFile || 'Invalid file.';
      uploadLabel.innerHTML = msg.replace(/\n/g, '<br>');
    }
  });

  fileInput.addEventListener('change', e => {
    const f = e.target.files[0];
    if (f) {
      uploadLabel.textContent = f.name;
      zone.classList.add('has-file');
    }
  });
})();

// ── Process Memo Button ────────────────────────────────────────────────────────
(function initProcessBtn() {
  const btn = document.getElementById('btn-process');
  const status = document.getElementById('process-status');
  const waveform = document.getElementById('waveform');
  const zone = document.getElementById('upload-zone');
  const fileInput = document.getElementById('audio-file');

  btn.addEventListener('click', () => {
    if (!zone.classList.contains('has-file') || !fileInput || !fileInput.files[0]) {
      const msg = DL_CONFIG.uiText.upload.noFileSelected || 'Please select an audio file first.';
      if (status) {
        status.classList.remove('hidden', 'text-success');
        status.textContent = msg;
      }
      zone.classList.add('zone-shake');
      setTimeout(() => zone.classList.remove('zone-shake'), 600);
      return;
    }

    btn.disabled = true;
    btn.textContent = 'PROCESSING...';
    status.classList.remove('hidden', 'text-success');
    status.textContent = DL_CONFIG.uiText.processing.starting;
    waveform.classList.add('active');

    const steps = DL_CONFIG.uiText.processing.steps || [];
    const stepDelay = 1600;
    steps.forEach((msg, idx) => {
      setTimeout(() => { status.textContent = msg; }, stepDelay * (idx + 1));
    });

    // If backend API is available, send the audio as base64
    const file = fileInput.files[0];
    if (window.api && typeof window.api.runPipeline === 'function' && file) {
      const reader = new FileReader();
      reader.onload = async (e) => {
        try {
          const buffer = e.target.result;
          const bytes = new Uint8Array(buffer);
          let binary = "";
          for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
          }
          const audioB64 = btoa(binary);
          console.log('[app.js] Calling runPipeline, audio base64 length:', audioB64.length, 'npuMode:', currentNpuMode);
          const resp = await window.api.runPipeline(audioB64, currentNpuMode);

          // DEBUG: Log the full response
          console.log('[app.js] Pipeline response received:', JSON.stringify(resp).substring(0, 2000));
          console.log('[app.js] Response keys:', Object.keys(resp));
          console.log('[app.js] situations field:', typeof resp.situations, Array.isArray(resp.situations), 'length:', resp.situations?.length);
          if (resp.situations?.length > 0) {
            console.log('[app.js] situations[0] keys:', Object.keys(resp.situations[0]));
            console.log('[app.js] situations[0].label:', resp.situations[0].label);
          } else {
            console.log('[app.js] WARNING: situations is empty or missing!');
          }

          // Hold the latest pipeline result for HITL approval in the AI panel
          CURRENT_PIPELINE = resp;
          aiPanelMode = 'incoming';
          selectedTaskId = null;
          renderAiPanel();

          status.textContent = DL_CONFIG.uiText.processing.done;
          status.classList.add('text-success');
        } catch (err) {
          console.error('Pipeline error', err);
          status.textContent = 'Pipeline error. See console.';
        } finally {
          btn.disabled = false;
          btn.textContent = 'PROCESS MEMO';
          waveform.classList.remove('active');
        }
      };
      reader.readAsArrayBuffer(file);
    } else {
      // Fallback: no backend available, just complete after a delay
      setTimeout(() => {
        status.textContent = DL_CONFIG.uiText.processing.done;
        status.classList.add('text-success');
        btn.disabled = false;
        btn.textContent = 'PROCESS MEMO';
        waveform.classList.remove('active');
      }, stepDelay * ((DL_CONFIG.uiText.processing.steps || []).length + 2));
    }
  });
})();

// ── AI Panel: Approve ─────────────────────────────────────────────────────────
(function initApprove() {
  const btnApprove = document.getElementById('btn-approve');
  btnApprove.addEventListener('click', () => {
    if (!window.api || typeof window.api.approveReport !== 'function') return;
    if (!CURRENT_PIPELINE) return;

    btnApprove.disabled = true;
    btnApprove.textContent = 'APPROVING...';

    // For now, auto-select the top situation (index 0)
    const selected_indices = [0];
    const manual_override = window.__DL_PENDING_OVERRIDE || null;

    window.api.approveReport(CURRENT_PIPELINE.request_id, selected_indices, manual_override)
      .then(resp => {
        // Update queue and volunteers from backend response
        QUEUE = resp.queue || [];
        VOLUNTEERS = resp.volunteers || [];

        // Clear current pipeline / override
        CURRENT_PIPELINE = null;
        aiPanelMode = 'queue';
        window.__DL_PENDING_OVERRIDE = null;
        selectedTaskId = resp.request_id || null;

        renderTasks();
        renderAiPanel();
      })
      .catch(err => {
        console.error('Approve error', err);
      })
      .finally(() => {
        btnApprove.textContent = 'APPROVE';
        btnApprove.disabled = false;
      });
  });
})();

// ── Override Modal ────────────────────────────────────────────────────────────
function openOverrideModal() {
  // Reset text fields
  document.getElementById('override-situation').value = '';
  document.getElementById('override-steps').value = '';

  // Build item rows from INVENTORY using safe DOM API
  const container = document.getElementById('override-items');
  container.innerHTML = '';

  INVENTORY.forEach(item => {
    const row = document.createElement('div');
    row.className = 'override-item-row';

    const nameEl = document.createElement('span');
    nameEl.className = 'override-item-name';
    nameEl.textContent = item.Item ?? item.name;

    const btnMinus = document.createElement('button');
    btnMinus.className = 'btn btn-qty';
    btnMinus.type = 'button';
    btnMinus.textContent = '\u2212';  // minus sign

    const qtyInput = document.createElement('input');
    qtyInput.type = 'number';
    qtyInput.className = 'qty-input';
    qtyInput.value = 0;
    qtyInput.min = 0;
    const maxQty = item.Available ?? item.qty ?? 0;
    qtyInput.max = maxQty;
    qtyInput.dataset.item = item.Item ?? item.name;

    const btnPlus = document.createElement('button');
    btnPlus.className = 'btn btn-qty';
    btnPlus.type = 'button';
    btnPlus.textContent = '+';

    const availEl = document.createElement('span');
    availEl.className = 'override-item-avail';
    availEl.textContent = `avail: ${maxQty}`;

    btnMinus.addEventListener('click', () => {
      qtyInput.value = Math.max(0, parseInt(qtyInput.value || 0) - 1);
    });
    btnPlus.addEventListener('click', () => {
      qtyInput.value = Math.min(maxQty, parseInt(qtyInput.value || 0) + 1);
    });

    row.appendChild(nameEl);
    row.appendChild(btnMinus);
    row.appendChild(qtyInput);
    row.appendChild(btnPlus);
    row.appendChild(availEl);
    container.appendChild(row);
  });

  document.getElementById('override-overlay').classList.remove('hidden');
}

function closeOverrideModal() {
  document.getElementById('override-overlay').classList.add('hidden');
}

(function initOverride() {
  document.getElementById('btn-override').addEventListener('click', () => {
    if (!CURRENT_PIPELINE) return;
    openOverrideModal();
  });
  document.getElementById('override-cancel').addEventListener('click', closeOverrideModal);

  document.getElementById('override-overlay').addEventListener('click', e => {
    if (e.target === document.getElementById('override-overlay')) closeOverrideModal();
  });

  document.getElementById('override-submit').addEventListener('click', () => {
    const situation = document.getElementById('override-situation').value.trim();
    const steps = document.getElementById('override-steps').value.trim();
    if (!situation) {
      document.getElementById('override-situation').focus();
      return;
    }
    if (!CURRENT_PIPELINE) return;
    if (!window.api || typeof window.api.overrideReport !== 'function') return;

    // Gather selected quantities (items with qty > 0)
    const resources = [...document.querySelectorAll('.qty-input')]
      .map(inp => ({ item: inp.dataset.item, qty: parseInt(inp.value || 0) }))
      .filter(r => r.qty > 0);

    const payload = {
      condition: situation,
      resources,
      notes: steps,
    };

    const submitBtn = document.getElementById('override-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'APPLYING...';

    window.api.overrideReport(CURRENT_PIPELINE.request_id, payload)
      .then(resp => {
        QUEUE = resp.queue || [];
        VOLUNTEERS = resp.volunteers || [];
        CURRENT_PIPELINE = null;
        window.__DL_PENDING_OVERRIDE = null;
        aiPanelMode = 'queue';
        selectedTaskId = resp.request_id || null;
        renderTasks();
        renderAiPanel();
      })
      .catch(err => {
        console.error('Override apply error', err);
      })
      .finally(() => {
        submitBtn.textContent = 'APPLY OVERRIDE';
        submitBtn.disabled = false;
        closeOverrideModal();
      });
  });
})();

// ── Complete & Returned Modal ──────────────────────────────────────────────────
function openCompleteModal(taskId) {
  const task = QUEUE.find(t => t.request_id === taskId);
  if (!task) return;
  activeTaskId = taskId;

  const checklist = document.getElementById('modal-checklist');
  checklist.innerHTML = '';

  const items = task.items_taken || [];
  items.forEach(item => {
    const row = document.createElement('div');
    row.className = 'override-item-row';  // reuse the same row style as Override modal

    // Name + "taken" label
    const nameEl = document.createElement('span');
    nameEl.className = 'override-item-name';
    nameEl.textContent = item.item;

    const takenEl = document.createElement('span');
    takenEl.className = 'override-item-avail';
    takenEl.textContent = `taken: ${item.quantity}`;

    const btnMinus = document.createElement('button');
    btnMinus.className = 'btn btn-qty';
    btnMinus.type = 'button';
    btnMinus.textContent = '\u2212';

    const qtyInput = document.createElement('input');
    qtyInput.type = 'number';
    qtyInput.className = 'qty-input return-qty';
    qtyInput.value = item.quantity;   // default to full return
    qtyInput.min = 0;
    qtyInput.max = item.quantity;
    qtyInput.dataset.item = item.item;
    qtyInput.dataset.max = item.quantity;

    const btnPlus = document.createElement('button');
    btnPlus.className = 'btn btn-qty';
    btnPlus.type = 'button';
    btnPlus.textContent = '+';

    btnMinus.addEventListener('click', () => {
      qtyInput.value = Math.max(0, parseInt(qtyInput.value || 0) - 1);
      updateConfirmBtn();
    });
    btnPlus.addEventListener('click', () => {
      const max = parseInt(qtyInput.dataset.max || item.quantity, 10);
      qtyInput.value = Math.min(max, parseInt(qtyInput.value || 0) + 1);
      updateConfirmBtn();
    });
    qtyInput.addEventListener('input', updateConfirmBtn);

    row.appendChild(nameEl);
    row.appendChild(btnMinus);
    row.appendChild(qtyInput);
    row.appendChild(btnPlus);
    row.appendChild(takenEl);
    checklist.appendChild(row);
  });

  updateConfirmBtn();
  document.getElementById('modal-overlay').classList.remove('hidden');
}

function updateConfirmBtn() {
  // Returning zero items is allowed; keep confirm enabled.
  document.getElementById('modal-confirm').disabled = false;
}

function closeModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
  activeTaskId = null;
}

document.getElementById('modal-cancel').addEventListener('click', closeModal);

document.getElementById('modal-confirm').addEventListener('click', () => {
  if (!activeTaskId) return;
  const task = QUEUE.find(t => t.request_id === activeTaskId);
  if (!task || !window.api || typeof window.api.volunteerReturn !== 'function') {
    closeModal();
    return;
  }

  const returned_items = [];
  document.querySelectorAll('.return-qty').forEach(inp => {
    const qty = parseInt(inp.value || 0);
    if (qty > 0) {
      returned_items.push({ item: inp.dataset.item, quantity: qty });
    }
  });

  const volunteerId = task.assigned_volunteer;
  window.api.volunteerReturn(volunteerId, returned_items)
    .then(resp => {
      QUEUE = resp.queue || [];
      VOLUNTEERS = resp.volunteers || [];
      INVENTORY = resp.inventory || INVENTORY;
      // Drop local timer for this request
      delete REQUEST_TIMERS[activeTaskId];
      renderTasks();
      renderInventory();
      renderAiPanel();
    })
    .catch(err => {
      console.error('Volunteer return error', err);
    })
    .finally(() => {
      closeModal();
    });
});

// Close modal on overlay click
document.getElementById('modal-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('modal-overlay')) closeModal();
});

// Close modals on Escape key
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeModal();
    closeOverrideModal();
  }
});

// ── Initialise ────────────────────────────────────────────────────────────────
async function bootstrapApp() {
  const queueModeBtn = document.getElementById('ai-mode-queue');
  const incomingModeBtn = document.getElementById('ai-mode-incoming');
  if (queueModeBtn) {
    queueModeBtn.addEventListener('click', () => {
      aiPanelMode = 'queue';
      renderAiPanel();
    });
  }
  if (incomingModeBtn) {
    incomingModeBtn.addEventListener('click', () => {
      if (!CURRENT_PIPELINE) return;
      aiPanelMode = 'incoming';
      renderAiPanel();
    });
  }

  // Load config from backend if available
  if (window.api && typeof window.api.getSettings === 'function') {
    try {
      const settings = await window.api.getSettings();
      DL_CONFIG = {
        polling: {
          queueMs: settings.polling?.queue_ms ?? DEFAULT_CONFIG.polling.queueMs,
          volunteersMs: settings.polling?.volunteers_ms ?? DEFAULT_CONFIG.polling.volunteersMs,
          timersMs: settings.polling?.timers_ms ?? DEFAULT_CONFIG.polling.timersMs,
        },
        audio: {
          acceptedExtensions: settings.audio?.accepted_extensions ?? DEFAULT_CONFIG.audio.acceptedExtensions,
        },
        uiText: {
          upload: {
            dropHint: settings.ui_text?.upload?.drop_hint ?? DEFAULT_CONFIG.uiText.upload.dropHint,
            invalidFile: settings.ui_text?.upload?.invalid_file ?? DEFAULT_CONFIG.uiText.upload.invalidFile,
            noFileSelected: settings.ui_text?.upload?.no_file_selected ?? DEFAULT_CONFIG.uiText.upload.noFileSelected,
          },
          processing: {
            starting: settings.ui_text?.processing?.starting ?? DEFAULT_CONFIG.uiText.processing.starting,
            steps: settings.ui_text?.processing?.steps ?? DEFAULT_CONFIG.uiText.processing.steps,
            done: settings.ui_text?.processing?.done ?? DEFAULT_CONFIG.uiText.processing.done,
          },
        },
      };
    } catch (err) {
      console.warn('Failed to load settings from backend, using defaults.', err);
    }
  }

  // Initial inventory load
  if (window.api && typeof window.api.getInventory === 'function') {
    try {
      const resp = await window.api.getInventory();
      INVENTORY = resp.inventory || [];
    } catch (err) {
      console.warn('Failed to load inventory from backend, falling back to empty.', err);
      INVENTORY = [];
    }
  }

  // Initial queue & volunteers load
  if (window.api && typeof window.api.getQueue === 'function') {
    try {
      const resp = await window.api.getQueue();
      QUEUE = resp.queue || resp.queue || [];
    } catch (err) {
      console.warn('Failed to load queue from backend.', err);
      QUEUE = [];
    }
  }
  if (window.api && typeof window.api.getVolunteers === 'function') {
    try {
      const resp = await window.api.getVolunteers();
      VOLUNTEERS = resp.volunteers || [];
    } catch (err) {
      console.warn('Failed to load volunteers from backend.', err);
      VOLUNTEERS = [];
    }
  }

  selectedTaskId = null;

  renderInventory();
  renderTasks();
  renderAiPanel();

  // Periodic polling for live data
  if (window.api && typeof window.api.getQueue === 'function') {
    setInterval(async () => {
      try {
        const resp = await window.api.getQueue();
        const newQueue = resp.queue || [];
        // Maintain timers only for active (non-resolved) requests
        const activeIds = new Set(newQueue.filter(r => r.status !== 'RESOLVED').map(r => r.request_id));
        Object.keys(REQUEST_TIMERS).forEach(id => {
          if (!activeIds.has(id)) {
            delete REQUEST_TIMERS[id];
          }
        });
        QUEUE = newQueue;
        renderTasks();
      } catch (err) {
        console.warn('Queue polling failed', err);
      }
    }, DL_CONFIG.polling.queueMs);
  }

  if (window.api && typeof window.api.getVolunteers === 'function') {
    setInterval(async () => {
      try {
        const resp = await window.api.getVolunteers();
        VOLUNTEERS = resp.volunteers || [];
      } catch (err) {
        console.warn('Volunteer polling failed', err);
      }
    }, DL_CONFIG.polling.volunteersMs);
  }

  if (window.api && typeof window.api.getInventory === 'function') {
    setInterval(async () => {
      try {
        const resp = await window.api.getInventory();
        INVENTORY = resp.inventory || [];
        renderInventory();
      } catch (err) {
        console.warn('Inventory polling failed', err);
      }
    }, DL_CONFIG.polling.queueMs);
  }

  // Timer tick interval uses configurable polling
  setInterval(tickTimers, DL_CONFIG.polling.timersMs);

  // ── Volunteer Count Form ──────────────────────────────────────────────────
  const volBtn = document.getElementById('btn-set-volunteers');
  const volInput = document.getElementById('volunteer-count-input');
  const volStatus = document.getElementById('volunteer-count-status');

  async function submitVolunteerCount() {
    const count = parseInt(volInput.value, 10);
    if (!count || count < 1) {
      if (volStatus) volStatus.textContent = '⚠ Enter a valid number ≥ 1';
      return;
    }
    if (!window.api || typeof window.api.setVolunteerCount !== 'function') {
      if (volStatus) volStatus.textContent = '⚠ API unavailable';
      return;
    }
    volBtn.disabled = true;
    try {
      const resp = await window.api.setVolunteerCount(count);
      VOLUNTEERS = resp.volunteers || [];
      if (volStatus) volStatus.textContent = `✓ Set to ${resp.count ?? count} volunteers`;
    } catch (err) {
      if (volStatus) volStatus.textContent = `✗ ${err.message}`;
    }
    volBtn.disabled = false;
  }

  if (volBtn && volInput) {
    volBtn.addEventListener('click', submitVolunteerCount);
    volInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); submitVolunteerCount(); }
    });
  }

  // ── Inventory Update Form ─────────────────────────────────────────────────
  const invBtn = document.getElementById('btn-update-inventory');
  const invItem = document.getElementById('inv-update-item');
  const invQty = document.getElementById('inv-update-qty');
  const invStatus = document.getElementById('inv-update-status');

  async function submitInventoryUpdate() {
    const item = invItem.value.trim();
    const qty = parseInt(invQty.value, 10);
    if (!item || !qty || qty < 1) {
      if (invStatus) invStatus.textContent = '⚠ Enter item name and quantity';
      return;
    }
    if (!window.api || typeof window.api.updateInventory !== 'function') {
      if (invStatus) invStatus.textContent = '⚠ API unavailable';
      return;
    }
    invBtn.disabled = true;
    try {
      const resp = await window.api.updateInventory(item, qty);
      INVENTORY = resp.inventory || [];
      renderInventory();
      if (invStatus) invStatus.textContent = `✓ Added ${qty}× ${item}`;
      invItem.value = '';
      invQty.value = '';
    } catch (err) {
      if (invStatus) invStatus.textContent = `✗ ${err.message}`;
    }
    invBtn.disabled = false;
  }

  if (invBtn && invItem && invQty) {
    invBtn.addEventListener('click', submitInventoryUpdate);
    invItem.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); submitInventoryUpdate(); }
    });
    invQty.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); submitInventoryUpdate(); }
    });
  }

  // ── Create New Item Form ──────────────────────────────────────────────────
  const createBtn = document.getElementById('btn-create-item');
  const createItem = document.getElementById('inv-create-item');
  const createCap = document.getElementById('inv-create-cap');
  const createStatus = document.getElementById('inv-create-status');

  async function submitCreateItem() {
    const name = createItem.value.trim();
    const cap = parseInt(createCap.value, 10);
    if (!name || !cap || cap < 1) {
      if (createStatus) createStatus.textContent = '⚠ Enter item name and capacity';
      return;
    }
    if (!window.api || typeof window.api.createInventoryItem !== 'function') {
      if (createStatus) createStatus.textContent = '⚠ API unavailable';
      return;
    }
    createBtn.disabled = true;
    try {
      const resp = await window.api.createInventoryItem(name, cap);
      INVENTORY = resp.inventory || [];
      renderInventory();
      if (createStatus) createStatus.textContent = `✓ Created ${name} (${cap}/${cap})`;
      createItem.value = '';
      createCap.value = '';
    } catch (err) {
      if (createStatus) createStatus.textContent = `✗ ${err.message}`;
    }
    createBtn.disabled = false;
  }

  if (createBtn && createItem && createCap) {
    createBtn.addEventListener('click', submitCreateItem);
    createItem.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); submitCreateItem(); }
    });
    createCap.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); submitCreateItem(); }
    });
  }
}

document.addEventListener('DOMContentLoaded', bootstrapApp);
