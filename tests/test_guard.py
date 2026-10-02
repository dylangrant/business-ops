import pytest

from bookkeeping.guard import is_forbidden


@pytest.mark.parametrize("url", [
    "https://csapps.pacificpower.net/secure/my-account/payments",
    "https://ipn2.paymentus.com/cp/payments.action",
    "https://x.com/payment-history/pay-now",
    "https://csapps.pacificpower.net/idm/guest-pay-login",
    "https://x.com/billing/autopay",
    "https://x.com/account/pay-my-bill",
    "https://x.com/checkout?step=1",
    "https://x.com/settings/payment-method",
    "https://x.com/a?action=pay",
])
def test_payment_pages_blocked(url):
    assert is_forbidden(url)


@pytest.mark.parametrize("url", [
    "https://csapps.pacificpower.net/secure/my-account/billing-history",
    "https://csapps.pacificpower.net/secure/my-account/billing-payment-history",
    "https://ipn2.paymentus.com/cp/bills.action",
    "https://css.portlandoregon.gov/css/account/accountTransaction",
    "https://x.com/account/statements",
    "https://x.com/bills/2026-09.pdf",
    "https://www.pacificpower.net/",
    "",
])
def test_bill_pages_allowed(url):
    assert not is_forbidden(url)
