# 001 - Shared-bill ledger agent: bill emails -> prorated "due to owner" ledger + bill archive

Status: PROPOSED 2026-09-30 (branch `claude_plan_01`)

## Why
ph27 pays its share of household bills (rent, utilities, internet, insurance, phone, subscriptions) out of the owner's personal accounts. Each share has to be recorded as owed to the owner, with the bill as documentation, and handed to the accountant at tax time. In 2025 this was a hand-built ledger (`iCloud/Taxes/2025/Deductible Expenses Ledger 2025.pdf`). This plan has an agent keep the 2026 version of that ledger by itself.

## Owner decisions (2026-09-30) - do not re-litigate
- **No Wave for now.** Wave is not on Pro, so it has no API. Output is a ledger in the accountant's format plus a bills folder. The owner is trying Wave's own Bluevine integration separately.
- **Scope is money only:** ZenBusiness, Namecheap, Bluevine, Wave. Buy Me a Coffee and the site tools (GitHub, Vercel, Render, Trello, GA, Umami, Neo4j) are out.
- **One agent (`bookkeeper`), no manager agent** until a second agent exists.
- **Where things live:** business logic in this repo (`ph27/business-ops`); generic MCP servers in `~/dev/MCPs`; runtime is the existing OpenClaw + n8n in `~/dev/me/ai-automations`.
- **The agent never pays anything or moves money.** Every bill here is already paid by autopay, Bilt, or a card. Paying the owner back from Bluevine stays a manual step.
- Per the owner's standing rule, there is no "review and submit yourself" gate. The agent records the entry. Anything it can't prove from the bill goes to `needs_review` with a reason.

## Allocation rules (source of truth: the 2025 ledger, confirmed by the owner)
| Share | Vendors / items | Category (2025 ledger name) |
|---|---|---|
| 5% (100 of 2,000 sq ft) | Rent (Bilt), Pacific Power, NW Natural, Portland Water Bureau | Rent / Utilities |
| 5% | Renters insurance | Insurance (non-health) |
| 5% of the business items only | Cleaning items in Amazon / Instacart orders | Janitorial |
| 50% | Quantum Fiber (formerly CenturyLink) | Utilities (internet) |
| 50% | 1Password | Dues and Subscriptions |
| 25% | T-Mobile | Telephone |
| 100% | Claude (replaced ChatGPT, which is gone), Namecheap, ZenBusiness, one-off licenses | Dues and Subscriptions / Legal and Professional |
| 100% of the business items only | Office items in Amazon / Instacart orders | Office |

- Rounding: half-up to cents, applied once to the final share.
- Ignore `iCloud/ph27/Accounting/Miscellaneous_Business_Expenses_Tracker.xlsx`: it's sample data, attached by mistake.
- Ignore `Home_Office_Deduction_Tracker.xlsx`'s 20%. The filed number is 5%.

## Design
```
Gmail (sender allowlist) --n8n poll--> intake item (message id, sender, subject, body, links)
      -> OpenClaw `bookkeeper` agent (browser): open the bill link, sign in via the credential broker,
         save the bill as a PDF, report {vendor, bill_date, amount_total, line_items[], pdf_path, status}
      -> deterministic code: verify the PDF exists and contains the amount -> match rule -> compute share
         -> append a ledger row -> file the PDF -> update the due-to-owner balance
monthly n8n cron -> summary email to the owner: rows added, needs_review items, balance owed, reimbursement amount
```
- The agent owns the browser outcome (finding and saving the bill). Code owns rules, math, dedupe, files, and verification. Same split as the apply flow (ai-automations plans 024/025).
- **Models:** bills carry account numbers and the home address. Use only local models (the `qwen3.8` / `gemma4:12b` routes already in OpenClaw) for anything that reads bill content. Never send it to the free Gemini tier, which may use prompts for training.
- **No new MCP server is needed for this plan.** The only `~/dev/MCPs` work is the Makefile cleanup in Step 1.

## Where the files go
- This repo:
  - `rules.yaml`: vendors, sender addresses, shares, categories, paid-from
  - `bookkeeping/`: Python rules engine, ledger writer, tests
  - `agents/bookkeeper/AGENTS.md`
  - `n8n/`: workflow builders, same pattern as `ai-automations/n8n/builders/`
