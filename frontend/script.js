/* ════════════════════════════════════════════════════════════════════════
   script.js  –  Frontend logic for TCP File Transfer app
   ════════════════════════════════════════════════════════════════════════ */

// ── Utility helpers ────────────────────────────────────────────────────────

function fmtBytes(bytes) {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString();
}

function showStatus(el, msg, type) {
  el.textContent = msg;
  el.className   = "status-msg " + type;
  el.style.display = "block";
}

function hideStatus(el) {
  el.style.display = "none";
}

// ── DOM refs ───────────────────────────────────────────────────────────────

const fileInput        = document.getElementById("file-input");
const fileDropArea     = document.getElementById("file-drop-area");
const fileDropLabel    = document.getElementById("file-drop-label");
const fileDetails      = document.getElementById("file-details");
const detailName       = document.getElementById("detail-name");
const detailSize       = document.getElementById("detail-size");
const btnClearFile     = document.getElementById("btn-clear-file");

const recvIp           = document.getElementById("recv-ip");
const recvPort         = document.getElementById("recv-port");
const btnSend          = document.getElementById("btn-send");
const sendProgressWrap = document.getElementById("send-progress-wrap");
const sendProgressFill = document.getElementById("send-progress-fill");
const sendProgressText = document.getElementById("send-progress-text");
const sendProgressPct  = document.getElementById("send-progress-pct");
const sendStatus       = document.getElementById("send-status");

const destFolder       = document.getElementById("dest-folder");
const listenPort       = document.getElementById("listen-port");
const btnStartRecv     = document.getElementById("btn-start-recv");
const btnStopRecv      = document.getElementById("btn-stop-recv");
const statusDot        = document.getElementById("status-dot");
const listenStatusText = document.getElementById("listen-status-text");
const incomingInfo     = document.getElementById("incoming-info");
const incomingFilename = document.getElementById("incoming-filename");
const incomingFilesize = document.getElementById("incoming-filesize");
const incomingSender   = document.getElementById("incoming-sender");
const recvProgressWrap = document.getElementById("recv-progress-wrap");
const recvProgressFill = document.getElementById("recv-progress-fill");
const recvProgressText = document.getElementById("recv-progress-text");
const recvProgressPct  = document.getElementById("recv-progress-pct");
const recvStatus       = document.getElementById("recv-status");

const historyEmpty     = document.getElementById("history-empty");
const historyTable     = document.getElementById("history-table");
const historyTbody     = document.getElementById("history-tbody");
const btnClearHistory  = document.getElementById("btn-clear-history");

// ── File picker ────────────────────────────────────────────────────────────

let selectedFile = null;

function showFileDetails(file) {
  selectedFile = file;
  detailName.textContent  = file.name;
  detailSize.textContent  = fmtBytes(file.size);
  fileDetails.style.display   = "flex";
  fileDropLabel.style.display = "none";
}

function clearFileSelection() {
  selectedFile = null;
  fileInput.value = "";
  fileDetails.style.display   = "none";
  fileDropLabel.style.display = "flex";
}

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) showFileDetails(fileInput.files[0]);
});

btnClearFile.addEventListener("click", clearFileSelection);

// Drag-and-drop
fileDropArea.addEventListener("dragover", e => {
  e.preventDefault();
  fileDropArea.classList.add("drag-over");
});
fileDropArea.addEventListener("dragleave", () => fileDropArea.classList.remove("drag-over"));
fileDropArea.addEventListener("drop", e => {
  e.preventDefault();
  fileDropArea.classList.remove("drag-over");
  if (e.dataTransfer.files[0]) showFileDetails(e.dataTransfer.files[0]);
});

// ── Send file ──────────────────────────────────────────────────────────────

