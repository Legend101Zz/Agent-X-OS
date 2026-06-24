# NEXT-SESSION PROMPT — Hormozi deep-dive → detailed HTML summaries

> Paste everything below the line into a fresh Claude Code session. It is self-contained:
> the new session starts cold and must rebuild context from these instructions + the
> checkpoint files it creates.

---

## MISSION

Turn me into someone who has genuinely **absorbed** Alex Hormozi's sales system — not skimmed it — and can apply it to my business, **Agent-X**. By the end, reading your output should be ≈ reading the three books for sales mastery, and I should be able to execute every offer / lead-gen / pricing move in my 60-day plan from first principles.

**Deliverable:** three long-form, deeply-analyzed HTML summaries (one per book), each **≥ 10 printed pages of real substance**, plus a short index page that ties them to my plan and a combined "Hormozi → Agent-X" cheat-sheet. Total read across the three ≈ 30–40 pages.

This is a long, multi-step task. **It MUST survive context loss** — if you get summarized or I `/clear`, a fresh session has to resume exactly where you stopped, never re-reading pages already done.

---

## STEP 0 — DO THESE BEFORE ANYTHING ELSE

1. **Invoke the `planning-with-files` skill.** This whole task is file-checkpointed for recovery. Honor its `task_plan.md` / `findings.md` / `progress.md` model.
2. **Invoke the `frontend-design` skill** before you build any HTML — I care about distinctive, non-generic design (no AI-slop defaults).
3. **Recovery check first:** if `memory.md` / `task_plan.md` / `progress.md` already exist in the working dir below, READ them and **resume from the next unstarted step** — using the local `memory.md` so you don't depend on the SSD being mounted. Say out loud: *"Resuming at Book X, pages Y onward,"* and do not restart or re-read completed pages.

---

## CONTEXT TO ABSORB (read, don't summarize — so your output is applied & consistent)

- `/Volumes/Mrigesh SSD/Startup/Agent-X-OS/docs/AGENTX_60DAY_PLAN_2026-06-23.html` — **my 2-month plan. Every summary must connect to this** (the lead-finder GTM, the CA mandate, the kill criteria, the dogfood engine).
- `/Volumes/Mrigesh SSD/Startup/Agent-X-OS/docs/sales/01_grand_slam_offer.md` … `08_seven_day_action_plan.md` — my existing **applied** playbook (already careful to never fabricate quotes — match that rigor).
- `/Users/comreton/Downloads/Alex Books/Book Summaries/hormozi_book_summaries.html` — existing **condensed** summary. Yours must go **far deeper** than this.
- `/Users/comreton/Downloads/Alex Books/agent_x_sales_playbook.html` — existing visual playbook (aesthetic reference).

## SOURCE BOOKS (read from these PDFs, in this order)

| # | Book | File | Pages |
|---|------|------|-------|
| 1 | **$100M Offers** | `/Users/comreton/Downloads/Alex Books/_OceanofPDF.com_100_million_offer_-_Alex_Hormozi.pdf` | 206 |
| 2 | **$100M Leads** | `/Users/comreton/Downloads/Alex Books/_OceanofPDF.com_Leads_-_Alex_hormozi.pdf` | 390 |
| 3 | **$100M Money Models** | `/Users/comreton/Downloads/Alex Books/_OceanofPDF.com_00M_Money_Models_How_To_Make_Money_-_Alex_Hormozi.pdf` | 188 |

Order rationale: it's how my playbook builds — the **Offer** first, then how to get **Leads** to it, then the **Money Model** that sequences pricing.

---

## SSD RESILIENCE — KEEP ALL MEMORY ON LOCAL DISK (read carefully)

The source books and your working files are on **local disk** (`/Users/comreton/Downloads/…`). The context files in STEP "CONTEXT TO ABSORB" are on an **external SSD** (`/Volumes/Mrigesh SSD/…`) **whose connection can drop mid-session.** So:

- **Never store recovery/working files on the SSD.** All checkpoint + memory files live **locally** in the working dir below.
- **Cache the SSD context locally up front.** Right after you read the SSD files, write their essentials into `memory.md` (below). From then on, work from `memory.md` — if the SSD disconnects, you can continue uninterrupted.
- If **any** read from `/Volumes/Mrigesh SSD/…` fails (SSD unplugged), **do not stop** — fall back to `memory.md`, note "SSD unavailable — continuing from local memory" in `progress.md`, and carry on.

## WORKING DIRECTORY + CHECKPOINT FILES

Create and work inside (LOCAL disk): `/Users/comreton/Downloads/Alex Books/Detailed Summaries/`

Maintain there (all local — none on the SSD):
- **`memory.md`** — the **SSD-context cache + cross-session recovery note**. At session start, populate it with the digest of the 60-day plan (its sections, the lead-finder GTM, the CA mandate, the kill criteria, the dogfood engine) + the essence of `docs/sales/01–08` (offers, scripts, objection ACA, money model). This is what lets you keep working if the SSD drops. **It is temporary scratch — DELETE it at the very end** (see Definition of Done).
- **`task_plan.md`** — the phases (B1 read → B1 HTML → B2 read → B2 HTML → B3 read → B3 HTML → index/cheat-sheet), acceptance criteria, and which phase is current.
- **`progress.md`** — a precise ledger and the **recovery anchor**. After **every** read-chunk and every file write, update it, e.g.:
  `Book 1 ($100M Offers): pp.1–20 ✓, 21–40 ✓ … next: 41–60. HTML: not started.`
