#!/usr/bin/env python3
"""Tiny TCP proxy that logs requests then forwards to real CPA."""
import socket, threading, sys

LISTEN_PORT = 8318
TARGET_HOST = "127.0.0.1"
TARGET_PORT = 8317

def handle(client):
    data = b""
    while True:
        chunk = client.recv(4096)
        if not chunk:
            break
        data += chunk
        if b"\r\n\r\n" in data:
            # got full headers
            break
    
    # Read body if Content-Length present
    headers_end = data.find(b"\r\n\r\n")
    header_part = data[:headers_end].decode(errors="replace")
    body_start = data[headers_end+4:]
    
    cl = 0
    for line in header_part.split("\r\n"):
        if line.lower().startswith("content-length:"):
            cl = int(line.split(":")[1].strip())
    
    while len(body_start) < cl:
        body_start += client.recv(4096)
    
    full_request = data[:headers_end+4] + body_start
    
    print("=" * 60)
    print("CODEX REQUEST CAPTURED:")
    print("=" * 60)
    print(header_part)
    print("---BODY---")
    print(body_start.decode(errors="replace")[:2000])
    print("=" * 60)
    sys.stdout.flush()
    
    # Forward to real CPA
    upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    upstream.connect((TARGET_HOST, TARGET_PORT))
    upstream.sendall(full_request)
    
    while True:
        resp = upstream.recv(4096)
        if not resp:
            break
        client.sendall(resp)
    
    upstream.close()
    client.close()

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", LISTEN_PORT))
srv.listen(5)
print(f"Sniff proxy listening on :{LISTEN_PORT}, forwarding to :{TARGET_PORT}")
sys.stdout.flush()
while True:
    c, _ = srv.accept()
    threading.Thread(target=handle, args=(c,), daemon=True).start()