btnSend.addEventListener("click", async () => {
  hideStatus(sendStatus);

  if (!selectedFile) {
    showStatus(sendStatus, "Please select a file first.", "error"); return;
  }
  const ip   = recvIp.value.trim();
  const port = parseInt(recvPort.value, 10);
  if (!ip)            { showStatus(sendStatus, "Enter the receiver's IP address.", "error"); return; }
  if (!port || port < 1 || port > 65535) {
    showStatus(sendStatus, "Enter a valid port number (1–65535).", "error"); return;
  }

  // Disable UI during transfer
  btnSend.disabled = true;
  sendProgressWrap.style.display = "flex";
  sendProgressFill.style.width   = "0%";
  sendProgressText.textContent   = "Uploading file to local backend…";
  sendProgressPct.textContent    = "0%";

  const formData = new FormData();
  formData.append("file",          selectedFile);
  formData.append("receiver_ip",   ip);
  formData.append("receiver_port", port);

  // We simulate upload progress via a fake local animation,
  // then show TCP transfer progress once the backend responds.
  // (XHR with upload.onprogress would handle the multipart upload phase)
  let uploadDone = false;
  const xhr = new XMLHttpRequest();

  xhr.upload.addEventListener("progress", e => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 40);   // 0→40% = upload
      sendProgressFill.style.width = pct + "%";
      sendProgressPct.textContent  = pct + "%";
    }
  });

  xhr.addEventListener("load", () => {
    try {
      const result = JSON.parse(xhr.responseText);

      sendProgressFill.style.width = "100%";
      sendProgressPct.textContent  = "100%";

      if (result.success) {
        sendProgressText.textContent = "Transfer complete!";
        showStatus(sendStatus,
          `✓  ${result.filename} (${fmtBytes(result.filesize)}) sent successfully.`,
          "success"
        );
        clearFileSelection();
        loadHistory();
      } else {
        sendProgressFill.style.backgroundColor = "var(--error)";
        sendProgressText.textContent = "Transfer failed.";
        showStatus(sendStatus, "✗  " + (result.message || "Transfer failed."), "error");
      }
    } catch (e) {
      showStatus(sendStatus, "Unexpected server response. Check console.", "error");
    }
    btnSend.disabled = false;
  });

  xhr.addEventListener("error", () => {
    showStatus(sendStatus, "Cannot reach the backend. Is the server running?", "error");
    btnSend.disabled = false;
  });

  // Start at 40% once upload is done; animate to 90% while TCP transfer runs
  xhr.upload.addEventListener("load", () => {
    sendProgressText.textContent = "Sending over TCP…";
    sendProgressFill.style.width = "50%";
    sendProgressPct.textContent  = "50%";
    // Animate slowly to 90% — actual result will snap to 100%
    let cur = 50;
    const iv = setInterval(() => {
      cur = Math.min(cur + 1, 90);
      sendProgressFill.style.width = cur + "%";
      sendProgressPct.textContent  = cur + "%";
      if (cur >= 90) clearInterval(iv);
    }, 200);
    xhr._progressInterval = iv;
  });

  xhr.open("POST", "/send");
  xhr.send(formData);
});

// ── Receiver ───────────────────────────────────────────────────────────────

let recvPolling = null;

btnStartRecv.addEventListener("click", async () => {
  hideStatus(recvStatus);
  const port   = parseInt(listenPort.value, 10) || 9001;
  const folder = destFolder.value.trim();

  const form = new FormData();
  form.append("port",        port);
  form.append("dest_folder", folder);

  try {
    const res  = await fetch("/receiver/start", { method: "POST", body: form });
    const data = await res.json();
    if (data.ok) {
      setReceiverRunning(true, port);
      startPolling();
    } else {
      showStatus(recvStatus, data.message, "error");
    }
  } catch (e) {
    showStatus(recvStatus, "Cannot reach backend. Is the server running?", "error");
  }
});

btnStopRecv.addEventListener("click", async () => {
  try {
    const res  = await fetch("/receiver/stop", { method: "POST" });
    const data = await res.json();
    setReceiverRunning(false);
    stopPolling();
    showStatus(recvStatus, "Receiver stopped.", "info");
  } catch (e) {
    showStatus(recvStatus, "Error stopping receiver.", "error");
  }
});

function setReceiverRunning(running, port) {
  btnStartRecv.disabled = running;
  btnStopRecv.disabled  = !running;
  listenPort.disabled   = running;
  destFolder.disabled   = running;
  statusDot.className   = "status-dot" + (running ? " active" : "");
  listenStatusText.textContent = running
    ? `Listening on port ${port}…`
    : "Not listening";
  if (!running) {
    incomingInfo.style.display   = "none";
    recvProgressWrap.style.display = "none";
  }
}

