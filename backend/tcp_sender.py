"""
tcp_sender.py  –  TCP File Sender
----------------------------------
Opens a TCP connection to (receiver_ip, receiver_port),
sends file metadata, waits for ACK, streams the file in
CHUNK_SIZE blocks, then waits for the final SUCCESS/FAILURE reply.

Progress is reported via a callback so the FastAPI layer can
stream real-time updates to the browser.
"""

import os
import socket
import hashlib
from typing import Callable

from protocol import (
    CHUNK_SIZE, ACK, REJECT, SUCCESS, FAILURE,
    send_framed, recv_framed,
    build_metadata,
)


def compute_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            block = f.read(65536)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def send_file(
    filepath: str,
    receiver_ip: str,
    receiver_port: int,
    progress_cb: Callable[[int, int], None] = None,
) -> dict:
    """
    Transfer a file to (receiver_ip, receiver_port).

    Args:
        filepath      – absolute path to the file on the sender's machine
        receiver_ip   – IP address of the receiving machine
        receiver_port – TCP port the receiver is listening on
        progress_cb   – optional callback(bytes_sent, total_bytes)

    Returns a result dict:
        {
          "success": bool,
          "message": str,
          "bytes_sent": int,
          "checksum": str,
        }
    """
    filename  = os.path.basename(filepath)
    filesize  = os.path.getsize(filepath)
    checksum  = compute_sha256(filepath)

    result = {
        "success": False,
        "message": "",
        "bytes_sent": 0,
        "checksum": checksum,
        "filename": filename,
        "filesize": filesize,
    }

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)          # 30-second timeout for connect / control msgs

    try:
        # ── Step 1: Establish TCP connection ──────────────────────────────
        try:
            sock.connect((receiver_ip, receiver_port))
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            result["message"] = f"Cannot connect to {receiver_ip}:{receiver_port} — {e}"
            return result

        # ── Step 2: Send file metadata ────────────────────────────────────
        meta_bytes = build_metadata(filename, filesize, checksum)
        send_framed(sock, meta_bytes)

        # ── Step 3: Wait for receiver ACK or REJECT ───────────────────────
        response = recv_framed(sock)
        if response == REJECT:
            result["message"] = "Receiver rejected the transfer (file may already exist or metadata is invalid)."
            return result
        if response != ACK:
            result["message"] = f"Unexpected response from receiver: {response!r}"
            return result

        # ── Step 4: Stream file in CHUNK_SIZE blocks ──────────────────────
        sock.settimeout(60)      # longer timeout during data transfer
        bytes_sent = 0
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                sock.sendall(chunk)
                bytes_sent += len(chunk)
                if progress_cb:
                    progress_cb(bytes_sent, filesize)

        result["bytes_sent"] = bytes_sent

        # ── Step 5: Wait for final SUCCESS / FAILURE ──────────────────────
        sock.settimeout(30)
        final = recv_framed(sock)
        if final == SUCCESS:
            result["success"] = True
            result["message"] = "File transferred successfully."
        else:
            result["message"] = f"Receiver reported failure: {final.decode(errors='replace')}"

    except ConnectionError as e:
        result["message"] = f"Connection lost during transfer: {e}"
    except Exception as e:
        result["message"] = f"Unexpected error: {e}"
    finally:
        try:
            sock.close()
        except Exception:
            pass

    return result