- `iCloud/ph27/Accounting/2026/`:
  - `ledger-2026.csv`: the agent owns it; the owner reads it but doesn't hand-edit
  - `Bills/MM/<yyyy-mm-dd>_<vendor>_<amount>.pdf`
- Ledger columns keep the 2025 ledger's (Name, Applies to, Category, Transaction Date, Amount, Adjusted Amount, Prorated Deductible Amount, Notes). Added columns: Paid From, Due To Owner, Document, Source (Gmail message id), Status (`recorded` / `needs_review`), Reimbursed (date).

## Steps

### 0. Repo bootstrap (done with this plan's commit)
- `git init` `ph27/business-ops`, add a README and `.gitignore`, and put this plan on `claude_plan_01`. Nothing gets pushed.

### 1. `~/dev/MCPs` cleanup (separate repo, its own branch `claude_plan_01`)
- The root `Makefile` still calls the deleted `neo4j/` and `postgres/` directories. Point `start`, `stop`, `restart` and `update` at the three kept servers: `agent-memory-mcp-server`, `jobspy-mcp-server`, `browserless-mcp-server`.
- `browserless-mcp-server/docker-compose.yaml` has `TOKEN=your_local_secure_token`. Move it to an untracked `.env` value, or delete the server if OpenClaw's own browser has fully replaced it (check `ai-automations/openclaw` config for any `browserless` reference first).
- Verify: `make help` and `make -n start` / `make -n update` show no missing-directory errors.

### 2. Rules engine plus a regression test against the 2025 ledger
- Write `rules.yaml` from the table above and `bookkeeping/allocate.py`:
  - Input: vendor, date, gross amount, optional business-item subtotal.
  - Output: category, share %, adjusted amount, due-to-owner amount, note.
- Fixture: transcribe the **ph27** rows (skip the `1099` rows) of the 2025 ledger into `tests/fixtures/ledger_2025_ph27.csv`. The test recomputes every row.
- Two known differences in the filed ledger: whitelist them in the test and don't "fix" the engine to match.
  - Amazon Janitorial 2025-12-22: $30.00 × 5% = $1.50, but the ledger says $1.60.
  - 1Password 2025-05-05: $59.85 × 50% = $29.93, but the ledger says $30.00.
- Done when every other ph27 row matches to the cent.

### 3. Ledger writer and bill filing
- Build `bookkeeping/ledger.py`:
  - Appends rows to `ledger-2026.csv`, deduping on the Gmail message id and on (vendor, date, amount).
  - Files each PDF under `Bills/MM/`.
  - Recomputes the due-to-owner balance: sum of Due To Owner minus rows with a Reimbursed date.
- Mount the iCloud folder into the n8n container read-write. The path has spaces, so quote it in compose. **STOP** if OrbStack can't see iCloud files that haven't been downloaded yet. In that case, write to `~/docker/shared/ph27-ledger/` and sync to iCloud from the host.
- Tests: re-running the same intake adds no row, and a failed write leaves no half-written row.

### 4. `bookkeeper` OpenClaw agent
- Write `agents/bookkeeper/AGENTS.md`:
  - **Goal:** given an intake item, get the actual bill (not just the email) and report the JSON above.
  - **Rules:**
    - Sign in only through the credential broker.
    - Never click pay, autopay, or any payment control, and never type into a payment form.
    - Never solve a CAPTCHA.
    - On 2FA the broker can't handle, return `blocked_login` with the URL.
- Register the agent the same way `autoapply` and `jdfinder` are (`ai-automations/openclaw/agents/*`; runbook in `ai-automations/n8n/builders/agent-apply/README.md`). Use a local model route. Browser tool exposed directly (`tools.toolSearch false`, per ai-automations plan 028).
- **Credential broker:** `ai-automations/n8n/scripts/job-credentials.js` is hard-wired to the `job-sites` vault (`OP_JOB_VAULT`). Add a per-request vault parameter with the default unchanged. Each vendor in `rules.yaml` names its vault (see the vault map below). Run the broker's existing tests (`n8n/scripts/test`). That change is committed in ai-automations on its own branch.
- **Verification (code, not the agent):** run `pdftotext` on the saved PDF and check that the reported total appears in it. On a mismatch or missing file, the row is `needs_review`.
- **Mixed orders (Amazon / Instacart): phase 2, not in this plan's first cut.** The agent would list line items; code would keep only items matching the cleaning / office keyword lists in `rules.yaml`; anything unmatched goes to `needs_review`.

