import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
N8N = ROOT / "n8n"


@pytest.fixture(scope="module")
def wf():
    subprocess.run([sys.executable, str(N8N / "build_monthly.py")], check=True, capture_output=True)
    return json.loads((N8N / "build" / "monthly_bills.json").read_text())


def test_attachments_node_wired_between_summary_and_email(wf):
    names = {n["name"]: n for n in wf["nodes"]}
    assert names["Attachments To Binary"]["type"] == "n8n-nodes-base.code"
    nxt = lambda a: [t["node"] for out in wf["connections"][a]["main"] for t in out]
    assert nxt("Build Summary") == ["Attachments To Binary"]
    assert nxt("Attachments To Binary") == ["Send Email?"]
    assert wf["connections"]["Send Email?"]["main"] == [[{"node": "Email Owner", "type": "main", "index": 0}], []]


def test_gmail_node_attaches_binaries(wf):
    p = {n["name"]: n for n in wf["nodes"]}["Email Owner"]["parameters"]
    assert p["options"]["attachmentsUi"] == {
        "attachmentsBinary": [{"property": "={{ Object.keys($binary || {}).join(',') }}"}]}
    assert "Bills:" not in p["message"]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_attachments_js_builds_binary(wf):
    js = next(n for n in wf["nodes"] if n["name"] == "Attachments To Binary")["parameters"]["jsCode"]
    harness = ("const $input={all:()=>[{json:{subject:'s',attachments:[{filename:'a.pdf',mimeType:'application/pdf',data:'QQ=='},"
               "{filename:'b.txt',mimeType:'text/plain',data:'Qg=='}]}}]};const f=new Function('$input',process.argv[1]);"
               "console.log(JSON.stringify(f($input)))")
    out = json.loads(subprocess.run(["node", "-e", harness, js], check=True, capture_output=True, text=True).stdout)
    assert out == [{"json": {"subject": "s"}, "binary": {
        "attachment_0": {"data": "QQ==", "mimeType": "application/pdf", "fileName": "a.pdf"},
        "attachment_1": {"data": "Qg==", "mimeType": "text/plain", "fileName": "b.txt"}}}]


def test_schedule_runs_in_pacific_time(wf):
    # n8n defaults to UTC; without this the 03:00 run fires at 20:00 PT the day before.
    assert wf["settings"]["timezone"] == "America/Los_Angeles"
    trigger = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.scheduleTrigger")
    assert trigger["parameters"]["rule"]["interval"][0]["expression"] == "0 3 3 * *"


def test_backfill_webhook_node(wf):
    node = {n["name"]: n for n in wf["nodes"]}["Backfill"]
    assert node["type"] == "n8n-nodes-base.webhook"
    assert node["parameters"]["httpMethod"] == "POST"
    assert node["parameters"]["path"] == "ph27-bills-backfill"
    assert node["parameters"]["authentication"] == "headerAuth"
    assert node["parameters"]["responseMode"] == "lastNode"
    assert node["webhookId"] == "ph27-bills-backfill"
    assert node["credentials"]["httpHeaderAuth"]["id"] == "Ph27BookkeepTk1"


def test_all_triggers_reach_month_range_and_timezone_kept(wf):
    for trigger in ("Monthly Schedule", "Run Now", "Backfill"):
        assert [t["node"] for out in wf["connections"][trigger]["main"] for t in out] == ["Month Range"]


def test_send_email_gate_checks_backfill(wf):
    gate = {n["name"]: n for n in wf["nodes"]}["Send Email?"]
    assert gate["type"] == "n8n-nodes-base.if"
    cond = gate["parameters"]["conditions"]["conditions"][0]
    assert "$('Backfill').isExecuted" in cond["leftValue"]
    assert cond["rightValue"] is False


def month_range(json_in):
    js = (N8N / "nodes_month_range.js").read_text()
    harness = ("const $input={first:()=>({json:JSON.parse(process.argv[2])})};"
               "const f=new Function('$input',process.argv[1]);console.log(JSON.stringify(f($input)))")
    out = subprocess.run(["node", "-e", harness, js, json.dumps(json_in)], check=True, capture_output=True, text=True).stdout
    return json.loads(out)[0]["json"]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
@pytest.mark.parametrize("src", [{"body": {"month": "2026-03"}}, {"month": "2026-03"}, {"query": {"month": "2026-03"}}])
def test_month_range_reads_each_source(src):
    assert month_range(src) == {"month": "2026-03", "after": "2026/03/01", "before": "2026/04/01"}


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_month_range_december_rolls_year():
    assert month_range({"body": {"month": "2025-12"}})["before"] == "2026/01/01"


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
@pytest.mark.parametrize("src", [{"body": {"month": "garbage"}}, {}])
def test_month_range_invalid_falls_back_to_last_month(src):
    from datetime import date
    today = date.today()
    y, m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    assert month_range(src)["month"] == f"{y}-{m:02d}"
