"""Live test harness for one bill fetch: bookkeeper agent <-> credential broker loop.

Usage: python3 scripts/live_fetch.py "Pacific Power" https://www.pacificpower.net/ utilities-expenses
Runs the same loop the n8n intake workflow will run (Step 5). Never snapshots a page after
the broker has typed, because snapshots expose input values.
"""
import json, re, subprocess, sys, uuid

AI = "/Users/dylangrant/dev/me/ai-automations"
env = {}
for f in [f"{AI}/openclaw/.env", f"{AI}/n8n/.env"]:
    for line in open(f):
        m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
        if m: env[m.group(1)] = m.group(2).strip().strip('"')
GW = "http://gateway-tailnet-proxy:8080"


def post(url, body, auth, timeout):
    r = subprocess.run(["docker", "exec", "-e", f"A={auth}", "-e", f"B={json.dumps(body)}", "n8n", "sh", "-c",
        f'wget -O- -T {timeout} --header "Authorization: Bearer $A" --header "Content-Type: application/json" --post-data "$B" {url}'],
        capture_output=True, text=True)
    try: return json.loads(r.stdout)
    except Exception: return {"raw": r.stdout[:300], "err": r.stderr[-300:]}


def browser(args):
    return post(GW + "/tools/invoke", {"tool": "browser", "agentId": "bookkeeper", "args": {"profile": "openclaw", **args}}, env["OPENCLAW_GATEWAY_TOKEN"], 60)


def agent(msg):
    r = post(GW + "/v1/chat/completions", {"model": "openclaw/bookkeeper", "user": "bk-" + uuid.uuid4().hex[:8],
             "messages": [{"role": "user", "content": msg}]}, env["OPENCLAW_GATEWAY_TOKEN"], 900)
    txt = r["choices"][0]["message"]["content"] if "choices" in r else json.dumps(r)
    m = re.search(r"\{.*\}", txt, re.S)
    try: return json.loads(m.group(0))
    except Exception: return {"status": "unparsed", "raw": txt[:500]}


def main(vendor, start_url, vault):
    tab = browser({"action": "open", "url": start_url})["result"]["details"]["targetId"]
    print("tab", tab, flush=True)
    goal = (f"targetId {tab}, profile openclaw. vendor: {vendor}. billUrl: {start_url} (already loaded). "
            "Sign in (return blocked_login at the sign-in form), then find the most recent bill and save it as a PDF. Answer with the final JSON.")
    for rnd in range(5):
        a = agent(goal); print("agent", rnd, json.dumps(a)[:600], flush=True)
        if a.get("status") != "blocked_login":
            return a
        tid = a.get("targetId") or tab
        # Guard (safe: nothing typed yet): the username ref must be a text box, not a link.
        snap = browser({"action": "snapshot", "targetId": tid, "refs": "aria", "mode": "efficient", "depth": 40})
        text = snap.get("result", {}).get("content", [{}])[0].get("text", "")
        line = next((l for l in text.splitlines() if f"[ref={a.get('usernameRef')}]" in l), "")
        if "textbox" not in line:
            print("guard: usernameRef is not a text box:", line.strip()[:100], flush=True)
            goal = (f"targetId {tid}, profile openclaw. vendor: {vendor}. The element you returned as usernameRef ({a.get('usernameRef')}) is "
                    f"'{line.strip()[:80]}', NOT a text box. Click it, close any popup, snapshot again, and return blocked_login with the "
                    "refs of the username/email TEXT BOX, password box and sign-in button from that new snapshot.")
            continue
        b = post("http://job-credentials:8090/resolve", {"action": "login", "vault": vault, "url": "", "company": vendor,
                 "gatewayUrl": GW + "/tools/invoke", "gatewayToken": env["OPENCLAW_GATEWAY_TOKEN"], "profile": "openclaw", "targetId": tid,
                 "usernameRef": a.get("usernameRef"), "passwordRef": a.get("passwordRef"), "submitRef": a.get("submitRef")}, env["BROKER_TOKEN"], 300)
        print("broker", json.dumps(b)[:400], flush=True)
        if b.get("status") not in ("logged_in", "username_submitted"):
            browser({"action": "close", "targetId": tid})   # never leave a typed password open
            return b
        goal = f"targetId {tid}, profile openclaw. vendor: {vendor}. You are now signed in. Find the most recent bill and save it as a PDF. Answer with the final JSON."
    return {"status": "gave_up"}


if __name__ == "__main__":
    print("RESULT", json.dumps(main(*sys.argv[1:4])), flush=True)
