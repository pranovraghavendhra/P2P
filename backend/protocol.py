"""
protocol.py  –  Application-level File Transfer Protocol over TCP
------------------------------------------------------------------
Message framing:
    Every message (metadata, ACK, REJECT, SUCCESS, FAILURE) is sent as:
        [4-byte big-endian length][payload bytes]

    This guarantees we never confuse message boundaries, even when
    recv() returns partial data (which TCP is allowed to do).

    File data is streamed in CHUNK_SIZE blocks; the receiver knows when
    to stop because the declared file-size is transmitted in metadata.
"""

import struct
import json

# ── Constants ──────────────────────────────────────────────────────────────
CHUNK_SIZE   = 4096          # bytes per chunk during file transfer
HDR_FMT      = ">I"          # 4-byte unsigned int, big-endian
HDR_SIZE     = struct.calcsize(HDR_FMT)   # == 4

# Control tokens
ACK     = b"ACK"
REJECT  = b"REJECT"
SUCCESS = b"SUCCESS"
FAILURE = b"FAILURE"


# ── Low-level framing helpers ───────────────────────────────────────────────

def recv_exact(sock, n: int) -> bytes:
    """
    Read *exactly* n bytes from sock.
    Raises ConnectionError if the connection closes before n bytes arrive.
    This handles partial reads, which TCP can produce at any time.
    """
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed while reading data")
        buf += chunk
    return buf


def send_framed(sock, payload: bytes) -> None:
    """
    Send payload preceded by a 4-byte big-endian length header.
    """
    header = struct.pack(HDR_FMT, len(payload))
    sock.sendall(header + payload)


def recv_framed(sock) -> bytes:
    """
    Read a framed message: first read the 4-byte header to learn the
    payload size, then read exactly that many bytes.
    """
    header = recv_exact(sock, HDR_SIZE)
    payload_len = struct.unpack(HDR_FMT, header)[0]
    return recv_exact(sock, payload_len)


# ── Metadata helpers ────────────────────────────────────────────────────────

def build_metadata(filename: str, filesize: int, checksum: str) -> bytes:
    """
    Encode file metadata as a JSON framed message.
    """
    meta = {
        "filename": filename,
        "filesize": filesize,
        "checksum": checksum,   # SHA-256 hex digest
    }
    return json.dumps(meta).encode("utf-8")


def parse_metadata(raw: bytes) -> dict:
    """
    Decode the JSON metadata message.
    Returns dict with keys: filename, filesize, checksum
    """
    return json.loads(raw.decode("utf-8"))
