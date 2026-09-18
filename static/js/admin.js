/**
 * Dynamic QR Attendance Tracker — Admin Dashboard JS
 */
(function () {
    "use strict";

    /* ── DOM refs ─────────────────────────────────────────────── */
    const createPanel    = document.getElementById("create-panel");
    const sessionPanel   = document.getElementById("session-panel");
    const createForm     = document.getElementById("create-form");
    const startBtn       = document.getElementById("start-btn");

    const dashSubject    = document.getElementById("dash-subject");
    const dashClass      = document.getElementById("dash-class");
    const dashTopic      = document.getElementById("dash-topic");
    const dashSessionId  = document.getElementById("dash-session-id");
    const qrImage        = document.getElementById("qr-image");
    const countdownEl    = document.getElementById("countdown");
    const timerCircle    = document.getElementById("timer-circle");
    const attendanceCount = document.getElementById("attendance-count");
    const attendanceBody = document.getElementById("attendance-body");
    const stopBtn        = document.getElementById("stop-btn");
    const exportBtn      = document.getElementById("export-btn");

    /* ── State ────────────────────────────────────────────────── */
    let currentSessionId = null;
    let tokenLifetime    = 10;  // seconds, updated from server
    let remaining        = 0;
    let countdownTimer   = null;
    let pollTimer        = null;

    const CIRCUMFERENCE  = 2 * Math.PI * 54; // matches SVG circle r=54

    /* ── Load past sessions on page load ──────────────────────── */
    loadPastSessions();

    /* ── Create session ───────────────────────────────────────── */
    createForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        startBtn.disabled = true;
        startBtn.textContent = "Starting…";

        const payload = {
            class_section: document.getElementById("class_section").value.trim(),
            subject:       document.getElementById("subject").value.trim(),
            topic:         document.getElementById("topic").value.trim(),
        };

        try {
            const res  = await fetch("/api/sessions/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) { alert(data.error || "Failed to start session"); return; }

            currentSessionId = data.session_id;
            tokenLifetime    = data.token.lifetime || 10;

            dashSubject.textContent   = data.subject;
            dashClass.textContent     = data.class_section;
            dashTopic.textContent     = data.topic || "";
            dashSessionId.textContent = data.session_id;

            showQR(data.qr_image, data.token);
            switchToSession();
            startPolling();
        } catch (err) {
            alert("Something went wrong. Please try again.");
            console.error(err);
        } finally {
            startBtn.disabled = false;
            startBtn.innerHTML = '<span class="btn-icon">▶</span> Start Attendance';
        }
    });

    /* ── Stop session ─────────────────────────────────────────── */
    stopBtn.addEventListener("click", async function () {
        if (!confirm("Stop this attendance session? No more students will be able to mark attendance.")) return;
        stopBtn.disabled = true;
        try {
            const sessionToExport = currentSessionId;
            await fetch(`/api/sessions/${currentSessionId}/stop`, { method: "POST" });
            clearInterval(countdownTimer);
            clearInterval(pollTimer);

            // Auto-download CSV with attendance data
            window.open(`/api/sessions/${sessionToExport}/export`, "_blank");

            alert("Attendance session stopped. CSV downloaded.");
            switchToCreate();
            loadPastSessions();
        } catch (err) {
            alert("Failed to stop session.");
            console.error(err);
        } finally {
            stopBtn.disabled = false;
        }
    });

    /* ── Export CSV ────────────────────────────────────────────── */
    exportBtn.addEventListener("click", function () {
        if (!currentSessionId) return;
        window.open(`/api/sessions/${currentSessionId}/export`, "_blank");
    });

    /* ── QR display & countdown ───────────────────────────────── */
    function showQR(imageDataUri, tokenInfo) {
        qrImage.src = imageDataUri;
        remaining = tokenInfo.lifetime || tokenLifetime;
        startCountdown();
    }

    function startCountdown() {
        clearInterval(countdownTimer);
        updateTimerUI(remaining);

        countdownTimer = setInterval(async () => {
            remaining--;
            if (remaining <= 0) {
                clearInterval(countdownTimer);
                await refreshQR();
            } else {
                updateTimerUI(remaining);
            }
        }, 1000);
    }

    function updateTimerUI(secs) {
        countdownEl.textContent = secs;
        const fraction = secs / tokenLifetime;
        const offset = CIRCUMFERENCE * (1 - fraction);
        timerCircle.style.strokeDashoffset = offset;

        timerCircle.classList.remove("warning", "danger");
        if (secs <= 3)      timerCircle.classList.add("danger");
        else if (secs <= 5) timerCircle.classList.add("warning");
    }

    async function refreshQR() {
        try {
            const res  = await fetch(`/api/sessions/${currentSessionId}/current-token`);
            const data = await res.json();
            if (!res.ok) {
                // session probably stopped elsewhere
                clearInterval(pollTimer);
                alert(data.error || "Session ended.");
                switchToCreate();
                loadPastSessions();
                return;
            }
            showQR(data.qr_image, data.token);
        } catch (err) {
            console.error("Failed to refresh QR:", err);
        }
    }

    /* ── Attendance polling ───────────────────────────────────── */
    function startPolling() {
        fetchAttendance(); // immediate
        pollTimer = setInterval(fetchAttendance, 3000);
    }

    async function fetchAttendance() {
        if (!currentSessionId) return;
        try {
            const res  = await fetch(`/api/sessions/${currentSessionId}/attendance`);
            const data = await res.json();
            if (!res.ok) return;

            attendanceCount.textContent = data.count;

            if (data.records.length === 0) {
                attendanceBody.innerHTML = '<tr><td colspan="4" class="muted">No attendance yet</td></tr>';
                return;
            }

            // show most recent first, limit to 50
            const rows = data.records.slice().reverse().slice(0, 50);
            attendanceBody.innerHTML = rows.map(r => {
                const time = r.marked_at ? r.marked_at.substring(11, 16) : "";
                return `<tr>
                    <td>${esc(r.roll_number)}</td>
                    <td>${esc(r.name)}</td>
                    <td>${esc(r.student_id)}</td>
                    <td>${time}</td>
                </tr>`;
            }).join("");
        } catch (err) {
            console.error("Polling error:", err);
        }
    }

    /* ── Past sessions ────────────────────────────────────────── */
    async function loadPastSessions() {
        try {
            const res  = await fetch("/api/sessions");
            const data = await res.json();
            const el   = document.getElementById("past-sessions-list");

            if (data.length === 0) {
                el.innerHTML = '<p class="muted">No sessions yet</p>';
                return;
            }

            el.innerHTML = data.slice(0, 20).map(s => {
                const dateStr = s.started_at ? s.started_at.substring(0, 16).replace("T", " ") : "";
                const badge   = s.status === "ACTIVE"
                    ? '<span class="past-badge active">Active</span>'
                    : '<span class="past-badge closed">Closed</span>';
                return `<div class="past-item">
                    <div class="past-info">
                        <strong>${esc(s.subject)} — ${esc(s.class_section)}</strong>
                        <span>${esc(s.id)} · ${dateStr}</span>
                    </div>
                    <div class="past-actions" style="display: flex; gap: 10px; align-items: center;">
                        ${badge}
                        <button class="delete-btn" data-id="${esc(s.id)}" style="background:none; border:none; color:#f43f5e; cursor:pointer; padding:4px;" title="Delete Session">
                            <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                            </svg>
                        </button>
                    </div>
                </div>`;
            }).join("");

            // Attach delete handlers
            el.querySelectorAll(".delete-btn").forEach(btn => {
                btn.addEventListener("click", async (e) => {
                    const id = e.currentTarget.getAttribute("data-id");
                    if (confirm(`Are you sure you want to permanently delete session ${id}? This will remove all associated attendance data.`)) {
                        try {
                            await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
                            loadPastSessions();
                        } catch(err) {
                            alert("Failed to delete session.");
                            console.error(err);
                        }
                    }
                });
            });

        } catch (err) {
            console.error(err);
        }
    }

    /* ── Panel switching ──────────────────────────────────────── */
    function switchToSession() {
        createPanel.style.display  = "none";
        sessionPanel.style.display = "block";
    }

    function switchToCreate() {
        sessionPanel.style.display = "none";
        createPanel.style.display  = "block";
        currentSessionId = null;
    }

    /* ── Utility ──────────────────────────────────────────────── */
    function esc(str) {
        const d = document.createElement("div");
        d.textContent = str;
        return d.innerHTML;
    }
})();
