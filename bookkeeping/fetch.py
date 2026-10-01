"""One bill fetch: bookkeeper agent <-> credential broker loop, with the payment-page watchdog.

Code owns the safety rules: the sign-in ref must be a text box before the broker types,
payment pages close the tab, and a failed sign-in closes the tab (a typed password must
never sit in a page an agent can snapshot).
"""
import json
import re
import threading
import urllib.request
import uuid
from dataclasses import dataclass

from bookkeeping.guard import is_forbidden


@dataclass
class Endpoints:
    gateway: str          # e.g. http://gateway-tailnet-proxy:8080
    gateway_token: str
    broker: str           # e.g. http://job-credentials:8090/resolve
    broker_token: str
    profile: str = "openclaw"


def http_post(url: str, body: dict, token: str, timeout: int) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except Exception as e:  # network errors and timeouts become a status, never an exception
        return {"ok": False, "transport_error": str(e)[:300]}


class Fetcher:
    def __init__(self, ep: Endpoints, post=http_post, poll_seconds: float = 4.0, log=print):
        self.ep, self.post, self.poll, self.log = ep, post, poll_seconds, log

    def browser(self, args: dict, timeout: int = 60) -> dict:
        return self.post(self.ep.gateway + "/tools/invoke",
                         {"tool": "browser", "agentId": "bookkeeper", "args": {"profile": self.ep.profile, **args}},
                         self.ep.gateway_token, timeout)

    def agent(self, msg: str) -> dict:
        r = self.post(self.ep.gateway + "/v1/chat/completions",
                      {"model": "openclaw/bookkeeper", "user": "bk-" + uuid.uuid4().hex[:8],
                       "messages": [{"role": "user", "content": msg}]}, self.ep.gateway_token, 1200)
        txt = r["choices"][0]["message"]["content"] if "choices" in r else json.dumps(r)
        m = re.search(r"\{.*\}", txt, re.S)
        try:
            return json.loads(m.group(0))
        except Exception:
            return {"status": "unparsed", "notes": txt[:300]}

    def close(self, tab: str) -> None:
        self.browser({"action": "close", "targetId": tab})

    def _watch(self, tab: str, stop: threading.Event, tripped: list) -> None:
        while not stop.wait(self.poll):
            r = self.browser({"action": "act", "kind": "evaluate", "fn": "() => location.href", "targetId": tab}, 20)
            url = r.get("result", {}).get("details", {}).get("result") or ""
            if isinstance(url, str) and is_forbidden(url):
                tripped.append(url)
                self.close(tab)
                self.log(f"guard: payment page, tab closed: {url}")
                return

    def _agent_guarded(self, tab: str, goal: str) -> tuple[dict, str]:
        stop, tripped = threading.Event(), []
        t = threading.Thread(target=self._watch, args=(tab, stop, tripped), daemon=True)
        t.start()
        try:
            a = self.agent(goal)
        finally:
            stop.set()
            t.join(timeout=30)
        return a, (tripped[0] if tripped else "")

    def _ref_line(self, tab: str, ref: str) -> str:
        snap = self.browser({"action": "snapshot", "targetId": tab, "refs": "aria", "mode": "efficient", "depth": 40})
        text = snap.get("result", {}).get("content", [{}])[0].get("text", "")
        return next((l.strip() for l in text.splitlines() if f"[ref={ref}]" in l), "")

    def run(self, vendor: str, start_url: str, vault: str, hint: str = "") -> dict:
        opened = self.browser({"action": "open", "url": start_url})
        tab = opened.get("result", {}).get("details", {}).get("targetId")
        if not tab:
            return {"status": "failed", "notes": f"could not open {start_url}: {json.dumps(opened)[:200]}"}
        goal = (f"targetId {tab}, profile {self.ep.profile}. vendor: {vendor}. billUrl: {start_url} (already loaded). {hint} "
                "Sign in if needed (return blocked_login at the sign-in form), then find the most recent bill and save it as a PDF. "
                "Answer with the final JSON.")
        try:
            for _ in range(5):
                a, tripped = self._agent_guarded(tab, goal)
                if tripped:
                    return {"status": "guard_stopped", "notes": f"agent reached a payment page: {tripped}"}
                tab = a.get("targetId") or tab
                if a.get("status") != "blocked_login":
                    return a
                line = self._ref_line(tab, a.get("usernameRef", ""))   # safe: nothing typed yet
                if "textbox" not in line:
                    goal = (f"targetId {tab}, profile {self.ep.profile}. vendor: {vendor}. The element you returned as usernameRef "
                            f"({a.get('usernameRef')}) is '{line[:80]}', NOT a text box. Click it, close any popup, snapshot again, "
                            "and return blocked_login with the refs of the username/email TEXT BOX, password box and sign-in button.")
                    continue
                b = self.post(self.ep.broker, {"action": "login", "vault": vault, "url": "", "company": vendor,
                              "gatewayUrl": self.ep.gateway + "/tools/invoke", "gatewayToken": self.ep.gateway_token,
                              "profile": self.ep.profile, "targetId": tab, "usernameRef": a.get("usernameRef"),
                              "passwordRef": a.get("passwordRef"), "submitRef": a.get("submitRef")}, self.ep.broker_token, 300)
                if b.get("status") not in ("logged_in", "username_submitted"):
                    return {"status": "blocked_login", "notes": f"sign-in failed: {b.get('status')} {b.get('message', '')[:150]}"}
                goal = (f"targetId {tab}, profile {self.ep.profile}. vendor: {vendor}. You are now signed in. "
                        "Find the most recent bill and save it as a PDF. Answer with the final JSON.")
            return {"status": "failed", "notes": "gave up after 5 rounds"}
        finally:
            self.close(tab)
