# Phase 2 multi-service/source pilot — technical GO for review

27 October 2026. Native run 20261027_234148_976bc9dc. **56/56 bounded checks passed.** Production remains unauthorized; all ten facts remain unapproved test fixtures. Phase 1 code and native results remain hash-identical. Stop for user review.

## Implementation and evidence

The extension retains Phase 1 and adds independent service/topic slots, multi-source validity checks, per-slot hybrid retrieval, sequence/dependency completeness and grouped immutable bilingual views. No question/answer lookup, Qwen, translation engine, new framework or model was introduced.

| Service | Facts | Source / locator | Evidence unit |
|---|---|---|---|
| axis_pay | F0010, F0011, F0012 | daily_brief/axis_wallet_sales_guide.pdf; {"type": "page", "page": "1", "line_start": null, "line_end": null, "source_segments": null} | source-verified-axis-guide-activation-198dffbc8ab1 |
| qnb_wallet | F0073 | KnowledgeBase/Articles/Wallets_ART.md; {"type": "lines", "page": null, "line_start": 161, "line_end": 165, "source_segments": null} | KU-3df6287f9511c6cd |
| azimut | F0037, F0038, F0039, F0040, F0041, F0042 | KnowledgeBase/Articles/AZIMUT_ART.md; {"type": "lines", "page": null, "line_start": 434, "line_end": 434, "source_segments": null, "exact_assertion_lines": [434]} | KU-6493927fb4e6b40f |

Exact source/body hashes, Arabic evidence, English drafts, conditions, dependencies, order and pending approvals are in fixture_data/definition.json. All three original document hashes and Markdown quote locations were checked. The original 82 facts and approval records were not edited. No new source authority is inferred.

QNB is limited to its conditional minimum funding statement; its provider tariff conflict, opening fees and balance disposition remain held. Azimut covers app navigation and conditional branch visit, not a document inventory or complete KYC procedure. AXIS retains only F0010–F0012. All other facts remain outside this fixture.

## Actual results and completeness

50 main cases (24 frozen Phase 1 questions plus 26 new cases), two setup turns and six integrity checks. No frozen Phase 1 expectation was changed. Source-based expected fact sets were authored before final execution and are separate from retrieval output; this is not independent human business acceptance.

{
  "complete_correct": 32,
  "correct_partial": 10,
  "correct_hold": 13,
  "incorrect_or_execution_failure": 0
}

Full questions, expected facts, actual answers/citations, slot gaps and HTTP/stage timings are retained in native_results/20261027_234148_976bc9dc/RESULTS.json. CLAIM_AND_SLOT_REVIEW.json checks every emitted view against its exact source-bound record; no critical unsupported claim was observed in the fixed set. Complete procedures retain all six steps and their order. A missing/revoked middle step holds the whole procedural slot; supported facts from other services can still be returned.

Main questions alone: {"complete_correct": 32, "correct_partial": 6, "correct_hold": 12}. The aggregate counts above also include five HTTP integrity mutations; the sixth integrity check rejects normal-mode construction. No recorded HTTP timeout or execution failure occurred.

### S07

Compare the initial activation funding for AXIS and QNB.

UNAPPROVED TEST FIXTURE — approvals pending.

AXIS Pay:
Activation is immediate upon depositing a minimum of 20 EGP into the customer account.
The initial AXIS Pay deposit of at least EGP 20 remains in the customer’s balance.

QNB Wallet:
QNB Wallet activation is immediate provided the customer deposits at least 20 EGP.

Only the selected financial facts and app navigation are covered; this is not a complete KYC or eligibility checklist.

Facts: F0011, F0012, F0073; complete=True; HTTP 519.19 ms. Exact per-claim original source citations are in the ledger.

### S08

AXIS و QNB اقل ايداع للتفعيل كام؟

اختبار معزول غير معتمد؛ الموافقات معلقة.

AXIS Pay:
التفعيل لحظي عند إيداع 20 جنيه كحد أدنى لحساب العميل.
إيداع مبلغ 20 جنيه مصري كحد أدنى (يستقر في رصيد العميل).

QNB Wallet:
تفعيل QNB Wallet يكون لحظيًا بشرط إيداع حد أدنى:

**20 جنيه**

النطاق هو الحقائق المالية المختارة وخطوات التطبيق فقط، وليس قائمة كاملة بشروط الفتح أو المستندات.

Facts: F0011, F0012, F0073; complete=True; HTTP 533.63 ms. Exact per-claim original source citations are in the ledger.

### S03

Explain Azimut registration steps in MyFawry.

UNAPPROVED TEST FIXTURE — approvals pending.

Azimut:
Open the MyFawry app.
Enter the wallet.
Select My Savings.
Select Add Fund.
Follow the registration steps.
Visit the nearest Fawry Plus branch when the application directs the customer to do so.

Only the selected financial facts and app navigation are covered; this is not a complete KYC or eligibility checklist.

Facts: F0037, F0038, F0039, F0040, F0041, F0042; complete=True; HTTP 245.23 ms. Exact per-claim original source citations are in the ledger.

### S04

خطوات تسجيل ازيموت من التطبيق ايه؟

اختبار معزول غير معتمد؛ الموافقات معلقة.

