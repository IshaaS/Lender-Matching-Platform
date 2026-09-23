# Lender Policy Normalization & Architecture Mapping

This document details how raw lender PDF underwriting guidelines are mapped into structured, policy-as-data rules evaluated by the Lender Matching Platform engine.

## Policy-as-Data Architecture

The platform separates policy definitions from evaluation code. Policies are JSON/relational structures composed of:
1. **Lender Restrictions**: Lender-wide hard rules (e.g. prohibited industries, excluded states, minimum guarantor ownership).
2. **Programs & Tiers**: Ordered credit tiers (`rank = 1, 2, 3...`) with program-specific rules, decision modes (`automatic` vs `manual_review`), and required document checklists.
3. **Rules**: Individual logic constraints consisting of:
   - `field`: Target feature key (e.g., `fico_score`, `equipment_is_titled`).
   - `operator`: Standard comparison operator from the operator registry (`gte`, `lte`, `in`, `not_in`, `between`, `is_true`, `subset_of`).
   - `value`: Target value or threshold.
   - `severity`: `"hard"` (causes rejection if failed) or `"soft"` (preference score adjustment).
   - `applies_when`: Conditional logic determining if the rule applies to the current application.
   - `message_template`: Custom rejection message with placeholders `{actual}` and `{expected}`.
   - `provenance`: Traceability fields (`source_document`, `source_page`, `source_quote`).

---

## 5 Seed Lender Policies Summary

### 1. Stearns Bank (`EF Credit Box 4.14.2025.pdf`)
- **Structure**: 4 credit tiers (Tier 1–4) for standard PayNet applicants, plus an alternative 4-tier table for applicants without PayNet.
- **Key Rules**:
  - Minimum FICO (725 / 712 / 700 / 680 with PayNet; 735 / 720 / 710 / 690 without PayNet).
  - Minimum time in business (2 years for Tiers 1–3, 3 years for Tier 4).
  - Excluded states: `CA`, `NV`.

### 2. Apex Commercial Capital (`Credit-Box-Broker-2025.pdf`)
- **Structure**: General programs (A+, A, B, C) and specialized Medical programs (A, B, C).
- **Key Rules**:
  - Medical vs General industry branching via `applies_when` conditions (`is_medical`).
  - Tiered revolving credit availability thresholds (75% for A+, 50% for A).
  - Down payment requirements (0% for A+, 10% for C).

### 3. Advantage+ Financing (`Advantage++Broker+2025.pdf`)
- **Structure**: Non-trucking equipment financing ($10k–$75k) split into Established Business vs Start-Up programs.
- **Key Rules**:
  - `is_trucking = False` restriction.
  - Startup detection (`is_startup = True` for TIB < 2 years).
  - Soft preference rules (e.g. 7 years trade history, 80% comparable credit).

### 4. Citizens Bank (`2025 Program Guidelines UPDATED.pdf`)
- **Structure**: Tier 1 (App Only), Tier 2 (Start-Up), Tier 3 (Full Financials / Manual Underwriting).
- **Key Rules**:
  - Excluded state: `CA`.
  - Excluded industries: `cannabis`.
  - Tier 3 configured with `decision_mode="manual_review"`: applicants with FICO 660–689 or complex financials qualify for manual underwriting instead of auto-approval.
  - Equipment age vs term caps (max 60m for equipment > 10 years old).

### 5. Falcon Equipment Finance (`Falcon_Guideline_Summary.pdf`)
- **Structure**: Standard Program vs Trucking Program (A/B credits only).
- **Key Rules**:
  - CDL requirement for trucking applications.
  - PayNet score requirements (675 for Standard, 700 for Trucking).
  - 10% down payment required for titled transportation equipment.

---

## Multi-Equipment Feature Derivation & Rules

When applications contain multiple equipment items:
- `equipment_is_titled`: Evaluated as `True` only if ALL equipment items are titled (`all(is_titled)`).
- `equipment_mileage`: Evaluated across all items or per category (`equipment_mileage_<category>`).
- `equipment_categories`: Validated using `subset_of` operator against lender allowed category lists.
- Order Independence: Equipment array ordering (`[item_A, item_B]` vs `[item_B, item_A]`) produces identical derived features and evaluation outcomes.

---

## Decision States & Ranking Logic

### Decision States
- `eligible`: Automatic approval cleared all hard rules in an automatic program.
- `manual_review`: Cleared all hard rules in a manual underwriting program (e.g. Citizens Bank Tier 3).
- `needs_information`: Required applicant features are missing (`None`).
- `ineligible`: Failed one or more hard rules.
- `error`: System evaluation error.

### Program & Lender Ranking Precedence
1. `decision`: `eligible` > `manual_review` > `needs_information` > `ineligible`.
2. `fit_score`: Higher fit score (0–100) breaks ties among lenders with equal decision precedence.
3. `version_number`: Latest published policy version breaks ties.
