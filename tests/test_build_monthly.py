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
    assert nxt("Attachments To Binary") == ["Email Owner"]


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
