// frontend/electron/preload.js
// Electron Preload — contextBridge IPC layer
//
// Exposes a minimal window.api object to the renderer (frontend/app.js).
// All HTTP calls are made here — the renderer never accesses Node or fetch directly.
//
// Exposed API:
//   window.api.runPipeline(audio_b64)                → POST /pipeline
//   window.api.approveReport(request_id, selected_indices, manual_override?)
//                                                     → POST /approve
//   window.api.volunteerReturn(volunteer_id, returned_items)
//                                                     → POST /volunteer/return
//   window.api.getQueue()                             → GET /queue
//   window.api.getVolunteers()                        → GET /volunteers
//   window.api.getInventory()                         → GET /inventory

const { contextBridge } = require("electron");
const http = require("http");

// Allow overriding the API host/port via environment for flexibility.
const API_HOST = process.env.DL_API_HOST || "127.0.0.1";
const API_PORT = Number(process.env.DL_API_PORT || 8000);
const API_BASE = `http://${API_HOST}:${API_PORT}`;

/**
 * Generic HTTP helper — returns a Promise<object>.
 * Only connects to 127.0.0.1 (offline-only, no external network calls).
 */
function apiCall(method, path, body = null) {
    return new Promise((resolve, reject) => {
        const payload = body ? JSON.stringify(body) : null;
        const options = {
            hostname: API_HOST,
            port: API_PORT,
            path,
            method,
            headers: {
                "Content-Type": "application/json",
                ...(payload
                    ? { "Content-Length": Buffer.byteLength(payload) }
                    : {}),
            },
        };
        const req = http.request(options, (res) => {
            let data = "";
            res.on("data", (chunk) => {
                data += chunk;
            });
            res.on("end", () => {
                console.log(`[preload] ${method} ${path} => status=${res.statusCode}, body length=${data.length}`);
                try {
                    const parsed = data ? JSON.parse(data) : {};
                    if (path === '/pipeline') {
                        console.log('[preload] /pipeline response keys:', Object.keys(parsed));
                        console.log('[preload] /pipeline situations type:', typeof parsed.situations, 'isArray:', Array.isArray(parsed.situations), 'length:', parsed.situations?.length);
                        console.log('[preload] /pipeline situations[0]:', JSON.stringify(parsed.situations?.[0])?.substring(0, 500));
                    }
                    if (res.statusCode >= 400) {
                        const msg = parsed?.detail || `HTTP ${res.statusCode}`;
                        reject(new Error(msg));
                        return;
                    }
                    resolve(parsed);
                } catch (e) {
                    console.error('[preload] JSON parse error:', e.message, 'raw data (first 500 chars):', data.substring(0, 500));
                    reject(new Error("Invalid JSON response"));
                }
            });
        });
        req.on("error", (err) => {
            console.error(`[preload] ${method} ${path} request error:`, err.message);
            reject(err);
        });
        if (payload) req.write(payload);
        req.end();
    });
}

contextBridge.exposeInMainWorld("api", {
    runPipeline: (audio_b64) => apiCall("POST", "/pipeline", { audio_b64 }),

    approveReport: (request_id, selected_indices, manual_override = null) =>
        apiCall("POST", "/approve", {
            request_id,
            selected_indices,
            manual_override,
        }),

    overrideReport: (source_request_id, manual_override) =>
        apiCall("POST", "/approve/override", {
            source_request_id,
            manual_override,
        }),

    volunteerReturn: (volunteer_id, returned_items) =>
        apiCall("POST", "/volunteer/return", { volunteer_id, returned_items }),

    getQueue: () => apiCall("GET", "/queue"),
    getVolunteers: () => apiCall("GET", "/volunteers"),
    getInventory: () => apiCall("GET", "/inventory"),
    getSettings: () => apiCall("GET", "/settings/frontend"),
});
