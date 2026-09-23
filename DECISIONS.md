# Decisions

## Requirements prioritized

The brief names seven required criteria: FICO, PayNet, minimum time in business, min/max loan
amount, equipment types, geographic restrictions, industry exclusions. All seven are modelled as
first-class catalog fields (`engine/catalog.py`) and evaluated for every lender — none of them
is a special case in the engine, they're just rows in a policy like any other rule.

Priority order, most to least:

1. **The seven required criteria, correct per-lender**, over covering every line of every PDF —
   including lender-specific wrinkles (Stearns' No-PayNet table, Apex's medical-professional
   programs, Citizens' per-asset term bands, Falcon's trucking overlay). This is what the
   matching engine is actually graded on.
2. **"Any other features you think are important,"** where they change eligibility, not just
   describe the deal: guarantor derogatory history, revolving-credit utilization and comparable
   business debt, entity type / corp-only structuring, US citizenship, CDL (trucking), licensed-
   practitioner status (medical). The catalog has 49 fields total; most exist because a specific
   lender's PDF gated a program on that exact thing.
3. **Extensibility over one-time completeness.** The brief grades "easy to add/edit rules, easy
   to add lenders" as heavily as matching accuracy — so time went into two generic registries
   (catalog + operators) and a rule editor built off them, rather than more special-cased rules.
4. **Deprioritized**: rate/pricing calculation, per-asset term/mileage matrices beyond age bands,
   bureau-specific FICO variants, multi-pass extraction for very long documents (why: see
   Simplifications).

## PDF parsing → lender policies

`upload → extract text → extract policy (model call) → validate → draft version → human review
→ publish`.

- **A model key is mandatory — `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. There is no key-less
  mode.** Without one, "Onboard from PDF" fails immediately with a clear "no model is connected"
  error. Nothing falls back to pre-parsed or canned data — that would defeat the point of
  demonstrating requirement #1 ("parses and normalizes lender guidelines"). The two live
  extractors (Anthropic `messages.parse`, OpenAI `responses.parse`) share one prompt and one
  schema, generated from the live field catalog, so a field added to the catalog is usable by
  the extractor with no prompt edit.
- A third implementation, `RecordedPolicyExtractor`, replays a saved response — **it is test
  infrastructure only**, wired in via monkeypatch in `tests/test_ingestion.py`, never reachable
  from the running app or selectable through configuration.
- **Human review is the design, not a fallback.** Extraction produces a *draft*; every extracted
  rule is re-validated by the engine's own `Rule` model, and anything it can't express is dropped
  to a review checklist instead of guessed. Nothing extracted is ever evaluated until published.
- **Measured, not assumed:** `tests/fixtures/extractions-live/` holds real OpenAI responses for
  all 5 PDFs, and `test_live_extractions.py` asserts the extracted policy agrees with the
  hand-modelled seed on eligibility for 20/20 sample-application × lender cases (tier position
  16/20 — the 4 misses are defensible structural judgement calls, exactly what the review
  checklist exists for).
- **`make seed` loads only 4 of the 5 lenders.** Stearns Bank is deliberately left out
  (`app/seeds/policies.py:SEEDED_LENDERS`) so onboarding it from its PDF is the first thing to do
  with the running app — the extraction pipeline gets demonstrated, not just asserted by a seed
  file. Stearns was the safest one to hold back: the live extractor agrees with it on tier
  position too (unlike Citizens and Falcon), and its PDF is exactly what the recorded-fixture
  test above already exercises — a genuinely imperfect extraction (a dropped corp-only table, an
  unmappable field) resolved through review, not hidden.

## Applications → underwriting

`validate completeness → derive features → evaluate each lender → rank → persist`, as plain
functions in `services/underwriting.py`. Two drivers call the same functions, so behaviour can't
diverge:

- **Hatchet is optional.** With `HATCHET_CLIENT_TOKEN` set, `workflows/underwriting.py` fans out
  one child workflow per lender (true parallelism, each with its own retries via
  `return_exceptions=True`, so one lender's exhausted retries become an "error" result rather
  than failing the run). **Without a token — or if Hatchet is configured but unreachable — the
  exact same step functions run in-process on the API server instead, one lender after another.**
  Either way the result is identical; the UI shows which mode ran (`sync` / `hatchet`).
- **Policies are data, not code.** `Lender → PolicyVersion (draft|published|archived) →
  Program[] (ranked) → Rule[] (field, operator, value, severity, applies_when)`. Editing a
  threshold is a database update, not a deploy. Hard rules decline; soft rules only lower score.
  `applies_when` makes a rule/program conditional; `any_of` passes on any one alternative.
- **Fit score (0–100):** `40 tier + 40 headroom + 20 soft preferences`. Tier = position of the
  matched program among ones the borrower could apply for. Headroom = how far numeric minimums
  are cleared. Ineligible lenders score 0 and rank by near-miss ratio.
- **The engine is a pure library** (`backend/app/engine`) with no DB/API/workflow imports
  (test-enforced) — Hatchet and FastAPI are thin wrappers over it, which is also why the sync
  fallback above is free rather than a second implementation.

## Simplifications

- No authentication (single-user internal tool).
- No rate/payment calculation — rates are stored and displayed, not computed.
- Field catalog lives in code, not a DB table, so `derive_features` stays the single source of
  truth a table could drift from.
- Uploaded PDFs on local disk (`UPLOADS_DIR`), not object storage.

## With more time

- **Authentication and authorization.** Currently a single-user internal tool with no login.
  Would add auth and separate roles — a broker who submits applications and runs underwriting
  vs. an underwriter/admin who edits lender policies and publishes them.
- **A proper `Business` entity shared across applications.** Today `Business` is embedded 1:1
  in each `LoanApplication` (`models/application.py`), so a repeat applicant is re-entered from
  scratch every time. Pulling it out into its own entity that multiple applications reference
  would let a business's profile and application history persist and be reused.
- **Chunked, multi-pass extraction** for guideline packs too long for one model call — today's
  extractor makes one pass per document (see PDF parsing above).
- **Handling already-underwritten applications when a policy changes.** Results are immutable
  and versioned by design (a match result stores the exact policy version it was run against),
  so publishing a new version never silently rewrites past decisions — but there's also nothing
  that reconciles the two today. An application matched under v1 has no indicator that the
  lender's policy has since moved to v2, no way to see whether it would now match differently,
  and no bulk "re-run everything affected by this publish" action. With more time: flag
  completed applications as "policy has changed since this run," a diff view between two
  versions showing which past applications would newly qualify or newly fail, and an explicit
  re-run (not a silent overwrite — a new run, same immutability guarantee).
- Pricing engine; full Citizens term/mileage matrices; bureau/PayNet integrations; audit log
  with users; record Anthropic live extractions alongside the OpenAI ones in the same
  regression suite.
