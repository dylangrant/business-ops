"""Turn a bill into a prorated ledger allocation using rules.yaml. Money math is Decimal, half-up, once."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import yaml

CENT = Decimal("0.01")
RULES_PATH = Path(__file__).resolve().parent.parent / "rules.yaml"


class NoRule(Exception):
    """No vendor rule matches; the caller records a needs_review row."""


@dataclass(frozen=True)
class Allocation:
    vendor_key: str
    category: str
    share: Decimal
    adjusted_amount: Decimal   # what the ledger calls "Adjusted Amount"
    deductible: Decimal        # prorated deductible = the amount ph27 owes the owner
    vault: str | None
    paid_from: str | None


def money(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def load_rules(path: Path = RULES_PATH) -> dict:
    return yaml.safe_load(path.read_text())


def _find(entries: list[dict], vendor: str) -> dict | None:
    name = vendor.lower()
    for e in entries:
        if any(m in name for m in e["match"]):
            return e
    return None


def allocate(rules: dict, vendor: str, gross: Decimal | str,
             business_subtotal: Decimal | str | None = None,
             item_category: str | None = None) -> Allocation:
    gross = Decimal(str(gross))
    mixed = _find(rules["mixed_vendors"], vendor)
    if mixed:
        if business_subtotal is None or item_category not in rules["mixed_categories"]:
            raise NoRule(f"{vendor}: mixed order needs business_subtotal and item_category")
        cat = rules["mixed_categories"][item_category]
        share, adjusted = Decimal(cat["share"]), money(Decimal(str(business_subtotal)))
        return Allocation(mixed["key"], cat["category"], share, adjusted, money(adjusted * share), None, None)
    rule = _find(rules["vendors"], vendor)
    if not rule:
        raise NoRule(f"no rule for vendor {vendor!r}")
    share = Decimal(rule["share"])
    amount = money(gross * share)
    return Allocation(rule["key"], rule["category"], share, amount, amount,
                      rule.get("vault"), rule.get("paid_from"))
