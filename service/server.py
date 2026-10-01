"""HTTP front end n8n calls each month. n8n schedules and labels; this service owns the rules and money.

POST /process  {"email": {id, sender, subject, date, text, links}}  -> process() result
POST /summary  {"month": "YYYY-MM"}                                  -> {subject, body, attachments}
GET  /health
"""
import hmac
import json
import os
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bookkeeping import summary
from bookkeeping.allocate import load_rules
from bookkeeping.fetch import Endpoints, Fetcher
from bookkeeping.ledger import Ledger
from bookkeeping.process import Email, process

TOKEN = os.environ.get("BOOKKEEPING_TOKEN", "")
MEDIA = Path(os.environ.get("BROWSER_MEDIA_DIR", "/media/browser"))
LOCK = threading.Lock()   # one bill at a time: one browser, one local model

if not TOKEN:
    raise SystemExit("BOOKKEEPING_TOKEN is required")


def fetcher() -> Fetcher:
    return Fetcher(Endpoints(os.environ["GATEWAY_URL"], os.environ["OPENCLAW_GATEWAY_TOKEN"],
                             os.environ["BROKER_URL"], os.environ["BROKER_TOKEN"]))


class H(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(200, {"ok": True}) if self.path == "/health" else self._send(404, {"ok": False})

    def do_POST(self):
        auth = self.headers.get("Authorization", "")
        if not hmac.compare_digest(auth.removeprefix("Bearer "), TOKEN):
            return self._send(401, {"ok": False, "message": "unauthorized"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self._send(400, {"ok": False, "message": "invalid JSON"})
        try:
            if self.path == "/process":
                e = body["email"]
                mail = Email(e["id"], e.get("sender", ""), e.get("subject", ""), date.fromisoformat(e["date"][:10]),
                             e.get("text", ""), e.get("links", []))
                with LOCK:
                    return self._send(200, {"ok": True, **process(mail, load_rules(), Ledger(), fetcher(), MEDIA)})
            if self.path == "/summary":
                return self._send(200, {"ok": True, **summary.build(Ledger(), body["month"])})
            return self._send(404, {"ok": False})
        except Exception as ex:  # never leak a stack trace with bill data in it to n8n's execution log
            return self._send(200, {"ok": False, "status": "error", "message": f"{type(ex).__name__}: {str(ex)[:200]}"})

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8091"))), H).serve_forever()
