# Resume here (phone or desk)

State 2026-10-03. Plan 001 Steps 1-5 built; nothing live yet.

## Deploy pending (owner was running an intensive job; do when `make status` shows no busy sessions)
1. `make deploy`: runs the tests, restarts `ph27-bookkeeping` (adds `/fixed`: rent, T-Mobile, USAA renters), and re-imports the n8n workflow **inactive**.
2. Live trial: `make trial-claude MSG=1a0c564cf0388ddf DATE=2026-09-21 TEXT='Amount paid $<amount from the receipt>'`. Then check that `iCloud/ph27/Accounting/2026/ledger-2026.csv` has a Claude row with Due To Owner 0.00.
3. Activate the workflow in the n8n UI ("ph27 Monthly Bills") once the trial looks right. The first scheduled run is Nov 3, 03:00 (October bills).

## Owner answers already in (don't re-ask)
- Gmail credential: added (`raqZCbXfJO1misFR`).
- Billing URLs: in `rules.yaml`.
- Pacific Power login URL: fixed.
- Forwarding: Quantum, Pacific Power, NW Natural, Portland Water -> dylan.grant@gmail.com.
- Fixed monthly entries:
  - Rent $3,520 (lease)
  - T-Mobile $15 (Venmo to brother)
  - USAA renters $68.52 through 2026-06, $66.16 from 2026-07 (changes about every 6 months; add a rate row when it does)

## Open
- Step 6 backfill Jan-Sep 2026: run `/fixed` per month, then the email intake per month. The utility emails before the forwarding filters may only be in Ivy's inbox, so expect gaps.
- Summary email lists bill paths instead of attaching PDFs; no Gmail labels yet.

## Safety rules (code-enforced; keep them)
- The payment-URL watchdog closes the tab.
- The broker clears typed passwords.
- Never snapshot a page after the broker typed.
- List 1Password item titles only (never URLs).