// ── Polling for receiver events ────────────────────────────────────────────

let currentRecvFile = { name: "", size: 0 };

function startPolling() {
  if (recvPolling) return;
  recvPolling = setInterval(pollReceiverStatus, 800);
}

function stopPolling() {
  clearInterval(recvPolling);
  recvPolling = null;
}

async function pollReceiverStatus() {
  try {
    const res    = await fetch("/receiver/status");
    const data   = await res.json();

    if (!data.running) {
      setReceiverRunning(false);
      stopPolling();
      return;
    }

    for (const ev of (data.events || [])) {
      handleRecvEvent(ev);
    }
  } catch (e) {
    // Silently ignore polling errors (server might be briefly busy)
  }
}

function handleRecvEvent(ev) {
  switch (ev.type) {

    case "incoming":
      currentRecvFile = { name: ev.filename, size: ev.filesize };
      incomingFilename.textContent = ev.filename;
      incomingFilesize.textContent = fmtBytes(ev.filesize);
      incomingSender.textContent   = ev.sender;
      incomingInfo.style.display   = "flex";
      recvProgressWrap.style.display = "flex";
      recvProgressFill.style.width   = "0%";
      recvProgressPct.textContent    = "0%";
      recvProgressFill.style.backgroundColor = "var(--accent)";
      recvProgressText.textContent   = "Receiving…";
      hideStatus(recvStatus);
      break;

    case "progress":
      if (ev.filesize > 0) {
        const pct = Math.round((ev.bytes_received / ev.filesize) * 100);
        recvProgressFill.style.width = pct + "%";
        recvProgressPct.textContent  = pct + "%";
        recvProgressText.textContent = `Receiving ${ev.filename}…`;
      }
      break;

    case "success":
      recvProgressFill.style.width = "100%";
      recvProgressPct.textContent  = "100%";
      recvProgressText.textContent = "Complete!";
      showStatus(recvStatus,
        `✓  Saved: ${ev.filename} (${fmtBytes(ev.filesize)})`,
        "success"
      );
      loadHistory();
      break;

    case "failure":
    case "error":
      recvProgressFill.style.backgroundColor = "var(--error)";
      showStatus(recvStatus, "✗  " + (ev.message || "Transfer failed."), "error");
      loadHistory();
      break;
  }
}

// ── Transfer history ───────────────────────────────────────────────────────

async function loadHistory() {
  try {
    const res     = await fetch("/history");
    const records = await res.json();

    if (!records.length) {
      historyEmpty.style.display = "block";
      historyTable.style.display = "none";
      return;
    }

    historyEmpty.style.display = "none";
    historyTable.style.display = "table";

    historyTbody.innerHTML = records.map(r => `
      <tr>
        <td title="${r.filename}">${truncate(r.filename, 35)}</td>
        <td>${fmtBytes(r.filesize)}</td>
        <td><span class="badge ${r.direction === 'sent' ? 'badge-sent' : 'badge-recv'}">
          ${r.direction === 'sent' ? '↑ Sent' : '↓ Received'}
        </span></td>
        <td>${fmtDate(r.timestamp)}</td>
        <td><span class="badge ${r.status === 'success' ? 'badge-success' : 'badge-error'}">
          ${r.status === 'success' ? '✓ Success' : '✗ Failed'}
        </span></td>
      </tr>
    `).join("");
  } catch (e) {
    // ignore
  }
}

function truncate(str, n) {
  return str.length > n ? str.slice(0, n - 1) + "…" : str;
}

btnClearHistory.addEventListener("click", async () => {
  await fetch("/history", { method: "DELETE" });
  loadHistory();
});

// ── Initialise ─────────────────────────────────────────────────────────────

(async function init() {
  // Restore receiver running state if page was refreshed
  try {
    const res  = await fetch("/receiver/status");
    const data = await res.json();
    if (data.running) {
      setReceiverRunning(true, data.port);
      startPolling();
    }
  } catch (e) {}

  loadHistory();
})();
