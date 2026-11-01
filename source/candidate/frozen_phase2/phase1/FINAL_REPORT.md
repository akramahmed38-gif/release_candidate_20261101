# Three-fact AXIS source-view pilot — technical GO for review

27 October 2026. Native run `20261027_182451_e6a97063`. **28/28 bounded checks passed.** This demonstrates the authorized three-fact technical fixture; it does not approve its facts, authorize a broader implementation, or establish production readiness. Stop for user review.

## Observed correctness

24 main requests included 13 complete supported answers, two correctly scoped partial answers and nine unavailable answers. Four additional source/eligibility/isolation checks passed. Two separate setup turns were retained. Actual main and mutation responses used private loopback HTTP; normal-mode rejection was a constructor check. No exact question-to-answer lookup or Qwen generation was used.

Offline inspection verified each emitted business statement is its exact source-bound Arabic or pending-review English representation, and each has the correct fact/source/page citation. No unsupported financial assertion was observed in these cases. The minimum 20 EGP deposit is conditional activation funding and remains balance; it is not rendered as a fee. Financial-only scope is disclosed, without implying a complete KYC checklist.

Expected fact sets were fixed before execution and include additional paraphrases. This is source-based technical checking, **not independent human fidelity/currentness approval or broad unseen-language certification**. General interpretation remains rule-based and bounded.

## Actual answer examples

### E04

Explain AXIS's opening fee, minimum initial deposit and whether that deposit stays in my balance.

UNAPPROVED TEST FIXTURE - approvals pending.

Opening the wallet has no subscription fee: 0 EGP.

Activation is immediate upon depositing a minimum of 20 EGP into the customer account.

The initial AXIS Pay deposit of at least EGP 20 remains in the customer’s balance.

Financial test scope only; this is not a complete KYC or eligibility checklist.

Citation: `daily_brief/axis_wallet_sales_guide.pdf`, page 1; facts F0010, F0011, F0012. HTTP 305.17 ms.

### A03

فتح محفظة اكسيس عليه رسوم؟ وأقل إيداع أولي كام وهل بيفضل في الرصيد؟

اختبار معزول غير معتمد؛ الموافقات ما زالت معلقة.

فتح المحفظة مجاني تمامًا بـ 0 جنيه رسوم اشتراك.

التفعيل لحظي عند إيداع 20 جنيه كحد أدنى لحساب العميل.

إيداع مبلغ 20 جنيه مصري كحد أدنى (يستقر في رصيد العميل).

نطاق الاختبار هو المعلومات المالية دي فقط. باقي شروط الفتح والمستندات خارج النطاق.

Citation: `daily_brief/axis_wallet_sales_guide.pdf`, page 1; facts F0010, F0011, F0012. HTTP 319.9 ms.

### M01

AXIS activation بكام وهل الفلوس بتفضل في balance؟

اختبار معزول غير معتمد؛ الموافقات ما زالت معلقة.

فتح المحفظة مجاني تمامًا بـ 0 جنيه رسوم اشتراك.

التفعيل لحظي عند إيداع 20 جنيه كحد أدنى لحساب العميل.

إيداع مبلغ 20 جنيه مصري كحد أدنى (يستقر في رصيد العميل).

نطاق الاختبار هو المعلومات المالية دي فقط. باقي شروط الفتح والمستندات خارج النطاق.

Citation: `daily_brief/axis_wallet_sales_guide.pdf`, page 1; facts F0010, F0011, F0012. HTTP 260.36 ms.

### N05

What is the AXIS opening fee and what are withdrawal fees?

UNAPPROVED TEST FIXTURE - approvals pending.

Opening the wallet has no subscription fee: 0 EGP.

Unverified in this test: withdrawal

Financial test scope only; this is not a complete KYC or eligibility checklist.

Citation: `daily_brief/axis_wallet_sales_guide.pdf`, page 1; facts F0010. HTTP 287.83 ms.

Source SHA-256: `198dffbc8ab1ce2887356e91fab9d241ea3f08c35216d2b32a1062e64439abce`. Evidence unit `source-verified-axis-guide-activation-198dffbc8ab1`; unit text SHA-256 `779db86d8e0f6b628bf7a5a5da67273da01490af86a8137ec6cabcb0a525774b`. Full per-fact citations and all expected/actual records are in `native_results/20261027_182451_e6a97063/RESULTS.json`.

