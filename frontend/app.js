// frontend/app.js
// Digital Lifeboat — All renderer UI logic.
// No backend integration; runs entirely on mock data for offline demo.
"use strict";

// ── Mock Data ──────────────────────────────────────────────────────────────────

const INVENTORY = [
  { name: 'Water Bottles', qty: 47,  total: 100 },
  { name: 'Medical Kits',  qty: 8,   total: 20  },
  { name: 'Blankets',      qty: 5,   total: 50  },
  { name: 'Food Rations',  qty: 120, total: 200 },
  { name: 'Rescue Gear',   qty: 12,  total: 15  },
  { name: 'First Aid Kits',qty: 3,   total: 30  },
];

const TASKS = [
  {
    id: 'REQ-001',
    title: 'Residential Collapse — Pine St & 5th Ave',
    priority: 'CRITICAL',
    status: 'IN_PROGRESS',
    location: 'Downtown',
    volunteer: 'VOL-07',
    elapsedSec: 0,
    escalated: true,
    transcript: '\u201cBuilding collapsed on Pine Street, multiple people trapped, need immediate assistance.\u201d',
    estVictims: '5\u20138',
    estTimeMins: 45,
    steps: [
      'Secure perimeter \u2014 50 m radius, redirect civilian traffic.',
      'Deploy structural assessment team before any entry.',
      'Establish triage station at NE corner of intersection.',
      'Initiate void-space search using rescue gear.',
      'Radio status update every 10 minutes to HQ.',
    ],
    sources: [
      'FEMA Urban Search & Rescue Field Operations Guide.pdf',
      'Multi-Victim Structural Collapse Protocol v3.pdf',
      'Downtown Zone Hazard Map 2025.pdf',
    ],
    handoff: [
      { agent: 'Intake Agent',    time: '14:23:01', note: 'Audio denoised & transcribed.',             done: true  },
      { agent: 'Triage Agent',    time: '14:23:04', note: 'Severity: CRITICAL \u2014 Est. 5\u20138 victims.', done: true  },
      { agent: 'RAG Agent',       time: '14:23:05', note: 'Protocol docs retrieved (3 sources).',      done: true  },
      { agent: 'Logistics Agent', time: '14:23:07', note: 'Resources allocated, VOL-07 dispatched.',   done: true  },
    ],
    items: [
      { name: 'Medical Kits', qty: 2 },
      { name: 'Rescue Gear',  qty: 3 },
      { name: 'Stretcher',    qty: 1 },
    ],
  },
  {
    id: 'REQ-002',
    title: 'Hospital Backup Power Failure \u2014 Medical Center',
    priority: 'HIGH',
    status: 'PENDING',
    location: 'Midtown',
    volunteer: null,
    elapsedSec: 0,
    escalated: false,
    transcript: '\u201cMedical center on Midtown Ave has lost main power. ICU and OR on backup. Backup generator also failing.\u201d',
    estVictims: '120+ patients at risk',
    estTimeMins: 30,
    steps: [
      'Contact facility engineer for generator room access.',
      'Deploy portable generator unit to loading dock B.',
      'Prioritise power to ICU, OR, and neonatal ward.',
      'Coordinate with grid operator for emergency reconnect.',
      'Station technician on-site until main power restored.',
    ],
    sources: [
      'Hospital Emergency Power Standard IEC 60364-7-710.pdf',
      'Mass Casualty Power Failure Response Plan v2.pdf',
    ],
    handoff: [
      { agent: 'Intake Agent',    time: '14:31:10', note: 'Audio transcribed \u2014 power failure confirmed.',  done: true  },
      { agent: 'Triage Agent',    time: '14:31:13', note: 'Severity: HIGH \u2014 life support at risk.',         done: true  },
      { agent: 'RAG Agent',       time: '14:31:14', note: 'IEC standard & response plan retrieved.',         done: true  },
      { agent: 'Logistics Agent', time: '14:31:16', note: 'Awaiting volunteer assignment.',                   done: false },
    ],
    items: [
      { name: 'Generator',      qty: 1 },
      { name: 'Fuel Canisters', qty: 4 },
    ],
  },
  {
    id: 'REQ-003',
    title: 'Water Main Rupture \u2014 Central Park Area',
    priority: 'HIGH',
    status: 'IN_PROGRESS',
    location: 'North',
    volunteer: 'VOL-03',
    elapsedSec: 24,
    escalated: false,
    transcript: '\u201cLarge water main burst near Central Park north entrance. Street flooding, basement units at risk.\u201d',
    estVictims: '~40 residents',
    estTimeMins: 90,
    steps: [
      'Shut off water main valve at Junction Node 7-N.',
      'Deploy water pumps to prevent basement flooding.',
      'Erect safety barriers on affected road sections.',
      'Notify utilities for emergency repair crew dispatch.',
      'Establish temporary water supply for affected residents.',
    ],
    sources: [
      'City Water Infrastructure Emergency Manual.pdf',
      'North Zone Utility Map v2024.pdf',
    ],
    handoff: [
      { agent: 'Intake Agent',    time: '14:45:00', note: 'Audio transcribed \u2014 rupture location confirmed.', done: true  },
      { agent: 'Triage Agent',    time: '14:45:02', note: 'Severity: HIGH \u2014 ~40 residents at flood risk.',   done: true  },
      { agent: 'RAG Agent',       time: '14:45:03', note: 'Utility manuals retrieved (2 sources).',             done: true  },
      { agent: 'Logistics Agent', time: '14:45:05', note: 'Resources allocated, VOL-03 dispatched.',            done: true  },
    ],
    items: [
      { name: 'Water Pump',      qty: 1 },
      { name: 'Safety Barriers', qty: 6 },
    ],
  },
];

