"""
main.py  –  FastAPI backend
----------------------------
Exposes REST endpoints consumed by the browser frontend.

Endpoints:
    POST /send          – upload file + trigger TCP send
    POST /receiver/start – start the TCP receiver server
    POST /receiver/stop  – stop the TCP receiver server
    GET  /receiver/status – receiver status + latest events
    GET  /history        – full transfer history
    GET  /              – serve index.html
    GET  /how-it-works  – serve how-it-works.html
"""

import os
import sys
import json
import time
import shutil
import tempfile
import threading
import unicodedata
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Add backend folder to path so imports work whether we run from project root
# or from inside backend/
sys.path.insert(0, os.path.dirname(__file__))

from tcp_sender   import send_file
from tcp_receiver import ReceiverServer

# ── App setup ──────────────────────────────────────────────────────────────
app = FastAPI(title="TCP File Transfer", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent.parent          # project root
FRONTEND_DIR  = BASE_DIR / "frontend"
DEFAULT_RECV  = str(BASE_DIR / "received_files")
HISTORY_FILE  = BASE_DIR / "transfer_history.json"

# ── Serve frontend static files ────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# ── Global state ──────────────────────────────────────────────────────────
receiver = ReceiverServer()

history_lock = threading.Lock()

def _load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text("utf-8"))
        except Exception:
            return []
    return []

def _save_history(records: list):
    HISTORY_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")

def _add_history(record: dict):
    with history_lock:
        records = _load_history()
        records.append(record)
        _save_history(records)


# ── Routes: UI pages ───────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = FRONTEND_DIR / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return HTMLResponse(content=html_path.read_text("utf-8"))


@app.get("/how-it-works", response_class=HTMLResponse)
async def how_it_works():
    html_path = FRONTEND_DIR / "how-it-works.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="how-it-works.html not found")
    return HTMLResponse(content=html_path.read_text("utf-8"))


# ── Routes: Sender ─────────────────────────────────────────────────────────

@app.post("/send")
async def send_endpoint(
    file:          UploadFile = File(...),
    receiver_ip:   str        = Form(...),
    receiver_port: int        = Form(...),
):
    """
    1. Accept the file upload from the browser (multipart/form-data).
    2. Save it to a temp location on the sender's machine.
    3. Call tcp_sender.send_file() to actually transmit it via TCP.
    4. Return result to the browser.
    """
    # Basic validation
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")
    if not (1 <= receiver_port <= 65535):
        raise HTTPException(status_code=400, detail="Invalid port number.")

    # Save upload to a temp file
    suffix = Path(file.filename).suffix
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            shutil.copyfileobj(file.file, tmp)

        # Run TCP send (blocking – fine for a demo app)
        result = send_file(
            filepath      = tmp_path,
            receiver_ip   = receiver_ip,
            receiver_port = receiver_port,
        )

        # Record history
        _add_history({
            "id":        int(time.time() * 1000),
            "direction": "sent",
            "filename":  file.filename,
            "filesize":  result.get("filesize", 0),
            "status":    "success" if result["success"] else "failed",
            "message":   result.get("message", ""),
            "checksum":  result.get("checksum", ""),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "peer":      f"{receiver_ip}:{receiver_port}",
        })

        return JSONResponse(result)

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


# ── Routes: Receiver ───────────────────────────────────────────────────────

@app.post("/receiver/start")
async def start_receiver(
    port:        int = Form(default=9001),
    dest_folder: str = Form(default=""),
):
    folder = dest_folder.strip() or DEFAULT_RECV
    result = receiver.start(port=port, dest_folder=folder)
    return JSONResponse(result)


@app.post("/receiver/stop")
async def stop_receiver():
    result = receiver.stop()
    return JSONResponse(result)


@app.get("/receiver/status")
async def receiver_status():
    events = receiver.pop_events()

    # Record successful receives in history
    for ev in events:
        if ev.get("type") == "success":
            _add_history({
                "id":        int(ev["timestamp"] * 1000),
                "direction": "received",
                "filename":  ev.get("filename", "unknown"),
                "filesize":  ev.get("filesize", 0),
                "status":    "success",
                "message":   "File received successfully.",
                "checksum":  ev.get("checksum", ""),
                "timestamp": datetime.fromtimestamp(ev["timestamp"]).isoformat(timespec="seconds"),
                "peer":      ev.get("sender", "unknown"),
            })
        elif ev.get("type") in ("failure", "error"):
            _add_history({
                "id":        int(ev.get("timestamp", time.time()) * 1000),
                "direction": "received",
                "filename":  ev.get("filename", "unknown"),
                "filesize":  0,
                "status":    "failed",
                "message":   ev.get("message", "Transfer failed."),
                "checksum":  "",
                "timestamp": datetime.fromtimestamp(ev.get("timestamp", time.time())).isoformat(timespec="seconds"),
                "peer":      ev.get("sender", "unknown"),
            })

    return JSONResponse({
        "running":     receiver.is_running,
        "port":        receiver.port,
        "dest_folder": receiver.dest_folder,
        "events":      events,
    })


# ── Routes: History ────────────────────────────────────────────────────────

@app.get("/history")
async def get_history():
    with history_lock:
        records = _load_history()
    # Most recent first
    return JSONResponse(list(reversed(records)))


@app.delete("/history")
async def clear_history():
    with history_lock:
        _save_history([])
    return JSONResponse({"ok": True})