Azimut:
يتم فتح تطبيق MyFawry
ثم الدخول إلى المحفظة
ثم مدخراتي
ثم إضافة صندوق
ثم اتباع خطوات التسجيل
وزيارة أقرب فرع فوري بلس عند توجيه التطبيق للعميل.

النطاق هو الحقائق المالية المختارة وخطوات التطبيق فقط، وليس قائمة كاملة بشروط الفتح أو المستندات.

Facts: F0037, F0038, F0039, F0040, F0041, F0042; complete=True; HTTP 252.77 ms. Exact per-claim original source citations are in the ledger.

### S11

What are the opening fees and initial deposits for AXIS and QNB?

UNAPPROVED TEST FIXTURE — approvals pending.

AXIS Pay:
Opening the wallet has no subscription fee: 0 EGP.
Activation is immediate upon depositing a minimum of 20 EGP into the customer account.
The initial AXIS Pay deposit of at least EGP 20 remains in the customer’s balance.

QNB Wallet:
QNB Wallet activation is immediate provided the customer deposits at least 20 EGP.

Unavailable or held: qnb_wallet / opening_fee

Only the selected financial facts and app navigation are covered; this is not a complete KYC or eligibility checklist.

Facts: F0010, F0011, F0012, F0073; complete=False; HTTP 810.48 ms. Exact per-claim original source citations are in the ledger.

Two dialogue sequences test AXIS→QNB→initial-deposit comparison and Azimut workflow→conditional branch visit→QNB. Isolated follow-ups have no borrowed session history. Explicit provider/topic clauses retain separate fact sets. Holds and partial answers are not counted as complete successes.

## Timing and resources

{
  "n": 32,
  "p50_ms": 487.59940080344677,
  "p95_ms": 843.0101053789258
}

- ar: {"n": 8, "p50_ms": 538.5726001113653, "p95_ms": 857.8271098434925, "mean_stages_ms": {"interpretation_ms": 4.799500573426485, "source_verification_ms": 1.1535994708538055, "retrieval_ms": 526.131562422961, "fact_selection_ms": 0.006162095814943314, "validation_and_assembly_ms": 0.3284378908574581}}
- en: {"n": 24, "p50_ms": 467.6679000258446, "p95_ms": 795.424060896039, "mean_stages_ms": {"interpretation_ms": 6.211512411634128, "source_verification_ms": 1.1138212867081165, "retrieval_ms": 431.96309156094986, "fact_selection_ms": 0.005408811072508494, "validation_and_assembly_ms": 0.3913417458534241}}

Startup/snapshot time: 4636.28 ms. Process peak working set: 197.81 MiB. Recorded main/mutation process CPU: 390.62 ms; setup/startup excluded. Shared BGE/Ollama model CPU/RAM is not attributable to this process. Query caches are cleared per supported slot, no answer cache is used, and all three private source copies are hashed each request. Generation/translation calls: zero.

PERFORMANCE.json preserves the 13 same-question Phase 1/2 pairs. These are sequential observations on the same server at different times, not randomized equal-load measurements. Phase 2 verifies three documents and may retrieve multiple slots independently; do not claim a formal improvement from different work. This small test does not certify production p95, concurrency or the 20% target. The original 10-second p95 objective remains a later gate.

Same-question comparison: the 13 complete Phase 1 questions averaged 270.79 ms in Phase 1 and 607.69 ms in Phase 2. Phase 2 was slower on these observations; it verifies three source files and performs separate topic-slot embeddings. No 20% speed improvement is established. Arabic output statistics include mixed-language questions answered in Arabic.

## Corrections and preservation

The initial local run 20261027_184826_b033a390 is retained with its failures. Only two necessary corrections followed: narrowly scoped deposit-fee parsing, and exact-view workflow compatibility. The original procedural checker rejects the harmless reviewed suffix “to do so” as residual vocabulary. A fingerprint-bound adapter normalizes only that grammatical anaphor for the unchanged checker; actual answer wording stays byte-identical. Added login, missing wallet, reordered steps and unconditional visit still fail (WORKFLOW_COMPATIBILITY_CHECKS.json). No arbitrary generated text uses this adapter. Numerical and procedural validator files remain byte-identical.

Source changes/deletion, test eligibility revocation, reviewed-language fingerprint revocation, attempted production flag and normal-mode entry are covered. Valid independent services remain answerable when another source/slot is held. Native before/after guards confirm production code/settings, active pointer, original selected sources and historical backup metadata unchanged. No originals, caches, document embeddings, production accounts, portal requests, restarts or frozen reports were modified.

## Decision and limits

Technical GO to review a larger approved-fact pilot, not authorization to build it. The fixed experiment shows source-controlled multi-service/topic and ordered navigation assembly across three independent sources, with no observed correctness regression in its evaluated cases.

Remaining limits: ten facts only, rule-based interpretation, incomplete original business coverage, unresolved policy conflicts, pending fidelity/currentness approvals, no human-independent accuracy sign-off and no production/load certification. Reusable reviewed language views and dependency-complete evidence are still prerequisites for broader coverage. Unknown policy and missing evidence remain unknown; successful abstention is not coverage.

Executable files and Windows instructions are in README.md. No Phase 3, migration, broad benchmark or deployment was started.
