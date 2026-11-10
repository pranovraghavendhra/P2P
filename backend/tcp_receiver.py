"""
tcp_receiver.py  –  TCP File Receiver
---------------------------------------
Runs a TCP server that:
  1. Accepts one connection at a time.
  2. Reads the file metadata (filename, filesize, checksum).
  3. Validates the metadata and checks for duplicate filenames.
  4. Sends ACK or REJECT.
  5. Reads file data in chunks and writes to destination folder.
  6. Verifies received size and SHA-256 checksum.
  7. Sends SUCCESS or FAILURE.
  8. Closes the connection.

The server runs in a background thread so FastAPI stays responsive.
"""

import os
import re
import socket
import hashlib
import threading
import time
from typing import Callable

from protocol import (
    CHUNK_SIZE, ACK, REJECT, SUCCESS, FAILURE,
    send_framed, recv_framed,
    parse_metadata, recv_exact,
)

# ── Filename safety ─────────────────────────────────────────────────────────
SAFE_FILENAME_RE = re.compile(r'^[\w\-. ]+$')   # allow letters, digits, dash, dot, space, underscore

def _sanitize_filename(name: str) -> str | None:
    """
    Return a safe filename or None if the name is unacceptable.
    Strips path components and validates characters.
    """
    # Strip any directory part an attacker might inject
    base = os.path.basename(name).strip()
    if not base or not SAFE_FILENAME_RE.match(base):
        return None
    return base


def _unique_filename(folder: str, filename: str) -> str:
    """
    If 'filename' already exists in 'folder', append _1, _2 … until unique.
    """
    base, ext = os.path.splitext(filename)
    candidate = filename
    counter   = 1
    while os.path.exists(os.path.join(folder, candidate)):
        candidate = f"{base}_{counter}{ext}"
        counter  += 1
    return candidate


def _compute_sha256_from_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(65536)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


# ── Per-connection handler ───────────────────────────────────────────────────

def _handle_connection(
    conn: socket.socket,
    addr,
    dest_folder: str,
    event_cb: Callable[[dict], None],
) -> None:
    """
    Handle one incoming TCP connection end-to-end.
    Calls event_cb(event_dict) to report progress / results.
    """
    conn.settimeout(30)
    sender_ip = addr[0]

    try:
        # ── Step 1: Read metadata ─────────────────────────────────────────
        try:
            raw_meta = recv_framed(conn)
        except Exception as e:
            event_cb({"type": "error", "message": f"Failed to read metadata: {e}", "sender": sender_ip})
            return

        try:
            meta     = parse_metadata(raw_meta)
            filename = meta["filename"]
            filesize = int(meta["filesize"])
            checksum = meta["checksum"]
        except Exception as e:
            send_framed(conn, REJECT)
            event_cb({"type": "error", "message": f"Invalid metadata: {e}", "sender": sender_ip})
            return

        # ── Step 2: Validate filename ─────────────────────────────────────
        safe_name = _sanitize_filename(filename)
        if not safe_name:
            send_framed(conn, REJECT)
            event_cb({"type": "error", "message": f"Rejected unsafe filename: {filename!r}", "sender": sender_ip})
            return

        # ── Step 3: Ensure destination folder exists ──────────────────────
        os.makedirs(dest_folder, exist_ok=True)

        # ── Step 4: Resolve unique filename (no accidental overwrite) ─────
        save_name = _unique_filename(dest_folder, safe_name)
        save_path = os.path.join(dest_folder, save_name)

        # ── Step 5: Send ACK ──────────────────────────────────────────────
        send_framed(conn, ACK)
        event_cb({
            "type": "incoming",
            "filename": save_name,
            "filesize": filesize,
            "sender":   sender_ip,
        })

        # ── Step 6: Receive file data ─────────────────────────────────────
        conn.settimeout(60)
        bytes_received = 0
        h = hashlib.sha256()

        with open(save_path, "wb") as f:
            while bytes_received < filesize:
                to_read = min(CHUNK_SIZE, filesize - bytes_received)
                try:
                    chunk = recv_exact(conn, to_read)
                except Exception as e:
                    event_cb({
                        "type": "error",
                        "message": f"Connection lost at {bytes_received}/{filesize} bytes: {e}",
                        "filename": save_name,
                        "sender": sender_ip,
                    })
                    # Remove incomplete file
                    try:
                        os.remove(save_path)
                    except OSError:
                        pass
                    send_framed(conn, FAILURE)
                    return

                f.write(chunk)
                h.update(chunk)
                bytes_received += len(chunk)

                event_cb({
                    "type": "progress",
                    "filename": save_name,
                    "bytes_received": bytes_received,
                    "filesize": filesize,
                    "sender": sender_ip,
                })

        # ── Step 7: Verify size and checksum ──────────────────────────────
        conn.settimeout(30)

        if bytes_received != filesize:
            send_framed(conn, FAILURE)
            os.remove(save_path)
            event_cb({
                "type": "failure",
                "message": f"Size mismatch: expected {filesize}, got {bytes_received}",
                "filename": save_name,
                "sender": sender_ip,
            })
            return

        received_checksum = h.hexdigest()
        if received_checksum != checksum:
            send_framed(conn, FAILURE)
            os.remove(save_path)
            event_cb({
                "type": "failure",
                "message": f"Checksum mismatch — file may be corrupted.",
                "filename": save_name,
                "sender": sender_ip,
            })
            return

        # ── Step 8: Send SUCCESS ──────────────────────────────────────────
        send_framed(conn, SUCCESS)
        event_cb({
            "type": "success",
            "filename": save_name,
            "filesize": filesize,
            "checksum": received_checksum,
            "save_path": save_path,
            "sender": sender_ip,
        })

    except Exception as e:
        event_cb({"type": "error", "message": f"Unhandled error: {e}", "sender": sender_ip})
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── ReceiverServer ────────────────────────────────────────────────────────────

