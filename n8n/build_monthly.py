#!/usr/bin/env python3
"""Builds the 'ph27 Monthly Bills' n8n workflow (plan 001 Step 5) -> build/monthly_bills.json.

Schedule (3rd, 03:00) or manual -> last month's bill emails from rules.yaml senders -> one at a time:
POST ph27-bookkeeping /process -> summary -> email the owner. n8n holds no rules and no money logic.
Deploy:  docker cp build/monthly_bills.json n8n:/tmp/m.json && docker exec n8n n8n import:workflow --input=/tmp/m.json
(imports INACTIVE; activate only after the owner connects Gmail in the n8n UI.)
"""
import json
import os
from pathlib import Path

import yaml

HERE = Path(__file__).parent
rules = yaml.safe_load((HERE.parent / "rules.yaml").read_text())
senders = sorted({s for v in rules["vendors"] for s in v.get("senders", [])})
gmail_q = "from:(" + " OR ".join(senders) + ") after:{{ $('Month Range').first().json.after }} before:{{ $('Month Range').first().json.before }}"
SVC = "http://ph27-bookkeeping:8091"
TOKEN_CRED = {"httpHeaderAuth": {"id": "Ph27BookkeepTk1", "name": "ph27 bookkeeping token"}}
OWNER = "dylan.grant@gmail.com"
GMAIL_CRED = {"gmailOAuth2": {"id": "raqZCbXfJO1misFR", "name": "Gmail account"}}


def n(name, typ, ver, pos, params, **extra):
    return {"id": name.lower().replace(" ", "-"), "name": name, "type": typ, "typeVersion": ver, "position": pos,
            "parameters": params, **extra}


nodes = [
    n("Monthly Schedule", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 0],
      {"rule": {"interval": [{"field": "cronExpression", "expression": "0 3 3 * *"}]}}),
    n("Run Now", "n8n-nodes-base.manualTrigger", 1, [0, 200], {}),
    n("Month Range", "n8n-nodes-base.code", 2, [220, 100], {"jsCode": (HERE / "nodes_month_range.js").read_text()}),
    n("Bill Emails", "n8n-nodes-base.gmail", 2.1, [440, 100],
      {"resource": "message", "operation": "getAll", "returnAll": True, "simple": False,
       "filters": {"q": "=" + gmail_q}, "options": {}}, alwaysOutputData=True, credentials=GMAIL_CRED),
    n("To Email", "n8n-nodes-base.code", 2, [660, 100],
      {"mode": "runOnceForEachItem", "jsCode": (HERE / "nodes_to_email.js").read_text()}),
    n("One At A Time", "n8n-nodes-base.splitInBatches", 3, [880, 100], {"batchSize": 1, "options": {}}),
    n("Process Bill", "n8n-nodes-base.httpRequest", 4.2, [1100, 200],
      {"method": "POST", "url": SVC + "/process", "authentication": "genericCredentialType",
       "genericAuthType": "httpHeaderAuth", "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json) }}",
       "options": {"timeout": 2400000}}, credentials=TOKEN_CRED, onError="continueRegularOutput"),
    n("Build Summary", "n8n-nodes-base.httpRequest", 4.2, [1100, 0],
      {"method": "POST", "url": SVC + "/summary", "authentication": "genericCredentialType",
       "genericAuthType": "httpHeaderAuth", "sendBody": True, "specifyBody": "json",
       "jsonBody": "={{ JSON.stringify({ month: $('Month Range').first().json.month }) }}", "options": {}},
      credentials=TOKEN_CRED, executeOnce=True),
    n("Email Owner", "n8n-nodes-base.gmail", 2.1, [1320, 0],
      {"resource": "message", "operation": "send", "sendTo": OWNER, "subject": "={{ $json.subject }}",
       "emailType": "text", "message": "={{ $json.body + '\\nBills: ' + ($json.attachments || []).join('\\n  ') }}",
       "options": {"appendAttribution": False}}, credentials=GMAIL_CRED),
]
c = {
    "Monthly Schedule": [["Month Range"]], "Run Now": [["Month Range"]], "Month Range": [["Bill Emails"]],
    "Bill Emails": [["To Email"]], "To Email": [["One At A Time"]],
    "One At A Time": [["Build Summary"], ["Process Bill"]], "Process Bill": [["One At A Time"]],
    "Build Summary": [["Email Owner"]],
}
connections = {k: {"main": [[{"node": t, "type": "main", "index": 0} for t in out] for out in v]} for k, v in c.items()}
wf = {"id": "Ph27MonthlyBills", "name": "ph27 Monthly Bills", "active": False, "nodes": nodes, "connections": connections,
      "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "none"}, "pinData": {}}
os.makedirs(HERE / "build", exist_ok=True)
(HERE / "build" / "monthly_bills.json").write_text(json.dumps(wf, indent=2))
print("built", len(nodes), "nodes;", len(senders), "senders")