## Measured latency and resources

Complete-correct responses: 13 observations, HTTP p50 **266.04 ms**, p95 **311.06 ms**. Startup/snapshot/model verification: **5.159 s**, separate from request latency. Query caches are cleared before supported requests; no answer or translation cache is used. Unsupported holds are excluded from these complete-answer latency figures.

- ar: 4 complete-correct samples; HTTP p50 281.66 ms, p95 315.97 ms.
  Mean stage times: interpretation_ms 2.97 ms, source_and_test_authorization_ms 0.61 ms, retrieval_ms 272.89 ms, validation_and_assembly_ms 0.39 ms.
  Mean embedding 268.04 ms, resource wait 0.13 ms.
- en: 9 complete-correct samples; HTTP p50 265.33 ms, p95 297.05 ms.
  Mean stage times: interpretation_ms 5.94 ms, source_and_test_authorization_ms 0.63 ms, retrieval_ms 247.03 ms, validation_and_assembly_ms 0.25 ms.
  Mean embedding 242.13 ms, resource wait 0.14 ms.

Measured Python/Chroma peak working set: **195.61 MiB**. Process CPU across recorded main/mutation requests: **171.88 ms** (setup/startup excluded; per-request values retained). Shared Ollama embedding-model CPU/RAM is not attributable from this process measurement. No inference-generation queue, prompt or decode work occurred.

This small sequential, three-row/one-source-vector test does not establish a 10-second production p95 SLA, throughput, concurrency capacity or an accuracy-preserving 20% improvement. Earlier failed generation cases are not an equivalent correct-answer baseline.

## Retrieval and controls

Real BGE-M3 query embeddings, Chroma cosine retrieval and the existing BM25 scorer were exercised. The three facts share one reused, exact source-page vector; no three independent fact embeddings are claimed. The repaired generation's explicit base collection is used for its unchanged anchor, with base-manifest hash, source hash, page and non-supersession checks. Thresholds remain 0.34 semantic, 0.24 final and one keyword overlap. No missing-anchor fallback or weakened validator was added.

The first two initialization failures remain preserved (`20261027_181229_bbde86c5`, `20261027_182134_1da58d66`). They exposed a fixture-adapter error: unchanged source vectors reside in the repair overlay's base collection rather than its delta collection. The adapter was corrected before the completed run; no model tuning or fact revision occurred.

Withdrawal fees, documents, QNB, ADIB, Vodafone, ongoing-balance rules and ATM deposit tariffs returned unavailable. Mixed opening-fee/withdrawal and activation/KYC questions retained only supported facts and were partial. Follow-up isolation and explicit service switching passed.

Changing the private source copy invalidated all answers/citations. Revoking F0012 removed that statement and its citation and made the answer partial. A production-use flag was rejected; normal-mode construction was rejected. No human/business approval was inferred. Original approval records and the 82-fact inventory remain hash-identical.

The numerical validator remains byte-identical: `9eb736461247aaa7f89347bb8284113c9bd51b5d3e6f954b31b4e4d665ac2848`. Code-swap, channel-percentage-swap and deposit-as-fee rejection probes passed. Actual Arabic cases passed. Procedural validators remain unchanged; no procedural fact is in this fixture, so broader workflow acceptance is not claimed.

Native before/after preservation checks passed for the production code/configuration, active pointer, original source and protected historical backup metadata. No Qwen calls, translations, document embeddings, OCR, production requests, activation or restart occurred.

## Decision and executable boundary

**Technical GO to review this three-fact approach; production NO-GO.** No unresolved failure remains in the fixed bounded suite. Broader interpretation, independent human review, currentness approvals, realistic corpus/load and end-to-end portal integration remain unverified. Do not expand automatically.

Candidate code: `pilot_engine.py` (interpretation/selection/assembly), `native_backend.py` (private native retrieval), `run_pilot.py` (loopback executable/fixed checks), `fixture_data/fixture_definition.json` (three test-only records). Existing modules are copied under `candidate/chatbot`; their numerical validator is unchanged. `README.md` contains Windows execution instructions. `--serve` exposes only the labelled loopback fixture, not a production admin route.

The user must review these findings before any broader approved-fact pilot. Fidelity/currentness approvals remain required for normal knowledge eligibility. No further implementation, benchmark or deployment is authorized by this technical result.
