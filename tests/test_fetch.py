import json
import time

from bookkeeping.fetch import Endpoints, Fetcher

EP = Endpoints("http://gw", "gt", "http://broker/resolve", "bt")


class Fake:
    """Scripted gateway + broker. agent_replies: list of dicts; url: current tab URL (mutable)."""
    def __init__(self, agent_replies, snapshot="- textbox \"User ID\" [ref=u1]", broker_status="logged_in", url="https://ok/x",
                 agent_delay=0.0):
        self.replies, self.snapshot, self.broker_status, self.url, self.delay = list(agent_replies), snapshot, broker_status, url, agent_delay
        self.calls, self.closed, self.broker_calls, self.prompts = [], [], [], []

    def __call__(self, url, body, token, timeout):
        self.calls.append((url, body))
        if url.endswith("/resolve"):
            self.broker_calls.append(body)
            return {"ok": True, "status": self.broker_status}
        if url.endswith("/v1/chat/completions"):
            self.prompts.append(body["messages"][0]["content"])
            time.sleep(self.delay)
            return {"choices": [{"message": {"content": json.dumps(self.replies.pop(0))}}]}
        a = body["args"]
        if a["action"] == "open":
            return {"result": {"details": {"targetId": "T1"}}}
        if a["action"] == "close":
            self.closed.append(a["targetId"]); return {"ok": True}
        if a["action"] == "snapshot":
            return {"result": {"content": [{"text": self.snapshot}]}}
        if a.get("kind") == "evaluate":
            return {"result": {"details": {"result": self.url}}}
        return {"ok": True}


def test_happy_path_signs_in_then_saves():
    f = Fake([{"status": "blocked_login", "usernameRef": "u1", "passwordRef": "p1", "submitRef": "s1"},
              {"status": "saved", "pdfPath": "FILE:/x.pdf", "amountTotal": 545.51}])
    r = Fetcher(EP, post=f, poll_seconds=0.01).run("Pacific Power", "https://pp", "utilities-expenses")
    assert r["status"] == "saved"
    assert f.broker_calls[0]["vault"] == "utilities-expenses" and f.broker_calls[0]["usernameRef"] == "u1"
    assert f.closed == ["T1"]


def test_link_instead_of_textbox_is_sent_back_to_the_agent():
    f = Fake([{"status": "blocked_login", "usernameRef": "e24"}, {"status": "not_found"}],
             snapshot='- link "sign in and manage account" [ref=e24]')
    r = Fetcher(EP, post=f, poll_seconds=0.01).run("PP", "https://pp", "v")
    assert r["status"] == "not_found" and not f.broker_calls
    assert "NOT a text box" in f.prompts[1]


def test_failed_sign_in_stops_and_closes_tab():
    f = Fake([{"status": "blocked_login", "usernameRef": "u1", "passwordRef": "p1"}], broker_status="login_rejected")
    r = Fetcher(EP, post=f, poll_seconds=0.01).run("PP", "https://pp", "v")
    assert r["status"] == "blocked_login" and "login_rejected" in r["notes"]
    assert f.closed == ["T1"]


def test_payment_page_trips_the_guard():
    f = Fake([{"status": "saved"}], url="https://pp/secure/my-account/payments", agent_delay=0.2)
    r = Fetcher(EP, post=f, poll_seconds=0.01).run("PP", "https://pp", "v")
    assert r["status"] == "guard_stopped" and "payments" in r["notes"]
    assert "T1" in f.closed
