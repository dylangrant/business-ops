"""URL guard for the bookkeeper's browser tab: payment pages are off-limits, enforced in code."""
import re
from urllib.parse import urlparse

# Path/query words that mean "money can move from here". Matched as whole path
# segments or word parts so "/statements" or "/billing-history" stay allowed.
FORBIDDEN = re.compile(
    r"(?:^|[/_\-.?=&])(?:pay|payment|payments|paybill|pay-bill|pay-my-bill|make-?a-?payment|autopay|auto-?pay|"
    r"wallet|checkout|guest-?pay|billpay|bill-pay|recurring-?payment|payment-?method|add-?card)(?:$|[/_\-.?=&])",
    re.I)


# Read-only history pages that happen to contain the word "payment" (Pacific Power's
# bills live at /billing-payment-history). Removed before the check, nothing else is.
HISTORY = re.compile(r"(?:billing-)?payments?[-_]?history", re.I)


def is_forbidden(url: str) -> bool:
    p = urlparse(url or "")
    return bool(FORBIDDEN.search(HISTORY.sub("history", p.path + ("?" + p.query if p.query else ""))))
