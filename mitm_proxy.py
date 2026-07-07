#!/usr/bin/env python3
"""MITM reverse proxy: captures Codex requests, forwards to CPA, logs everything."""
import http.server
import http.client
import json
import sys
import threading

LISTEN_PORT = 8319
UPSTREAM_HOST = "127.0.0.1"
UPSTREAM_PORT = 8317

class MITMHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self._proxy("GET")

    def do_POST(self):
        self._proxy("POST")

    def do_OPTIONS(self):
        self._proxy("OPTIONS")

    def _proxy(self, method):
        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b""

        # Log request
        print(f"\n{'='*70}", flush=True)
        print(f">>> {method} {self.path}", flush=True)
        print(f">>> Headers:", flush=True)
        for k, v in self.headers.items():
            # Truncate Authorization for readability
            if k.lower() == "authorization":
                v = v[:40] + "..." if len(v) > 40 else v
            print(f"    {k}: {v}", flush=True)
        if body:
            try:
                parsed = json.loads(body)
                # Show keys and truncated values
                print(f">>> Body keys: {list(parsed.keys())}", flush=True)
                # Show model, stream, tool count
                print(f"    model={parsed.get('model')}", flush=True)
                print(f"    stream={parsed.get('stream')}", flush=True)
                if 'tools' in parsed:
                    print(f"    tools count={len(parsed['tools'])}", flush=True)
                if 'input' in parsed:
                    inp = parsed['input']
                    if isinstance(inp, str):
                        print(f"    input={inp[:200]}", flush=True)
                    elif isinstance(inp, list):
                        print(f"    input items={len(inp)}", flush=True)
                        for i, item in enumerate(inp[:3]):
                            if isinstance(item, dict):
                                print(f"      [{i}] type={item.get('type')} role={item.get('role','')}", flush=True)
                if 'instructions' in parsed:
                    inst = parsed.get('instructions', '')
                    print(f"    instructions len={len(inst) if inst else 0}", flush=True)
            except:
                print(f">>> Body ({len(body)} bytes): {body[:500]}", flush=True)
        print(f"{'='*70}", flush=True)
        sys.stdout.flush()

        # Forward to upstream
        try:
            conn = http.client.HTTPConnection(UPSTREAM_HOST, UPSTREAM_PORT, timeout=30)
            # Forward all headers
            headers = {}
            for k, v in self.headers.items():
                if k.lower() not in ('host', 'transfer-encoding'):
                    headers[k] = v
            conn.request(method, self.path, body=body if body else None, headers=headers)
            resp = conn.getresponse()

            print(f"\n<<< Response: {resp.status} {resp.reason}", flush=True)

            # Send response status and headers
            self.send_response(resp.status)
            # Copy response headers
            for k, v in resp.getheaders():
                if k.lower() not in ('transfer-encoding',):
                    self.send_header(k, v)
            self.end_headers()

            # Stream response body
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()

            print(f"<<< Response complete", flush=True)
            conn.close()

        except Exception as e:
            print(f"<<< UPSTREAM ERROR: {e}", flush=True)
            self.send_error(502, str(e))

if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", LISTEN_PORT), MITMHandler)
    print(f"MITM proxy: 127.0.0.1:{LISTEN_PORT} → {UPSTREAM_HOST}:{UPSTREAM_PORT}")
    sys.stdout.flush()
    server.serve_forever()