- **`findings.md`** — your distilled raw notes per book as you read: frameworks named **exactly**, verbatim memorable lines **with page numbers**, the real examples/numbers Hormozi uses, and "apply-to-Agent-X" ideas. **The HTML is built FROM findings.md**, so make it rich.
- the **3 book HTML files** + **`index.html`** (the durable deliverables — these stay).

---

## HOW TO READ (PDF limits — important)

The Read tool **requires a `pages` range for PDFs > 10 pages and reads max 20 pages per call.** So:

- Read in **≤ 20-page chunks, in order.** Never attempt a whole book in one call.
- After each chunk: append distilled notes to `findings.md`, then update `progress.md` with exactly what's done and what's next.
- Skim front matter / acknowledgements quickly; spend the depth on content chapters.
- If a page's text extraction looks garbled, re-read it as a rendered page and transcribe carefully.
- **Quote only what is actually on the page.** Mark paraphrases as paraphrase. **Never fabricate a quote or a statistic** — cite the page number for every verbatim line. (My existing files hold this standard; yours must too.)

---

## ONE BOOK AT A TIME (with a checkpoint stop)

Fully finish a book — **read all chunks → write its HTML → mark complete in `progress.md`** — BEFORE starting the next.

After each book's HTML is done, **STOP** and report:
1. The file path.
2. A 5-line *"what you can now DO"* summary (concrete sales actions, not a recap).
3. What's next.

Then **wait for me to say "continue"** before the next book. This keeps context lean and lets me review. (If I `/clear` between books, the recovery protocol picks it up.)

---

## WHAT EACH HTML MUST CONTAIN (the depth bar — ≥ 10 pages)

1. **Hero** — book title, Hormozi's one-sentence thesis, and the single line I should tattoo on my brain.
2. **The core engine** — the book's master framework/equation rendered visually (e.g. the Value Equation; the Core Four; the 4 offer types). Explain each variable in plain English.
3. **Chapter-by-chapter (or section-by-section) deep summary** — for EACH:
   - the concept in plain English;
   - Hormozi's **exact terminology**;
   - the **real example** he uses in the book (with the numbers);
   - the **verbatim line worth memorizing** + page number;
   - an **`APPLY TO AGENT-X`** callout box mapping it to my lead-finder and/or CA mandate, and naming which `docs/sales/0X` file or which **60-day-plan section** it powers.
4. **Deep Analysis** (this is the part that makes it more than a recap): how the frameworks interlock; where Hormozi contradicts common advice and why; the 3–5 ideas that matter MOST for a **technical, first-time founder with no sales experience selling cross-border (India → US/UK)**; and the **specific failure modes I'm most likely to hit** given my plan.
5. **Mistakes Hormozi explicitly warns against** (with pages).
6. **Mastery checklist** — "can I now do X?" items I can self-test against.
7. **Quick-reference cheat card** — the scripts/numbers/sequences I'd want on one screen.

Be **opinionated and concrete**, not generic. If a concept is already used in my `docs/sales/` files, say where, and deepen it rather than repeat it.

---

## DESIGN

Use the `frontend-design` skill. Make the three books **visually distinct** (e.g. a signature accent color per book) yet **cohesive as a set**, and in the same spirit as my 60-day plan's aesthetic. Self-contained HTML (inline CSS, system-safe Google fonts), responsive, comfortable for long-form reading, with strong typographic hierarchy. Respect `prefers-reduced-motion`.

---

## DEFINITION OF DONE

- ✅ 3 HTML summaries, each genuinely **≥ 10 pages** of substance, every chapter mapped to Agent-X.
- ✅ 1 `index.html` linking all three + a combined **"Hormozi → Agent-X" cheat-sheet** (the whole system on one page: offer + lead magnet + Core Four + objection ACA + money model + kill criteria, each pointing to the relevant plan section).
- ✅ `progress.md` shows all three books complete, with page ledgers.
- ✅ I can read the set in ~30–40 pages and apply the entire Hormozi system to my 60-day plan.
- ✅ **Cleanup:** once everything above is verified, **DELETE `memory.md`** (it was temporary SSD-cache scratch). Keep the HTML deliverables; `task_plan.md` / `progress.md` / `findings.md` may also be removed if I confirm, but `memory.md` goes regardless.

---

## START HERE

1. Invoke `planning-with-files`; do the recovery check (read local `memory.md` if present).
2. Read the SSD context files (60-day plan, `docs/sales/`, the two existing summary HTMLs) **and immediately cache their essentials into local `memory.md`** so the rest of the task survives an SSD disconnect.
3. Write `task_plan.md`.
4. **Confirm your plan back to me in ~8 lines** (phases, local working dir, SSD-cache + delete-at-end note, order, checkpoint cadence) **before** you read the first chunk of Book 1.

Then begin Book 1 ($100M Offers), 20 pages at a time, logging as you go.
