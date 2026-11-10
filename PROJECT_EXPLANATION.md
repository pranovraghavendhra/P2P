# Project Explanation
## Design and Implementation of a Simple File Transfer Application Using TCP Socket Programming

---

## 1. Project Introduction

This project implements a complete file transfer application that allows two computers on the same local network to exchange files using Python TCP socket programming. A simple web interface built with HTML, CSS, and JavaScript makes the application easy to use without any specialised software on the user's side.

The project demonstrates the following Computer Networks concepts in a practical, working system:
- The TCP/IP protocol stack
- Socket programming
- Connection-oriented communication
- Application-level protocol design
- Message framing and partial read handling
- File integrity verification using cryptographic checksums

---

## 2. Problem Statement

Two users on the same Wi-Fi network want to transfer a file from one computer to the other. They do not want to use cloud services (which require internet access and third-party servers). They need a direct, local transfer method.

**Requirements:**
- The sender selects a file and enters the receiver's IP address.
- The file is transmitted directly over the local network.
- The receiver saves the file to a chosen folder.
- The application confirms that the file arrived correctly and completely.

---

## 3. Objectives

1. Implement a TCP socket-based file transfer using Python's standard `socket` library.
2. Design a simple application-level protocol with metadata, acknowledgements, and checksums.
3. Provide a browser-based user interface served by a FastAPI web server.
4. Handle errors gracefully: connection failures, corrupted data, duplicate filenames.
5. Verify file integrity using SHA-256.

---

## 4. TCP Fundamentals

### 4.1 What is TCP?

**TCP (Transmission Control Protocol)** operates at the Transport Layer (Layer 4) of the OSI model. It provides:

| Property | Meaning |
|---|---|
| **Reliable delivery** | Lost packets are automatically retransmitted |
| **Ordered delivery** | Data arrives in the same order it was sent |
| **Error detection** | Checksums detect corrupted packets |
| **Flow control** | Prevents a fast sender from overwhelming a slow receiver |
| **Congestion control** | Reduces sending rate when the network is congested |

### 4.2 The Three-Way Handshake

Before any data is sent, TCP establishes a connection using three messages:

```
Client (Sender)          Server (Receiver)
     │                         │
     │──── SYN ───────────────►│   "I want to connect"
     │◄─── SYN-ACK ────────────│   "OK, I'm ready"
     │──── ACK ───────────────►│   "Great, let's go"
     │                         │
     │    [DATA TRANSFER]       │
     │                         │
```

After the handshake, both sides can send and receive data simultaneously.

### 4.3 Why TCP for File Transfer?

- If even one byte of a file is missing or corrupted, the file may be unusable (especially for executables, archives, and PDFs).
- TCP's automatic retransmission guarantees that every byte arrives correctly.
- UDP would be faster but offers no delivery guarantee — a lost packet would silently corrupt the file.

---

## 5. Socket Programming

A **socket** is the programming interface to the network. It is identified by:
- **IP address** — which machine
- **Port number** — which application on that machine

### 5.1 Key Python Socket Calls

```python
# Create a TCP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Sender: connect to receiver
sock.connect(("192.168.1.5", 9001))

# Receiver: bind to a port and listen
sock.bind(("0.0.0.0", 9001))
sock.listen(5)
conn, addr = sock.accept()   # blocks until a client connects

# Send data (reliably — retries internally until all bytes are sent)
sock.sendall(data_bytes)

# Receive data (may return fewer bytes than requested — see §6)
data = sock.recv(4096)
```

### 5.2 The Partial Read Problem

`sock.recv(n)` is NOT guaranteed to return exactly `n` bytes. It returns *up to* `n` bytes — whatever is currently in the OS receive buffer.

Our solution is the `recv_exact()` function in `protocol.py`:

```python
def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed")
        buf += chunk
    return buf
```

This loops until exactly `n` bytes have been accumulated.

---

## 6. Sender and Receiver Architecture

### 6.1 Sender (`tcp_sender.py`)

The sender is a simple function: `send_file(filepath, receiver_ip, receiver_port)`.

```
 send_file()
     │
     ├── Compute SHA-256 checksum of file
     ├── Open TCP socket → connect to receiver
     ├── Build metadata JSON {filename, filesize, checksum}
     ├── Send framed metadata message
     ├── Wait for ACK or REJECT
     │       └── REJECT? Return failure to caller
     ├── Open file, read in 4096-byte chunks
     │       └── sock.sendall(chunk) for each chunk
     ├── Wait for SUCCESS or FAILURE from receiver
     └── Return result dict to FastAPI
```

