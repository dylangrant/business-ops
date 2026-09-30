"""Append-only 2026 ledger (CSV) + bill filing. Columns extend the 2025 ledger the accountant already takes."""
import csv
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

COLUMNS = ["Name", "Applies to", "Category", "Transaction Date", "Amount", "Adjusted Amount",
           "Prorated Deductible Amount", "Notes", "Paid From", "Due To Owner", "Document",
           "Source", "Status", "Reimbursed"]

DEFAULT_ROOT = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/ph27/Accounting/2026"


@dataclass
class Entry:
    name: str
    category: str
    txn_date: date
    amount: Decimal            # gross bill
    adjusted: Decimal
    deductible: Decimal
    notes: str = ""
    paid_from: str = ""
    due_to_owner: Decimal = Decimal("0")
    document: str = ""
    source: str = ""           # Gmail message id (dedupe key)
    status: str = "recorded"   # recorded | needs_review
    applies_to: str = "ph27"


class Ledger:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or os.environ.get("PH27_LEDGER_ROOT") or DEFAULT_ROOT)
        self.path = self.root / "ledger-2026.csv"

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(newline="") as f:
            return list(csv.DictReader(f))

    def _is_duplicate(self, e: Entry, rows: list[dict]) -> bool:
        for r in rows:
            if e.source and r["Source"] == e.source:
                return True
            if (r["Name"], r["Transaction Date"], r["Amount"], r["Category"]) == \
               (e.name, e.txn_date.isoformat(), f"{e.amount:.2f}", e.category):
                return True
        return False

    def add(self, e: Entry) -> bool:
        """Returns False (and writes nothing) when the entry duplicates an existing row."""
        rows = self.rows()
        if self._is_duplicate(e, rows):
            return False
        rows.append({
            "Name": e.name, "Applies to": e.applies_to, "Category": e.category,
            "Transaction Date": e.txn_date.isoformat(), "Amount": f"{e.amount:.2f}",
            "Adjusted Amount": f"{e.adjusted:.2f}", "Prorated Deductible Amount": f"{e.deductible:.2f}",
            "Notes": e.notes, "Paid From": e.paid_from, "Due To Owner": f"{e.due_to_owner:.2f}",
            "Document": e.document, "Source": e.source, "Status": e.status, "Reimbursed": "",
        })
        self._write(rows)
        return True

    def _write(self, rows: list[dict]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=COLUMNS)
                w.writeheader()
                w.writerows(rows)
            os.replace(tmp, self.path)       # atomic: a failure leaves the old file intact
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def file_bill(self, pdf: Path, vendor: str, txn_date: date, amount: Decimal) -> Path:
        slug = re.sub(r"[^a-z0-9]+", "-", vendor.lower()).strip("-")
        dest_dir = self.root / "Bills" / f"{txn_date:%m}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{txn_date.isoformat()}_{slug}_{amount:.2f}.pdf"
        if not dest.exists():
            shutil.copyfile(pdf, dest)
        return dest

    def balance_owed(self) -> Decimal:
        return sum((Decimal(r["Due To Owner"]) for r in self.rows()
                    if r["Status"] == "recorded" and not r["Reimbursed"]), Decimal("0"))