// ── State ──────────────────────────────────────────────────────────────────────
let activeTaskId   = null;
let selectedTaskId = TASKS[0].id;   // pre-select first task for immediate AI panel display

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

// ── Render: Inventory ──────────────────────────────────────────────────────────
function renderInventory() {
  const el = document.getElementById('inventory-list');
  el.innerHTML = INVENTORY.map(item => {
    const pct     = Math.round((item.qty / item.total) * 100);
    const isCrit  = pct < 20;
    const countCls = isCrit ? 'inv-count critical-text' : 'inv-count';
    return `
      <div class="inv-item">
        <div class="inv-item-header">
          <span class="inv-name">${item.name}</span>
          <span class="${countCls}">${item.qty}/${item.total}</span>
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
  const active = TASKS.filter(t => t.status !== 'COMPLETE');
  document.getElementById('incident-count').textContent = active.length;

  el.innerHTML = active.map(task => {
    const p           = task.priority.toLowerCase();
    const stateClass  = task.status === 'IN_PROGRESS' ? 'in-progress' : 'pending';
    const statusLabel = task.status === 'IN_PROGRESS' ? 'IN PROGRESS' : 'PENDING';
    const escalIcon   = task.escalated
      ? '<span class="escalated-icon" title="Priority escalated">&#x26A0;</span>'
      : '';
    const completeBtn = task.status === 'IN_PROGRESS'
      ? `<button class="btn btn-complete" data-id="${task.id}">COMPLETE</button>`
      : '';
    const volunteerLine = task.volunteer
      ? `<div class="card-volunteer">&#x1F464; ${task.volunteer}</div>`
      : '';
    const timer    = formatTimer(task.elapsedSec);
    const timerCls = task.elapsedSec > 600 ? 'card-timer overdue' : 'card-timer';
    const selCls   = task.id === selectedTaskId ? ' card-selected' : '';

    return `
      <div class="task-card priority-${p} ${stateClass}${selCls}" data-task-id="${task.id}">
        <div class="card-top">
          <div class="card-badges">
            <span class="priority-badge badge-${p}">[${task.priority}]</span>
            ${escalIcon}
            <span class="status-badge status-${stateClass}">${statusLabel}</span>
          </div>
          <span class="${timerCls}">T-${timer}</span>
        </div>
        <div class="card-title">${task.title}</div>
        ${volunteerLine}
        <div class="card-footer">
          <div class="card-location">&#x1F4CD; ${task.location}</div>
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

// ── Render: Agent Handoff Timeline ────────────────────────────────────────────
function renderHandoffTimeline() {
  const el = document.getElementById('handoff-timeline');
  el.innerHTML = HANDOFF_LOG.map((entry, i) => {
    const isLast = i === HANDOFF_LOG.length - 1;
    return `
      <div class="handoff-entry">
        <div class="handoff-dot${entry.done ? ' done' : ''}"></div>
        ${!isLast ? '<div class="handoff-line"></div>' : '<div></div>'}
        <div class="handoff-content">
          <div class="handoff-agent">${entry.agent}</div>
          <div class="handoff-time">${entry.time}</div>
          <div class="handoff-note">${entry.note}</div>
        </div>
      </div>`;
  }).join('');
}

// ── Render: Materials ─────────────────────────────────────────────────────────
function renderMaterials() {
  const el = document.getElementById('materials-list');
  el.innerHTML = MOCK_ASSESSMENT.materials.map(m => {
    const pct = (m.qty / m.total) * 100;
    const cls = pct >= 80 ? 'green-text' : pct >= 40 ? 'orange-text' : 'critical-text';
    return `
      <div class="material-row">
        <span class="material-name">${m.name}</span>
        <span class="material-qty ${cls}">${m.qty}/${m.total}</span>
      </div>`;
  }).join('');
}

// ── Countdown Timers ──────────────────────────────────────────────────────────
function tickTimers() {
  let needsFullRender = false;
  TASKS.forEach(task => {
    if (task.status !== 'IN_PROGRESS') return;
    task.elapsedSec++;
    // Auto-escalate if over 10 minutes
    if (task.elapsedSec > 600 && !task.escalated) {
      task.escalated = true;
      needsFullRender = true;
    }
    // Update timer display in-place
    const card = document.querySelector(`.task-card[data-task-id="${task.id}"]`);
    if (card) {
      const timerEl = card.querySelector('.card-timer');
      if (timerEl) {
        timerEl.textContent = `T-${formatTimer(task.elapsedSec)}`;
        if (task.elapsedSec > 600) timerEl.classList.add('overdue');
      }
    }
  });
  if (needsFullRender) renderTasks();
}

// ── Upload Zone ────────────────────────────────────────────────────────────────
(function initUpload() {
  const zone        = document.getElementById('upload-zone');
  const fileInput   = document.getElementById('audio-file');
  const uploadLabel = document.getElementById('upload-label');

  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('dragging');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragging'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dragging');
    const f = e.dataTransfer.files[0];
    if (f && /\.(mp3|wav)$/i.test(f.name)) {
      uploadLabel.textContent = f.name;
      zone.classList.add('has-file');
    } else {
      uploadLabel.innerHTML = 'Invalid file.<br>Drop .mp3 or .wav';
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
  const btn     = document.getElementById('btn-process');
  const status  = document.getElementById('process-status');
  const waveform = document.getElementById('waveform');
  const zone    = document.getElementById('upload-zone');

  btn.addEventListener('click', () => {
    if (!zone.classList.contains('has-file')) {
      zone.classList.add('zone-shake');
      setTimeout(() => zone.classList.remove('zone-shake'), 600);
      return;
    }

    btn.disabled = true;
    btn.textContent = 'PROCESSING...';
    status.classList.remove('hidden', 'text-success');
    status.textContent = '\u23F3 Denoising audio...';
    waveform.classList.add('active');

    const steps = [
      [1600, '\u23F3 Transcribing speech...'],
      [3200, '\u23F3 Running triage analysis...'],
      [4800, '\u23F3 Allocating resources...'],
    ];

    steps.forEach(([delay, msg]) => {
      setTimeout(() => { status.textContent = msg; }, delay);
    });

    setTimeout(() => {
      status.textContent = '\u2713 Processing complete.';
      status.classList.add('text-success');
      btn.disabled = false;
      btn.textContent = 'PROCESS MEMO';
      waveform.classList.remove('active');
    }, 6400);
  });
})();

// ── AI Panel: Approve ─────────────────────────────────────────────────────────
(function initApprove() {
  const btnApprove = document.getElementById('btn-approve');
  btnApprove.addEventListener('click', () => {
    btnApprove.textContent = '\u2713 APPROVED';
    btnApprove.classList.add('btn-approved');
    btnApprove.disabled = true;
    setTimeout(() => {
      btnApprove.textContent = 'APPROVE';
      btnApprove.classList.remove('btn-approved');
      btnApprove.disabled = false;
    }, 2500);
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
    nameEl.textContent = item.name;

    const btnMinus = document.createElement('button');
    btnMinus.className = 'btn btn-qty';
    btnMinus.type = 'button';
    btnMinus.textContent = '\u2212';  // minus sign

    const qtyInput = document.createElement('input');
    qtyInput.type = 'number';
    qtyInput.className = 'qty-input';
    qtyInput.value = 0;
    qtyInput.min = 0;
    qtyInput.max = item.qty;
    qtyInput.dataset.item = item.name;

    const btnPlus = document.createElement('button');
    btnPlus.className = 'btn btn-qty';
    btnPlus.type = 'button';
    btnPlus.textContent = '+';

    const availEl = document.createElement('span');
    availEl.className = 'override-item-avail';
    availEl.textContent = `avail: ${item.qty}`;

    btnMinus.addEventListener('click', () => {
      qtyInput.value = Math.max(0, parseInt(qtyInput.value || 0) - 1);
    });
    btnPlus.addEventListener('click', () => {
      qtyInput.value = Math.min(item.qty, parseInt(qtyInput.value || 0) + 1);
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
  document.getElementById('btn-override').addEventListener('click', openOverrideModal);
  document.getElementById('override-cancel').addEventListener('click', closeOverrideModal);

  document.getElementById('override-overlay').addEventListener('click', e => {
    if (e.target === document.getElementById('override-overlay')) closeOverrideModal();
  });

  document.getElementById('override-submit').addEventListener('click', () => {
    const situation = document.getElementById('override-situation').value.trim();
    const steps     = document.getElementById('override-steps').value.trim();
    if (!situation) {
      document.getElementById('override-situation').focus();
      return;
    }
    // Gather selected quantities (items with qty > 0)
    const resources = [...document.querySelectorAll('.qty-input')]
      .map(inp => ({ item: inp.dataset.item, qty: parseInt(inp.value || 0) }))
      .filter(r => r.qty > 0);

    // Log to console (no backend integration)
    console.log('[OVERRIDE]', { situation, steps, resources });

    closeOverrideModal();
  });
})();

// ── Complete & Returned Modal ──────────────────────────────────────────────────
function openCompleteModal(taskId) {
  const task = TASKS.find(t => t.id === taskId);
  if (!task) return;
  activeTaskId = taskId;

  const checklist = document.getElementById('modal-checklist');
  // Build checklist with text-only content (no HTML injection from data)
  checklist.innerHTML = '';
  task.items.forEach((item, i) => {
    const label = document.createElement('label');
    label.className = 'checklist-item';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'return-check';
    cb.dataset.index = i;
    cb.addEventListener('change', () => {
      label.classList.toggle('checked', cb.checked);
      updateConfirmBtn();
    });

    const span = document.createElement('span');
    // Safe text assignment — no innerHTML
    span.textContent = `${item.name} \u00D7 ${item.qty}`;

    label.appendChild(cb);
    label.appendChild(span);
    checklist.appendChild(label);
  });

  updateConfirmBtn();
  document.getElementById('modal-overlay').classList.remove('hidden');
}

function updateConfirmBtn() {
  const allChecked = [...document.querySelectorAll('.return-check')].every(c => c.checked);
  document.getElementById('modal-confirm').disabled = !allChecked;
}

function closeModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
  activeTaskId = null;
}

document.getElementById('modal-cancel').addEventListener('click', closeModal);

document.getElementById('modal-confirm').addEventListener('click', () => {
  if (!activeTaskId) return;
  const task = TASKS.find(t => t.id === activeTaskId);
  if (task) {
    task.status = 'COMPLETE';
    task.items.forEach(item => {
      const inv = INVENTORY.find(i => i.name === item.name);
      if (inv) inv.qty = Math.min(inv.total, inv.qty + item.qty);
    });
    // If the completed task was selected, move selection to next available
    if (selectedTaskId === activeTaskId) {
      const next = TASKS.find(t => t.status !== 'COMPLETE' && t.id !== activeTaskId);
      selectedTaskId = next ? next.id : null;
    }
  }
  closeModal();
  renderTasks();
  renderInventory();
  renderAiPanel();
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
document.addEventListener('DOMContentLoaded', () => {
  renderInventory();
  renderTasks();
  renderAiPanel();
  setInterval(tickTimers, 1000);
});