### 6.2 Receiver (`tcp_receiver.py`)

The `ReceiverServer` class runs a background thread that accepts connections:

```
ReceiverServer.start()
     │
     └── Create TCP server socket → bind → listen
         Background thread: accept() loop
             │
             └── For each connection: spawn _handle_connection() thread
                     │
                     ├── Read framed metadata message
                     ├── Validate filename (no path traversal, safe chars)
                     ├── Check for duplicate → make unique name
                     ├── Send ACK
                     ├── Read file chunks → write to disk → update SHA-256
                     ├── Compare received size and checksum
                     ├── Send SUCCESS or FAILURE
                     └── Fire event callback (for FastAPI to forward to browser)
```

### 6.3 FastAPI Backend (`main.py`)

The FastAPI backend bridges the browser and the TCP layer:

- **POST /send** — accepts the file upload from the browser (multipart/form-data), saves it to a temp file, calls `send_file()`, returns the result.
- **POST /receiver/start** — starts the `ReceiverServer` on the requested port.
- **POST /receiver/stop** — stops the `ReceiverServer`.
- **GET /receiver/status** — returns the server's running state and any events (incoming file, progress, success, failure). The browser polls this every 800 ms.
- **GET /history** — returns the full transfer history from `transfer_history.json`.

---

## 7. Step-by-Step File Transfer Protocol

This is the exact communication sequence implemented in this project:

```
SENDER                              RECEIVER
  │                                     │
  │── TCP Connect ─────────────────────►│
  │                                     │
  │── [4-byte length][JSON metadata] ──►│  filename, filesize, checksum
  │                                     │
  │◄── [4-byte length]["ACK"] ──────────│  or "REJECT" if invalid
  │                                     │
  │── [chunk 1: 4096 bytes] ───────────►│  write to file, update hash
  │── [chunk 2: 4096 bytes] ───────────►│
  │── [chunk N: remaining bytes] ───────►│
  │                                     │
  │◄── [4-byte length]["SUCCESS"] ──────│  or "FAILURE" if mismatch
  │                                     │
  │── TCP Close ────────────────────────│
```

### Message Framing Detail

Every control message (metadata, ACK, REJECT, SUCCESS, FAILURE) is sent as:

```
┌───────────────────┬──────────────────────────────┐
│  4 bytes (uint32) │  N bytes (payload)            │
│  big-endian       │  (JSON or ASCII token)        │
│  length = N       │                               │
└───────────────────┴──────────────────────────────┘
```

This allows the receiver to read the exact number of bytes that form one message, even if TCP delivers them in multiple `recv()` calls.

File data is **not** framed this way — it is streamed directly. The receiver knows when to stop because the declared `filesize` in the metadata tells it how many bytes to expect.

---

## 8. Explanation of Key Python Files

### `protocol.py`
- Defines `CHUNK_SIZE = 4096` — the size of each file block.
- `send_framed(sock, payload)` — prepends a 4-byte length header and sends.
- `recv_framed(sock)` — reads the 4-byte header, then reads exactly that many bytes.
- `recv_exact(sock, n)` — reads exactly n bytes, handling partial reads.
- `build_metadata(filename, filesize, checksum)` — creates JSON metadata bytes.
- `parse_metadata(raw)` — decodes JSON metadata back to a dict.

### `tcp_sender.py`
- `compute_sha256(filepath)` — reads a file in 64 KB blocks and computes SHA-256.
- `send_file(filepath, receiver_ip, receiver_port, progress_cb)` — the main transfer function. Returns a result dict with `success`, `message`, `bytes_sent`, `checksum`.

### `tcp_receiver.py`
- `_sanitize_filename(name)` — rejects filenames with path separators or illegal characters.
- `_unique_filename(folder, filename)` — returns `file_1.txt`, `file_2.txt`… if the name exists.
- `_handle_connection(conn, addr, dest_folder, event_cb)` — handles one complete transfer.
- `ReceiverServer` — manages the server socket and background thread. Methods: `start()`, `stop()`, `pop_events()`.

### `backend/main.py`
- FastAPI application with CORS middleware.
- Mounts the `frontend/` directory as static files at `/static`.
- Serves `index.html` at `/` and `how-it-works.html` at `/how-it-works`.
- `POST /send` — saves upload to temp file, calls `send_file()`, records history.
- `GET /receiver/status` — returns pending events; records received files in history.

