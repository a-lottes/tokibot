"""A tiny in-memory stand-in for an ntfy server (POST /<topic>, GET /<topic>/json stream)."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeNtfy:
    def __init__(self):
        self.messages = []          # (topic, id, body)
        self.cond = threading.Condition()
        fake = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
                with fake.cond:
                    mid = f"m{len(fake.messages)}"
                    fake.messages.append((self.path.strip("/"), mid, body))
                    fake.cond.notify_all()
                out = json.dumps({"id": mid, "event": "message"}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def do_GET(self):
                path, _, query = self.path.partition("?")
                topic = path.strip("/").rsplit("/json", 1)[0]
                since = query.split("since=", 1)[1] if "since=" in query else None
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                self.wfile.write(b'{"event":"open"}\n')
                self.wfile.flush()
                with fake.cond:
                    ids = [m[1] for m in fake.messages]
                    pos = ids.index(since) + 1 if since in ids else len(fake.messages)
                while True:
                    with fake.cond:
                        fake.cond.wait_for(lambda: len(fake.messages) > pos, timeout=1)
                        new = fake.messages[pos:]
                        pos = len(fake.messages)
                    try:
                        for t, mid, body in new:
                            if t == topic:
                                line = {"id": mid, "time": int(time.time()), "event": "message",
                                        "topic": t, "message": body}
                                self.wfile.write(json.dumps(line).encode() + b"\n")
                        self.wfile.flush()
                    except OSError:
                        return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
