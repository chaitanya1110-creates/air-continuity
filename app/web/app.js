// AirContinuity iPhone Client Logic
let socket = null;
let currentPcClipboard = "";

// DOM Elements
const headerStatusDot = document.getElementById("headerStatusDot");
const headerStatusText = document.getElementById("headerStatusText");
const pcHostname = document.getElementById("pcHostname");

const mirrorStatusLabel = document.getElementById("mirrorStatusLabel");
const mirrorPulse = document.getElementById("mirrorPulse");

const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const uploadProgressContainer = document.getElementById("uploadProgressContainer");
const uploadProgressBar = document.getElementById("uploadProgressBar");
const uploadProgressText = document.getElementById("uploadProgressText");
const pcFilesList = document.getElementById("pcFilesList");

const pcClipboardPreview = document.getElementById("pcClipboardPreview");
const btnCopyFromPC = document.getElementById("btnCopyFromPC");
const iphoneClipInput = document.getElementById("iphoneClipInput");
const btnSendToPC = document.getElementById("btnSendToPC");

// Initialize Tab Navigation
document.querySelectorAll(".tab-item").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-item").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

        btn.classList.add("active");
        const targetId = btn.getAttribute("data-tab");
        const targetPane = document.getElementById(targetId);
        if (targetPane) targetPane.classList.add("active");
    });
});

// Setup WebSocket Connection
function initWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        headerStatusDot.classList.remove("offline");
        headerStatusText.textContent = "Connected to Windows";
        fetchStatus();
        fetchPCFiles();
    };

    socket.onclose = () => {
        headerStatusDot.classList.add("offline");
        headerStatusText.textContent = "Reconnecting...";
        setTimeout(initWebSocket, 2000);
    };

    socket.onerror = (err) => {
        console.error("WS error:", err);
    };

    socket.onmessage = async (event) => {
        try {
            const data = jsonParse(event.data);
            if (!data) return;

            if (data.type === "clipboard_update") {
                currentPcClipboard = data.text;
                pcClipboardPreview.textContent = data.text;
            } else if (data.type === "file_received" || data.type === "file_ready") {
                fetchPCFiles();
            }
        } catch (e) {
            console.error("Error processing incoming WS message:", e);
        }
    };
}

function jsonParse(str) {
    try { return JSON.parse(str); } catch { return null; }
}

async function fetchStatus() {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();
        if (data.device) {
            pcHostname.textContent = data.device;
            // Update the AirPlay server name in the instructions
            const nameEl = document.getElementById("airplayServerName");
            if (nameEl) {
                nameEl.textContent = "AirContinuity-" + data.device;
            }
        }
        // Update mirror status based on server-reported state
        if (data.screen_active) {
            mirrorStatusLabel.textContent = "🟢 Screen Mirroring Active";
            mirrorPulse.style.background = "#30D158";
        }
    } catch {}
}
// Periodically refresh status to keep mirror indicator current
setInterval(fetchStatus, 5000);

// File Transfer / AirDrop
dropZone.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
        uploadFiles(e.target.files);
    }
});

function uploadFiles(files) {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append("files", files[i]);
    }

    uploadProgressContainer.style.display = "block";
    uploadProgressBar.style.width = "0%";
    uploadProgressText.textContent = `Uploading ${files.length} file(s)...`;

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload", true);

    xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
            const percent = Math.round((e.loaded / e.total) * 100);
            uploadProgressBar.style.width = percent + "%";
            uploadProgressText.textContent = `Uploading... ${percent}%`;
        }
    };

    xhr.onload = () => {
        uploadProgressText.textContent = "Transfer Complete!";
        setTimeout(() => {
            uploadProgressContainer.style.display = "none";
        }, 2000);
    };

    xhr.onerror = () => {
        uploadProgressText.textContent = "Upload failed. Check Wi-Fi connection.";
    };

    xhr.send(formData);
}

async function fetchPCFiles() {
    try {
        const res = await fetch("/api/files");
        const data = await res.json();
        renderPCFiles(data.files || []);
    } catch {}
}

function renderPCFiles(files) {
    if (!files.length) {
        pcFilesList.innerHTML = '<div class="empty-state">No files shared from PC yet</div>';
        return;
    }
    pcFilesList.innerHTML = "";
    files.forEach(f => {
        const div = document.createElement("div");
        div.className = "file-item";
        div.innerHTML = `
            <div>
                <div class="file-name">${escapeHtml(f.name)}</div>
                <div class="file-size">${escapeHtml(f.size)}</div>
            </div>
            <a href="/api/download/${f.id}" class="btn btn-primary" style="padding: 6px 12px; font-size: 13px; text-decoration: none;" download>
                Save
            </a>
        `;
        pcFilesList.appendChild(div);
    });
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// Universal Clipboard
btnCopyFromPC.addEventListener("click", async () => {
    if (!currentPcClipboard) return;
    try {
        await navigator.clipboard.writeText(currentPcClipboard);
        btnCopyFromPC.textContent = "Copied to iPhone!";
        setTimeout(() => { btnCopyFromPC.textContent = "Copy to iPhone Clipboard"; }, 1500);
    } catch {
        alert("Clipboard permission needed in Safari");
    }
});

btnSendToPC.addEventListener("click", () => {
    const text = iphoneClipInput.value.trim();
    if (!text) return;

    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            type: "clipboard_update",
            text: text
        }));
    }

    fetch("/api/clipboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text })
    });

    btnSendToPC.textContent = "Pushed to Windows!";
    setTimeout(() => {
        btnSendToPC.textContent = "Push to Windows Clipboard";
        iphoneClipInput.value = "";
    }, 1500);
});

// Periodic manifest refresh
setInterval(fetchPCFiles, 6000);

// Kickoff
initWebSocket();