---

## 9. Demonstration Procedure

### Setup (on the demonstrator's laptop)
```
cd P2P
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
Open Chrome → `http://localhost:8000`

### Localhost Demo (single machine)
1. Open the page. Under **Receive a File**, click **Start Receiving** (port 9001).
2. Under **Send a File**, click the file picker and choose any file.
3. Enter `127.0.0.1` as receiver IP and `9001` as port.
4. Click **Send File**.
5. Watch the progress bar fill. Check the Transfer History table.
6. Open `received_files/` folder and verify the file is there.

### Two-Computer Demo
1. Start the application on both computers.
2. Computer B: Start Receiving on port 9001.
3. Computer A: Find Computer B's IP with `ipconfig`. Enter it in the Sender form.
4. Click Send File. The file appears on Computer B.

### Demonstrate Error Cases
- With the receiver stopped, try to send → "Cannot connect" error shown.
- Send the same file twice → second copy saved as `filename_1.ext`.

---

## 10. Viva Questions and Answers

**Q1. What is TCP and why did you use it?**
TCP (Transmission Control Protocol) is a connection-oriented, reliable transport protocol. I used it because file transfer requires every byte to arrive correctly and in order. TCP's automatic retransmission guarantees this, unlike UDP which can drop packets silently.

**Q2. What is a socket?**
A socket is a software endpoint used by programs to communicate over a network. It is identified by an IP address and a port number. In Python, I create one with `socket.socket(AF_INET, SOCK_STREAM)`.

**Q3. What is the three-way handshake?**
It is how TCP establishes a connection. The client sends SYN, the server replies SYN-ACK, and the client sends ACK. After this, data transfer begins. This is handled automatically by the OS when I call `sock.connect()`.

**Q4. Why do you read the file in 4096-byte chunks?**
Two reasons: (1) large files may not fit in RAM if loaded at once; (2) TCP sends data in segments anyway, so chunking aligns with the network's natural unit of transfer. 4096 bytes is a common block size that matches OS memory pages.

**Q5. What is message framing and why is it needed?**
TCP is a stream protocol with no built-in message boundaries. A single `recv()` call may return partial data. I use length-prefix framing: I prepend a 4-byte integer (the message length) before each control message. The receiver reads 4 bytes first to learn the length, then reads exactly that many bytes.

**Q6. What is a SHA-256 checksum?**
SHA-256 is a cryptographic hash function. It takes any input and produces a fixed 256-bit (64 hex character) value. Any change to the input — even one bit — produces a completely different output. I compute it on the file before sending and after receiving. If the hashes differ, the file was corrupted.

**Q7. What does ACK mean in your protocol?**
After the sender transmits the file metadata (filename, size, checksum), the receiver validates it. If everything is acceptable, the receiver sends the byte string "ACK" (Acknowledgement) to tell the sender to proceed with the file data. If the metadata is invalid, it sends "REJECT".

**Q8. What happens if the connection drops mid-transfer?**
My `recv_exact()` function raises a `ConnectionError` when `sock.recv()` returns an empty bytes object (indicating the connection closed). The receiver catches this, deletes the incomplete file from disk, and the sender catches the exception and reports a failure to the user.

**Q9. How does the receiver prevent path traversal attacks?**
The receiver applies `os.path.basename()` to strip any directory components from the received filename, then checks the result against a regular expression that only allows letters, digits, spaces, hyphens, dots, and underscores. A filename like `../../etc/passwd` would be rejected.

**Q10. How does the browser know the receiver is getting a file?**
The browser polls the `/receiver/status` API endpoint every 800 milliseconds. The `ReceiverServer` maintains an event log. When `_handle_connection()` processes a connection, it calls `event_cb()` with events (incoming, progress, success, failure). The `/receiver/status` endpoint returns and clears these events. The browser reads them and updates the UI.

**Q11. Why does the sender upload the file to its own backend via HTTP before TCP transfer?**
Web browsers enforce security restrictions and cannot open raw TCP sockets. So the browser sends the file to its local FastAPI server using standard HTTP multipart upload. The FastAPI server, running as a normal Python process, then opens the real TCP socket connection to the remote receiver machine.

**Q12. What is the port number used in this project and how is it configured?**
The default TCP port is 9001. The user can change it in the UI. The FastAPI server runs on port 8000 (HTTP, for the browser). Port 9001 is used for the actual TCP file transfer between sender and receiver.
