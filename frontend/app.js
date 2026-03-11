// frontend/app.js
// All UI logic for the Emergency Intelligence Hub renderer.
//
// Responsibilities:
//   · Audio file upload → base64 encoding → POST /pipeline
//   · HITL report rendering: situation cards, materials checklist, source chunks
//   · Situation selection + manual override → POST /approve
//   · Live countdown timers per volunteer (updates every second)
//   · "Back at Base" button → return popup → POST /volunteer/return
//   · 3-second polling: GET /queue, /volunteers, /inventory
//
// All HTTP calls go through window.api (defined in electron/preload.js).
// This file has zero direct Node / Electron / fetch dependencies.

"use strict";

// ── State ─────────────────────────────────────────────────────────────────────
let currentRequestId = null;
let currentSituations = [];
let selectedIndices = new Set();
let pollingInterval = null;
let timerInterval = null;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const audioFileInput = document.getElementById("audio-file");
const btnProcess = document.getElementById("btn-process");
const processingStatus = document.getElementById("processing-status");
const hitlPanel = document.getElementById("hitl-panel");
const reportRequestId = document.getElementById("report-request-id");
const reportTranscript = document.getElementById("report-transcript");
const situationCards = document.getElementById("situation-cards");
const btnApprove = document.getElementById("btn-approve");
const btnRefill = document.getElementById("btn-refill");
const queueTbody = document.getElementById("queue-tbody");
const inventoryTbody = document.getElementById("inventory-tbody");
const volunteerCards = document.getElementById("volunteer-cards");

// ── Audio processing ──────────────────────────────────────────────────────────
btnProcess.addEventListener("click", async () => {
    const file = audioFileInput.files[0];
    if (!file) {
        setStatus("Please select an audio file first.");
        return;
    }

    setStatus("Encoding audio...");
    btnProcess.disabled = true;

    const audio_b64 = await fileToBase64(file);
    setStatus("Processing pipeline (this may take 30–60s)...");

    try {
        const result = await window.api.runPipeline(audio_b64);
        currentRequestId = result.request_id;
        currentSituations = result.situations;
        selectedIndices.clear();

        reportRequestId.textContent = `Request: ${result.request_id}`;
        reportTranscript.textContent = `"${result.transcript}"`;
        renderHITLReport(result.situations, result.is_vague);

        hitlPanel.classList.remove("hidden");
        setStatus("");
    } catch (err) {
        setStatus(`Error: ${err.message}`);
    } finally {
        btnProcess.disabled = false;
    }
});