### 5. n8n intake and monthly summary
- **Intake workflow:**
  - Poll Gmail every 30 minutes for senders in `rules.yaml` (Bilt, Pacific Power, NW Natural, Portland Water Bureau, Quantum Fiber, T-Mobile, Anthropic / Claude billing, 1Password, Namecheap, ZenBusiness, insurer).
  - Call the agent, run Steps 2-3, and on a Gmail success label the email `ph27/recorded` or `ph27/needs_review`.
- **Monthly workflow:** on the 1st, email the owner last month's rows, open `needs_review` items with reasons, the balance owed, and the PDFs attached. A self-addressed summary email is allowed.
- Builders live in `business-ops/n8n/`. Push live with the `docker exec n8n` import, per the owner's n8n rule.

### 6. Backfill Jan-Sep 2026
- Run intake over Gmail from 2026-01-01 to today, in date order.
- Expected: about 9 × (rent, power, gas, water, internet, insurance, phone) plus subscriptions and the Namecheap / ZenBusiness renewals.
- Hand the owner a count by vendor and month, and flag every gap (a vendor/month with no row). Some bills (Bilt rent receipts, the insurer) may never have been emailed. Those get a `needs_review` gap row, not an invented amount.

## Verification / done criteria
1. The Step 2 regression test passes (all ph27 2025 rows except the two whitelisted ones).
2. Dry run on three real 2026 emails (one Bilt rent, one Pacific Power, one Quantum Fiber), writing to a scratch ledger:
   - Each row has a PDF whose text contains the amount.
   - Shares are $176.00, 5%, and 50%.
3. Re-running the dry run adds zero rows.
4. The backfill completes, and every month Jan-Sep has a rent, power, and internet row or an explicit gap row.
5. The agent never reached a payment page. Check the browser screenshots under `~/docker/shared/screenshots` for the backfill run.

## STOP conditions
- A vendor portal needs SMS 2FA on every login. Record `blocked_login` gap rows for that vendor and report it; don't retry in a loop.
- Anything suggests the agent would have to act in a payment flow to see the bill.
- The Step 2 regression shows differences other than the two whitelisted rows. Report them; don't change the rules.

## Vault map (owner-created 2026-09-30; the owner can move items, and `rules.yaml` follows)
| Vault | Holds | Used by |
|---|---|---|
| `utilities` | Bilt (rent), Pacific Power, NW Natural, Portland Water Bureau, Quantum Fiber, T-Mobile, renters insurer | 001 |
| `ph27` | ZenBusiness, Namecheap, Anthropic / Claude billing, 1Password billing | 001 receipts, 003 |
| `ph27-money` | Bluevine, Wave | 004, 005, 006 |
| `ph27-marketing` | nothing yet | later |

## Owner actions (before Step 4)
- [x] Vaults created 2026-09-30: `utilities`, `ph27`, `ph27-money`, `ph27-marketing`.
- [ ] Make sure each vendor login in the vault map below exists in its vault, with the portal URL saved on the item (the broker matches logins by host).
- [ ] Confirm bills go to `dylan.grant@gmail.com`, or list the other inboxes.
- [ ] Fill in `paid_from` per vendor in `rules.yaml` (Bilt from BECU; which subscriptions come from the USAA shared account).
- [ ] Name the renters insurer (the 2025 ledger just says "Insurance").

## Later plans (not this one)
- 002: mixed Amazon / Instacart orders (item-level business split).
- 003: ZenBusiness compliance calendar (annual report, registered agent) and Namecheap renewal reminders. This is browser-only for ZenBusiness.
- 004: Wave, if it's upgraded to Pro, or if the Bluevine -> Wave integration turns out to cover it. Post ledger rows as entries against a "Paid by owner" account.
- 005: detect Bluevine reimbursement transfers and set Reimbursed dates automatically.
