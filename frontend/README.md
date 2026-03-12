# Digital Lifeboat — Frontend

Electron-based desktop application for offline disaster relief coordination.

## Quick Start

```bash
cd frontend
npm install      # first time only
npm start        # launch the app
```

> **Always run npm commands from inside the `frontend/` directory**, not the project root.

---

## File Structure

```
frontend/
├── index.html          # App shell — 3-column layout + modals (no logic)
├── app.js              # All UI logic, mock data, rendering, event handling
├── styles.css          # Theme variables + all component styles
├── package.json        # Electron entry point & scripts
├── electron/
│   ├── main.js         # Electron main process — creates BrowserWindow
│   └── preload.js      # contextBridge IPC layer (for future backend wiring)
└── README.md           # This file
```

---

## Layout — 3-Column Command Centre

| Column | Name | Contents |
|--------|------|----------|
| 1 (260 px) | **Intake & Inventory** | Hub status, inventory bars, audio waveform, file upload, PROCESS MEMO button |
| 2 (flex) | **Priority Queue** | Task cards — click any card to load its AI analysis in Column 3 |
| 3 (380 px) | **AI Review** | Full task detail: transcript, steps, agent handoff, RAG sources, materials |

---

## Themes

Toggle via the **LIGHT / DARK / HC** buttons in the **bottom-left corner**. Choice is persisted to `localStorage`.

| Theme | Background | Text | Use case |
|-------|-----------|------|----------|
| **Light** | `#f0f2f5` | `#111` | Normal daylight operations |
| **Dark** | `#0d0d0d` | `#e0e0e0` | Reduced eye strain / night ops |
| **HC** (High-Contrast) | `#000000` | `#ccff00` | Harsh conditions, low-power OLED displays, maximum readability |

---

## Mock Data (app.js)

All data is defined at the top of `app.js` — no backend required.

### `INVENTORY` array
Each entry: `{ name, qty, total }`  
Items below 20% stock show a blinking **CRITICAL LOW** label.

### `TASKS` array
Each task carries the full information model used across the UI:

| Field | Type | Used in |
|-------|------|---------|
| `id` | `string` | Card header, AI panel |
| `title` | `string` | Card body, AI panel heading |
| `priority` | `'CRITICAL' \| 'HIGH'` | Card badge colour, AI chip |
| `status` | `'IN_PROGRESS' \| 'PENDING' \| 'COMPLETE'` | Card state, border glow |
| `location` | `string` | Card footer |
| `volunteer` | `string \| null` | Card body |
| `elapsedSec` | `number` | Live countdown timer on card |
| `escalated` | `boolean` | ⚠ escalation icon on card |
| `transcript` | `string` | AI panel — TRANSCRIPT section |
| `estVictims` | `string` | AI panel — meta chip |
| `estTimeMins` | `number` | AI panel — meta chip |
| `steps` | `string[]` | AI panel — STEPS TO TAKE numbered list |
| `sources` | `string[]` | AI panel — SOURCES (PDF filenames) |
| `handoff` | `{ agent, time, note, done }[]` | AI panel — AGENT HANDOFF timeline |
| `items` | `{ name, qty }[]` | AI panel — REQUIRED MATERIALS; Complete modal checklist |

---

## Key Interactions

### Task Selection
Click any task card in Column 2 → Column 3 (AI Review) populates with that task's full data.  
The first task is pre-selected on load.

### COMPLETE & RETURNED
Click **COMPLETE** on an in-progress card → modal opens with a checklist of items taken.  
All items must be checked before **CONFIRM RETURN** is enabled.  
On confirm: task is marked complete, items are returned to inventory counts, AI panel moves to next task.

### PROCESS MEMO
Upload a `.mp3` or `.wav` file → click **PROCESS MEMO** → animated pipeline simulation  
(Denoise → Transcribe → Triage → Allocate) with waveform animation.

### OVERRIDE
Click **OVERRIDE** in Column 3 → modal with:
- **Situation** — text input (required)
- **Steps to take** — textarea
- **Resources** — `+`/`−` quantity selectors per inventory item (capped at available stock)

### Auto-escalation
Tasks in progress for > 10 minutes automatically gain the ⚠ escalation icon and timer turns red.

---

## Styling Notes

- **Brutalist design**: `border-radius: 0 !important` applied globally — no rounded corners.
- **No gradients, no heavy shadows** — mission-critical terminal aesthetic.
- In-progress cards animate with a priority-coloured glow (`@keyframes glow-*`).
- CRITICAL LOW inventory label blinks via `@keyframes blink-label`.
- Waveform bars animate during processing via `@keyframes wave-scale`.

---

## Adding a New Task

Add an entry to the `TASKS` array in `app.js` following the schema above. The UI renders everything dynamically — no HTML changes needed.

## Future Backend Integration

`electron/preload.js` exposes `window.api` via `contextBridge` with stubs for:
- `runPipeline(audio_b64)` → `POST /pipeline`
- `approveReport(...)` → `POST /approve`
- `volunteerReturn(...)` → `POST /volunteer/return`
- `getQueue()`, `getVolunteers()`, `getInventory()`

Replace mock data calls in `app.js` with `await window.api.*` calls to wire up the FastAPI backend.
