# Session — Close the send loop: the first REAL outbound effect (2026-06-20)

**Goal (one sentence):** a human clicks Approve on a drafted outreach → the run resumes → a REAL email
is sent via the founder's Gmail → it settles with provenance. Proven by an actual email accepted by
Gmail for the founder's own inbox.

**Verdict: DONE.** The lead-finder now emits the gated `send_email`; approving the parked outreach
performs a real send via Gmail SMTP. One real email was sent founder→founder and the run settled —
**settle #1 of the ~100** the BLUEPRINT §7 WIN needs.

---

## What changed

1. **Gmail SMTP transport** (`packages/syscall/src/agentx_syscall/email_transports.py`)
   - `SmtpEmailTransport`: stdlib `smtplib` + `ssl`, STARTTLS, App Password; runs the blocking
     handshake in a worker thread; sets `From` to the per-send sender (#8); returns a `Message-ID`
     receipt. No new pip dependency.
   - `build_configured_email_transport` now prefers **SMTP** (`SMTP_HOST`+`SMTP_PASSWORD`) > **Resend**
     (`RESEND_API_KEY`) > **None**, all under the `RUN_LIVE_EMAIL` master gate (so a dev `.env`
     carrying SMTP keys never makes a sim/test runtime build a real transport). Env reading is
     injectable so selection/absence tests are deterministic.
   - **Bug fixed:** the `.env` fallback used `parents[3]` → resolved `packages/` instead of the repo
     root, so env-driven SMTP/Resend config silently yielded *no transport* (→ `human_task` tail,
     never sending). `_find_dotenv` now walks up to the nearest `.env`. This had never been caught
     because no real env-driven send had ever run.

2. **Lead-finder emits `send_email`** (`packages/mandate/.../library/lead_finder_playbook.py`)
   - `build_outreach_call` emits `send_email` (was `draft_email`) with the grounded outreach body.
     Because `send_email` is external_message at L2, an instance at ring **L1 PARKS it for human
     approval** exactly as `draft_email` did; only **Approve** resumes the run into a real send via
     the configured transport. No transport → `human_task` tail (invariant #5).
   - The kernel run-loop stamps `From` from `ChannelBinding.sender_identity` (#8) and **defaults an
     unset recipient to that same sender** (send-to-self review-in-your-own-inbox dogfood — a real
     send can then only ever reach the operator, never an unverified address).
   - `POST /commands/instantiate` accepts an optional `sender_identity` to set the email
     `ChannelBinding`, so a real run can send as that per-instance sender.
   - The swarm `SimAdapter` now simulates `send_email` (no real send in the synthetic wind-tunnel).
   - The lead-finder type's constraint changed from "draft email only; never send" to "outreach is
     sent only after explicit human approval (gated `send_email`)".

3. **Tests**
   - New: `packages/syscall/tests/test_email_transports.py` (SMTP transport handshake, STARTTLS,
     provider selection, `RUN_LIVE_EMAIL` gate, `_find_dotenv`).
   - New done-when tests in `api/tests/test_send_email_integration.py` (fake transport): lead-finder
     run → **park (no send)** → approve → transport called **exactly once** → settles `sent:True`;
     no transport → `human_task` tail; a second approve **never double-sends**.
   - Migrated the playbook/operator/swarm assertions from `draft_email` → `send_email`.

---

## LIVE PROOF (the point of the session)

Driven through the API end-to-end with `RUN_LIVE_EMAIL=1` + the founder's `SMTP_*` in `.env`, via
`scripts/_send_loop_live_proof.py` (`cd api && uv run python ../scripts/_send_loop_live_proof.py`).
The Approve step is the human gate — exactly what the dashboard's Approve button POSTs to
`/commands/approve`.

```
transport=smtp  sender=elplanito11@gmail.com
instantiated inst_founder_dogfood_1781946660 (ring L1, sender=elplanito11@gmail.com)
after trigger: state=parked  sends_so_far=0
approval card: syscall=send_email  to=elplanito11@gmail.com
  subject='Quick idea for [sim] sim_lead_1 Dental Clinic'
>>> APPROVING (the human gate) ...
after approve: state=settled  sends=1
=== REAL SEND RECEIPT ===
  message_id = <178194666095.61930.3102482248798944072@gmail.com>
  from       = elplanito11@gmail.com
  to         = elplanito11@gmail.com
  subject    = Quick idea for [sim] sim_lead_1 Dental Clinic
  accepted   = True
sends total  = 1 (must be 1)
run state    = settled
```

**What this proves:**
- **The gate is sacrosanct:** at L1 the run PARKS and `sends_so_far=0` — nothing left the system
  before a human Approve.
- **Approve → real send:** Gmail accepted the message over STARTTLS after App Password login
  (`sendmail` returned no refused recipients → `accepted=True`); the run then settled.
- **Exactly once:** one send for one approval; the adapter + gateway idempotency prevent double-send.
- **`message_id`** `<178194666095.61930.3102482248798944072@gmail.com>` (the Message-ID stamped on
  the outbound message and returned on the receipt).

**Inbox confirmation:** the founder should see the email in the `elplanito11@gmail.com` inbox
(send-to-self). This proof captures the SMTP-level acceptance + Message-ID; visual inbox confirmation
is the founder's one-glance step (the agent cannot read the founder's Gmail).

---

## Full gate (green before push)

Python:
```
ruff .................. All checks passed!
mypy --strict packages db tests ........ no issues (116 files)
mypy --strict api/src api/tests ........ no issues (13 files)
pytest (root) ......... 196 passed, 2 skipped       (live Hermes/promptfoo skipped)
pytest packages ....... 84 passed
pytest api ............ 41 passed
lint-imports .......... Contracts: 3 kept, 0 broken (lane fence intact)
```
Dashboard:
```
npm test .............. 22 pass / 0 fail   (incl. deriveSendPosture live/staged)
npm run build ......... success
```

---

## Honest verdict + known issues

- ✅ **Send loop closed and live-proven.** The first real outbound settle landed.
- ⚠️ **Recipient is send-to-self by default.** Phase-1 leads carry a contact *page* (`contact_url`),
  not an email address, so the outreach lands in the operator's own inbox to review/forward — or an
  explicit `target.review_recipient` / a real lead email when available. This is the honest Phase-1
  model, not a limitation to hide: the agent doesn't cold-email prospects directly yet.
- ⚠️ **Gmail rewrites `From` to the authenticated user**, so `EMAIL_FROM` must equal `SMTP_USERNAME`
  and the instance `sender_identity` should be that address (it is, for the dogfood). Multi-sender
  per-tenant identities are a later concern; the per-instance plumbing (#8) is already in place.
- ⚠️ **Demo seed still shows a `draft_email` card.** The `seed_demo` fixture in `api/.../state.py`
  is a static illustration of a parked approval and still uses `draft_email` (a still-valid
  registered syscall). Real lead-finder runs now emit `send_email`; the seed was left untouched to
  avoid rippling into many dashboard fixtures for a cosmetic demo difference.
- ⏭️ **Stretch deferred (honestly):** capturing the sent outreach's reply/bounce into a real
  `eval_case(origin="real")` was NOT done this session. The Step-D maturation machinery (G3,
  `packages/kernel/.../watch_maturation.py`) already exists to do it; wiring a reply-watch on a real
  send is the natural next step toward the ~100-settle milestone.
- 📌 **Operating milestone, not a coding one:** the BLUEPRINT §7 WIN needs ~100 real settles. This is
  settle #1. The remaining distance is dogfooding, not code.

⚠️ **Dogfood only:** Gmail's ~500/day limit and the shared-sender risk (#8) mean this path is for
the founder's own dogfooding, never bulk cold outreach.
