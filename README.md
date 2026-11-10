# TCP File Transfer — README

## Project Title
Design and Implementation of a Simple File Transfer Application Using TCP Socket Programming

---

## Abstract
This project implements a peer-to-peer file transfer application that uses Python TCP socket programming to transfer files between two computers on the same local network. A lightweight FastAPI web server provides the browser-based user interface. The application demonstrates core Computer Networks concepts including TCP connections, socket programming, message framing, chunked file transfer, acknowledgements, and integrity verification using SHA-256 checksums.

---

## Objectives
- Demonstrate how TCP sockets enable reliable data transfer between two computers.
- Implement an application-level file transfer protocol with metadata, acknowledgements, and checksums.
- Provide a simple browser-based interface for sending and receiving files.
- Handle real-world scenarios such as connection failures, duplicate filenames, and file corruption detection.

---

## Features
- **Send a file** — select any file, enter the receiver's IP and port, click Send.
- **Receive files** — start a TCP listener, configure a destination folder, receive files from any sender on the LAN.
- **Transfer progress** — real-time progress bar for both sending and receiving.
- **SHA-256 integrity check** — every file is verified by checksum on arrival.
- **Duplicate file protection** — received files are never overwritten; a numbered suffix is added instead.
- **Transfer history** — persistent log of all actual transfers (sent and received), with filename, size, direction, timestamp, and status.
- **How It Works page** — educational explanation of TCP, sockets, the transfer protocol, and viva Q&A.

---

## Technologies Used

| Layer | Technology |
|---|---|
| Backend | Python 3, `socket` (stdlib), FastAPI, Uvicorn |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| File integrity | `hashlib` SHA-256 (stdlib) |
| HTTP transport | `python-multipart` (file upload) |

---

## System Architecture

```
Browser (Chrome)
    │  HTTP multipart upload (file → backend)
    │  HTTP polling (receiver events)
    ▼
FastAPI Backend (main.py)   ←→   TCP Socket Layer
    │                               │
    ├── tcp_sender.py               ├── protocol.py  (framing, metadata)
    └── tcp_receiver.py             └── ReceiverServer (background thread)
                │
                ▼
     Remote Receiver Machine
     (same app, different computer)
```

---

## Project Structure

```
P2P/
├── backend/
│   ├── main.py          FastAPI application (HTTP endpoints)
│   ├── tcp_sender.py    TCP file sender logic
│   ├── tcp_receiver.py  TCP file receiver server
│   └── protocol.py      Message framing, metadata encoding
├── frontend/
│   ├── index.html       Main transfer page
│   ├── how-it-works.html Educational explanation page
│   ├── style.css        Stylesheet
│   └── script.js        Browser-side logic
├── received_files/      Default folder for received files
├── requirements.txt     Python dependencies
├── README.md            This file
└── PROJECT_EXPLANATION.md  Academic explanation + viva Q&A
```

---

## Installation

### Requirements
- Python 3.10 or newer
- Google Chrome

### Step 1 — Install Python packages

Open a command prompt in the `P2P` folder and run:

```
pip install -r requirements.txt
```

---

## Running the Application

### Step 2 — Start the server

```
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Open Google Chrome and go to:

```
http://localhost:8000
```

> **Note:** The `--host 0.0.0.0` flag makes the server reachable from other computers on the same Wi-Fi network.

---

## How to Transfer Files

### On the Receiving Computer
1. Open Chrome → `http://localhost:8000`
2. Under **Receive a File**, optionally set a destination folder.
3. Set the listen port (default: 9001).
4. Click **Start Receiving**.
5. The status indicator turns green: "Listening on port 9001…"

### On the Sending Computer
1. Open Chrome → `http://localhost:8000`
2. Under **Send a File**, click the file picker and choose a file.
3. Enter the **Receiver's IP address** (e.g. `192.168.1.5`).
4. Enter the **Port** (must match what the receiver is listening on, e.g. `9001`).
5. Click **Send File**.
6. Watch the progress bar; a success message appears when complete.

### Finding the Receiver's IP Address
On the receiving Windows computer, open Command Prompt and run:
```
ipconfig
```
Look for **IPv4 Address** under your Wi-Fi adapter (e.g. `192.168.1.5`).

---

## Testing Between Two Computers

Both computers must be on the **same Wi-Fi or LAN**.

1. Start the application on **both** computers.
2. On Computer B (receiver): click **Start Receiving** on port 9001.
3. On Computer A (sender): enter Computer B's IP address, port 9001, select a file, click **Send File**.
4. The file appears in Computer B's destination folder.

### Testing on One Computer (localhost)
You can test using two browser tabs on the same machine:
- Tab 1 (Receiver): Start receiving on port 9001.
- Tab 2 (Sender): Enter `127.0.0.1` as the receiver IP.

---

## Windows Firewall

If the receiver is not accepting connections from other computers, Windows Firewall may be blocking the port.

To allow port 9001:

```
netsh advfirewall firewall add rule name="TCP File Transfer" dir=in action=allow protocol=TCP localport=9001
```

To remove the rule when no longer needed:

```
netsh advfirewall firewall delete rule name="TCP File Transfer"
```

---

## Test Results (Actual)

All tests were executed on a Windows machine using localhost:

| # | Test | Result |
|---|---|---|
| 1 | Small text file (1 KB) | ✓ PASS |
| 2 | Medium binary file (500 KB) + SHA-256 checksum | ✓ PASS |
| 3 | Receiver not running (connection refused) | ✓ PASS (correct error shown) |
| 4 | Duplicate filename prevention | ✓ PASS (`file.txt` → `file_1.txt`) |
| 5 | Large file (5 MB) + SHA-256 checksum | ✓ PASS |

---

## Limitations
- No encryption — transfers are in plaintext. Suitable only on a trusted LAN.
- No authentication — any machine on the network can connect to an open receiver.
- One active transfer at a time per application instance.
- The browser-to-backend upload uses HTTP (not TCP directly), because browsers cannot open raw TCP sockets.

## Future Improvements
- TLS encryption using Python's `ssl` module.
- Password protection for the receiver.
- Multiple simultaneous transfers.
- Pause and resume support.
- Folder transfer (zip before sending).
- Mobile-responsive improvements.