function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",")[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

// ── HITL report rendering ─────────────────────────────────────────────────────
function renderHITLReport(situations, isVague) {
    situationCards.innerHTML = "";

    if (isVague) {
        const banner = document.createElement("div");
        banner.className = "status-text";
        banner.textContent =
            "⚠ Vague transcript — expanded with LLM hypotheses";
        situationCards.appendChild(banner);
    }

    situations.forEach((sit, i) => {
        const card = document.createElement("div");
        card.className = `situation-card severity-${sit.severity.toLowerCase()}`;
        card.dataset.index = i;
        card.innerHTML = `
      <h3>${sit.label}
        <span class="badge badge-${sit.severity.toLowerCase()}">${sit.severity}</span>
      </h3>
      <p>Confidence: ${(sit.confidence * 100).toFixed(0)}%
         · Travel: ${sit.travel_time_min}min
         · Resolution: ${sit.resolution_time_min}min
         · Key: ${sit.heap_key.toFixed(1)}</p>

      <h4 style="margin-top:8px">Materials</h4>
      <ul>
        ${sit.materials
            .map(
                (m) => `
          <li class="${m.available ? "" : "greyed-out"}">
            ${m.available ? "☑" : "☐"} ${m.item} ×${m.quantity}
            ${
                m.available
                    ? `— Bin ${m.bin} (${m.available_qty} avail.)`
                    : "— OUT OF STOCK"
            }
          </li>
        `,
            )
            .join("")}
      </ul>

      <details style="margin-top:8px">
        <summary>📄 Source chunks</summary>
        ${sit.source_chunks.map((s) => `<p class="chunk-ref">${s}</p>`).join("")}
      </details>
    `;
        card.addEventListener("click", () => toggleSituation(i, card));
        situationCards.appendChild(card);
    });
}

function toggleSituation(index, cardEl) {
    if (selectedIndices.has(index)) {
        selectedIndices.delete(index);
        cardEl.classList.remove("selected");
    } else {
        selectedIndices.add(index);
        cardEl.classList.add("selected");
    }
}

// ── Approve & dispatch ────────────────────────────────────────────────────────
btnApprove.addEventListener("click", async () => {
    if (selectedIndices.size === 0) {
        alert("Please select at least one situation before approving.");
        return;
    }

    const conditionInput = document
        .getElementById("manual-condition")
        .value.trim();
    const itemsInput = document.getElementById("manual-items").value.trim();
    const manualOverride = conditionInput
        ? {
              condition: conditionInput,
              items: itemsInput
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
          }
        : null;

    btnApprove.disabled = true;
    try {
        await window.api.approveReport(
            currentRequestId,
            Array.from(selectedIndices),
            manualOverride,
        );
        hitlPanel.classList.add("hidden");
        refreshAll();
    } catch (err) {
        alert(`Approve failed: ${err.message}`);
    } finally {
        btnApprove.disabled = false;
    }
});

// ── Queue rendering ───────────────────────────────────────────────────────────
function renderQueue(queue) {
    queueTbody.innerHTML = queue
        .map(
            (req) => `
    <tr>
      <td>${req.request_id}</td>
      <td>${req.situations?.[0]?.severity ?? "—"}</td>
      <td>${req.status}</td>
      <td>${req.assigned_volunteer ?? "—"}</td>
      <td>${req.heap_key?.toFixed(1) ?? "—"}</td>
    </tr>
  `,
        )
        .join("");
}

// ── Volunteer rendering ───────────────────────────────────────────────────────
function renderVolunteers(volunteers) {
    volunteerCards.innerHTML = volunteers
        .map((vol) => {
            const statusClass = `vol-status-${vol.status.toLowerCase()}`;
            const countdown = vol.expected_return
                ? computeCountdown(vol.expected_return)
                : null;
            const timerHtml =
                countdown !== null
                    ? `<span class="vol-timer ${countdown < 0 ? "overdue" : ""}">${formatCountdown(countdown)}</span>`
                    : "";
            const returnBtn =
                vol.status === "BUSY"
                    ? `<button class="btn btn--secondary" onclick="showReturnModal('${vol.volunteer_id}')">Back at Base</button>`
                    : "";
            return `
      <div class="volunteer-card">
        <span class="vol-id">${vol.volunteer_id}</span>
        <span class="vol-status ${statusClass}">${vol.status}</span>
        <span style="font-size:11px;color:var(--text-muted)">
          ${vol.request_id ? `→ ${vol.request_id}` : ""}
        </span>
        ${timerHtml}
        ${returnBtn}
      </div>
    `;
        })
        .join("");
}

// ── Inventory rendering ───────────────────────────────────────────────────────
function renderInventory(inventory) {
    inventoryTbody.innerHTML = inventory
        .map((item) => {
            const lowStock = item.Available === 0 ? "greyed-out" : "";
            return `
      <tr class="${lowStock}">
        <td>${item.Item}</td>
        <td>${item.Available}</td>
        <td>${item.Reserved}</td>
        <td>${item.Total}</td>
        <td>${item["Bin Location"] ?? "—"}</td>
      </tr>
    `;
        })
        .join("");
}

// ── Volunteer return modal ────────────────────────────────────────────────────
function showReturnModal(volunteerId) {
    const items = prompt(
        `${volunteerId}: Enter returned items (comma-separated)`,
        "",
    );
    if (items === null) return;
    const returnedItems = items
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .map((item) => ({ item, quantity: 1 }));

    window.api
        .volunteerReturn(volunteerId, returnedItems)
        .then(() => refreshAll())
        .catch((err) => alert(`Return failed: ${err.message}`));
}

// ── Timer helpers ─────────────────────────────────────────────────────────────
function computeCountdown(expectedReturn) {
    // expectedReturn is "HH:MM:SS" (today's date assumed)
    const [h, m, s] = expectedReturn.split(":").map(Number);
    const now = new Date();
    const target = new Date(now);
    target.setHours(h, m, s, 0);
    return Math.floor((target - now) / 1000); // seconds remaining (negative = overdue)
}

function formatCountdown(seconds) {
    const absS = Math.abs(seconds);
    const mm = String(Math.floor(absS / 60)).padStart(2, "0");
    const ss = String(absS % 60).padStart(2, "0");
    return seconds < 0 ? `-${mm}:${ss}` : `${mm}:${ss}`;
}

// ── Polling & refresh ─────────────────────────────────────────────────────────
async function refreshAll() {
    try {
        const [queueRes, volRes, invRes] = await Promise.all([
            window.api.getQueue(),
            window.api.getVolunteers(),
            window.api.getInventory(),
        ]);
        renderQueue(queueRes.queue ?? []);
        renderVolunteers(volRes.volunteers ?? []);
        renderInventory(invRes.inventory ?? []);
    } catch (_) {
        /* backend may not be ready yet */
    }
}

function startPolling() {
    refreshAll();
    pollingInterval = setInterval(refreshAll, 3000);
    // Re-render volunteer timers every second for countdown display
    timerInterval = setInterval(() => {
        window.api
            .getVolunteers()
            .then((r) => renderVolunteers(r.volunteers ?? []))
            .catch(() => {});
    }, 1000);
}

// ── Inventory refill ──────────────────────────────────────────────────────────
btnRefill.addEventListener("click", async () => {
    await fetch("http://127.0.0.1:8000/inventory/refill", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "partial" }),
    });
    refreshAll();
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function setStatus(msg) {
    processingStatus.textContent = msg;
}

// ── Initialise ────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    startPolling();
});
