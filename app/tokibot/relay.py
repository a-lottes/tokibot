"""Relay subscriber: receives hook events through an ntfy topic.

Claude Code running in the cloud (e.g. Claude Projects) cannot reach a gotchi on a
phone hotspot or home network. Its hooks publish to an ntfy topic instead, and the
gotchi keeps one outgoing connection open to that topic. No port needs to be open
on the gotchi's side, so this works behind any hotspot or NAT.

Message body (published by tokibot_client.py):
  {"tokibot": 1, "path": "/hook" | "/limits", "token": "...", "data": {...}}
"""
import json
import logging
import threading
import time
import urllib.parse
import urllib.request

log = logging.getLogger("tokibot.relay")

READ_TIMEOUT = 120         # ntfy sends a keepalive every ~45 s
MAX_BACKOFF = 60


def parse(line, token):
    """One line of ntfy's JSON stream -> (ntfy id, path, data), or None to skip it."""
    try:
        msg = json.loads(line)
    except ValueError:
        return None
    if msg.get("event") != "message":
        return None
    try:
        env = json.loads(msg.get("message") or "")
    except ValueError:
        return None
    if not isinstance(env, dict) or 1 not in (env.get("tokibot"), env.get("claudegotchi")):
        return None
    if token and env.get("token") != token:
        log.warning("Relay message with a wrong token ignored")
        return None
    if env.get("path") not in ("/hook", "/limits") or not isinstance(env.get("data"), dict):
        return None
    return msg.get("id"), env["path"], env["data"]


class Relay(threading.Thread):
    def __init__(self, url, token, dispatch, auth=""):
        super().__init__(daemon=True, name="relay")
        self.url = url.rstrip("/")
        self.token = token
        self.dispatch = dispatch
        self.auth = auth
        self.last_id = None
        self.stop_evt = threading.Event()

    def stream_url(self):
        # After a reconnect, ask ntfy for what we missed in between.
        q = {"since": self.last_id} if self.last_id else {}
        return self.url + "/json" + ("?" + urllib.parse.urlencode(q) if q else "")

    def run(self):
        backoff = 2
        while not self.stop_evt.is_set():
            try:
                headers = {"Authorization": f"Bearer {self.auth}"} if self.auth else {}
                req = urllib.request.Request(self.stream_url(), headers=headers)
                with urllib.request.urlopen(req, timeout=READ_TIMEOUT) as resp:
                    log.info("Relay connected: %s", self.url)
                    backoff = 2
                    for raw in resp:
                        if self.stop_evt.is_set():
                            return
                        hit = parse(raw.decode("utf-8", "replace"), self.token)
                        if hit:
                            self.last_id, path, data = hit
                            self.dispatch(path, data)
            except Exception as e:
                log.warning("Relay connection lost (%s), retrying in %d s", e, backoff)
            self.stop_evt.wait(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)