class ReceiverServer:
    """
    A TCP server that runs in a background thread.
    Start / stop it from the FastAPI application.
    """

    def __init__(self):
        self._thread:      threading.Thread | None = None
        self._server_sock: socket.socket | None    = None
        self._stop_event   = threading.Event()
        self.is_running    = False
        self.port:         int    = 0
        self.dest_folder:  str    = ""
        self.last_event:   dict   = {}
        self._event_log:   list   = []   # for the frontend to poll

    def start(self, port: int, dest_folder: str) -> dict:
        if self.is_running:
            return {"ok": False, "message": "Already running."}

        self.port        = port
        self.dest_folder = dest_folder
        self._stop_event.clear()

        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.bind(("0.0.0.0", port))
            self._server_sock.listen(5)
            self._server_sock.settimeout(1.0)   # check stop_event every second
        except OSError as e:
            return {"ok": False, "message": f"Cannot bind to port {port}: {e}"}

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.is_running = True
        return {"ok": True, "message": f"Listening on port {port}."}

    def stop(self) -> dict:
        if not self.is_running:
            return {"ok": False, "message": "Not running."}
        self._stop_event.set()
        try:
            self._server_sock.close()
        except Exception:
            pass
        self._thread.join(timeout=3)
        self.is_running = False
        return {"ok": True, "message": "Receiver stopped."}

    def _run(self):
        while not self._stop_event.is_set():
            try:
                conn, addr = self._server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break   # server socket closed → stop

            t = threading.Thread(
                target=_handle_connection,
                args=(conn, addr, self.dest_folder, self._on_event),
                daemon=True,
            )
            t.start()

    def _on_event(self, event: dict):
        event["timestamp"] = time.time()
        self.last_event = event
        self._event_log.append(event)
        # Keep log bounded
        if len(self._event_log) > 200:
            self._event_log = self._event_log[-100:]

    def pop_events(self) -> list:
        """Return and clear all pending events."""
        events = self._event_log[:]
        self._event_log.clear()
        return events
