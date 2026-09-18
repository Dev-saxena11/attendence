/**
 * Dynamic QR Attendance Tracker — Student Form JS
 */
(function () {
    "use strict";

    const form       = document.getElementById("attendance-form");
    const markBtn    = document.getElementById("mark-btn");
    const messageDiv = document.getElementById("form-message");

    form.addEventListener("submit", async function (e) {
        e.preventDefault();
        markBtn.disabled = true;
        markBtn.textContent = "Submitting…";
        messageDiv.style.display = "none";

        const payload = {
            session_id:    document.getElementById("session_id").value,
            token:         document.getElementById("token").value,
            name:          document.getElementById("name").value.trim(),
            roll_number:   document.getElementById("roll_number").value.trim(),
            class_section: document.getElementById("class_section_input").value.trim(),
            student_id:    document.getElementById("student_id").value.trim(),
            email:         document.getElementById("email").value.trim(),
        };

        try {
            const res  = await fetch("/api/attendance/mark", {
                method:  "POST",
                headers: { "Content-Type": "application/json" },
                body:    JSON.stringify(payload),
            });
            const data = await res.json();

            if (res.ok) {
                // Replace form with success card
                const container = form.parentElement;
                form.remove();
                container.innerHTML += `
                    <div class="card success-card">
                        <div class="success-icon">✓</div>
                        <h2>Attendance Marked!</h2>
                        <div class="success-details">
                            <div><span class="label">Name</span><br>${esc(data.name)}</div>
                            <div><span class="label">Roll Number</span><br>${esc(data.roll_number)}</div>
                            <div><span class="label">Subject</span><br>${esc(data.subject)}</div>
                            <div><span class="label">Session</span><br>${esc(data.session_id)}</div>
                            <div><span class="label">Time</span><br>${data.marked_at ? data.marked_at.substring(11, 19) : ""}</div>
                            <div><span class="label">Status</span><br>${esc(data.status)}</div>
                        </div>
                    </div>`;
            } else {
                showMessage(data.detail || data.error || "Something went wrong.", "error");
                markBtn.disabled = false;
                markBtn.textContent = "✓ Mark Attendance";
            }
        } catch (err) {
            showMessage("Something went wrong. Please try again.", "error");
            markBtn.disabled = false;
            markBtn.textContent = "✓ Mark Attendance";
            console.error(err);
        }
    });

    function showMessage(text, type) {
        messageDiv.textContent = text;
        messageDiv.className = "form-message " + type;
        messageDiv.style.display = "block";
    }

    function esc(str) {
        const d = document.createElement("div");
        d.textContent = str || "";
        return d.innerHTML;
    }
})();
