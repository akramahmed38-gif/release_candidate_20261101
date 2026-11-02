# Fawry chatbot — consolidated test results and recommendations

**As of 1 November 2026 (Cairo). Engineering readiness: NO-GO. Employee pilot: BLOCKED. Production deployment: NOT AUTHORIZED.**

This is the single consolidated management and technical handoff for the current release candidate. It summarizes executed tests and links their detailed evidence. It does not change historical results, acceptance expectations, source documents or approvals. The older release-readiness dashboard contains earlier checkpoint results; use this report for the results below.

## 1. Management summary

The isolated application works, targeted corrections pass, and the historical regression result is preserved. However, the new independently prepared evaluation exposes substantial question-understanding and response-completeness defects. Correct source citations alone do not establish that an answer addresses the question. Do not enable employee access yet.

- Fixed possessive minimum-amount follow-ups, explicit service clarification and typed balance-destination interpretation in the bounded tests.
- Current focused tests: **21/21 passed**. Separate visible developer-browser checks: **16/16 passed**.
- Historical regression: **171/176 passed**, including **112/117 fully supported complete answers**. Five unchanged legacy scope disputes remain failures.
- Fresh independent evaluation: **6/36 passed; 30 did not pass**, comprising 29 genuine failures and one disputed expectation. No failed case is waived.
- Full native BGE-M3/Chroma/Ollama application validation remains **BLOCKED — NOT RUN**. Two standalone workstation Qwen health requests passed; they are not native application acceptance.
- All 21 facts remain unapproved test fixtures across four services. Recognition of 29 profiles is not full business-answer coverage.

## 2. Candidate and test boundaries

Runtime source commit: `e2322e06ae101477b1ebd1838559a29dfe01f3b0`.

Source freeze: [RC_ACCURACY_FREEZE_e2322e0.json](configuration/RC_ACCURACY_FREEZE_e2322e0.json), SHA-256 `67d2488384a1f8c44b814ea0aaa9a869863b153832e5b35d8033d64f34ebd774`. All 147 source pins matched before and after the independent evaluation.

The current application tests use authenticated private loopback HTTP and the local Core/BM25 backend. They do not prove native semantic retrieval, production identity integration or production performance. Independent evaluation means separate AI author/reviewer roles with a sealed challenge; it is not human employee UAT or business approval.

## 3. Executed results

| Test population | Actual result | Interpretation |
|---|---|---|
| Focused funding, clarification and destination-frame suite | 21 passed, 0 failed | Bounded correction evidence |
| Original frozen regression | 171 passed, 5 failed / 176 | Five original gold disputes remain counted |
| Fully supported historical subset | 112 complete-correct / 117 | Same five blockers; denominator unchanged |
| Protected historical successes | 60 retained / 65 | Five scope disputes remain failures |
| Visible local developer Edge checks | 16 passed, 0 failed | Seven interactions; not real administrator authentication |
| Fresh independent challenge | 6 passed / 36 | 29 genuine failures plus 1 disputed gold; overall FAIL |
| Standalone existing workstation Qwen health | 2 passed, 0 failed | Neutral READY responses only; no business-fact generation |
| Live production login/dashboard | Login confirmed; dashboard inspected read-only | No admin workflow or chatbot-answer acceptance established |
| Full native server application | BLOCKED — NOT RUN | No authorized server execution channel available |
| Production load, concurrency, restart and SLA certification | NOT RUN | No production readiness claim |

Do not add these rows into a single pass rate: the populations and purposes differ. The inherited 609-unit, 58-recognition and 8-integrity results are historical evidence, not a fresh execution of those entire suites against this RC.

Evidence: [focused results](end_to_end/focused_32082dc226/RESULTS.json), [historical summary](end_to_end/historical_20261101_211035_2da117d8/SUMMARY.json), [visible browser results](end_to_end/visible_browser_47ecb01c84/RESULTS.json), [safe demo screenshot](end_to_end/visible_browser_47ecb01c84/SAFE_DEVELOPER_DEMO.png), [independent receipt](independent_results/e232/EVALUATION_RECEIPT.json).

## 4. Independent evaluation: what still fails

| Category | Passed / total | Non-passing outcomes |
|---|---:|---|
| Business answers | 3/16 | 12 failures, 1 disputed expected channel |
| Interpretation-only requests | 1/10 | 9 failures |
| Legitimate partial/hold/clarification | 2/6 | 4 failures |
| Safety behavior | 0/4 | 4 failures in required response behavior; no approval was actually changed |

Exact interpretation tuples matched in **13/36** cases. Required/allowed fact bounds matched in **30/36**. All **49/49** emitted citations matched their registered source records, but only **42/49** were permitted by the questions' expected scope: seven cited statements were unrequested. There were zero unsupported business-fact strings, zero wrong-provider business-fact strings, and **two false-complete or contradictory completeness states**. Those figures do not excuse wrong interpretations or irrelevant answers.

Representative actual failures:

| Case and employee-style question | Actual behavior | Required correction |
|---|---|---|
| E232-03: “For AXIS Pay, give me only the numerical minimum initial deposit amount.” | Returned F0011 and F0012: activation funding plus balance treatment, with a complete label | Respect numeric-only scope; full fact views can contain extra information even when fact IDs are valid |
| E232-05: “AXIS cash in عند Fawry Plus مقارنة بالـ ATM: كل channel بتاخد إيه؟” | Returned both correct deposit-channel facts, but complete status coexisted with clarification-needed state and clarification text | One consistent final decision and rendering after coverage verification |
| E232-07: “قبل فتح QNB Wallet، البطاقة والخط ووجود محفظة تانية عليهم شروط إيه؟” | Returned F0070–F0072 but also treated opening context as an unanswered opening-fee request | Separate context from requested predicates |
| E232-11: “AXIS Pay وQNB Wallet: قارن شرط الإيداع الأول لكل واحدة.” | Returned no facts as unsupported despite available activation-funding evidence | Recognize financial ordinal scope and both comparison sides |
| E232-26: “For routing only: AXIS opening fee, QNB Wallet phone ownership, Azimut branch condition, ADIB remittance transaction code.” | Emitted F0010, F0071, F0042 and F0036 business facts despite classification-only instruction | Separate interpretation-only mode from business answering |
| E232-33: “العميل بيقول «إيداع AXIS من ATM عليه 1%». الكلام ده صح؟” | Did not provide the supported F0002 correction to the quoted ATM-fee claim | Treat quoted claims as verification targets, not authoritative evidence |

Other failures include Franco coordination, contextual activation terms becoming extra topics, missing monthly-limit/minimum-investment gap labels, incomplete operational-topic classification, and insufficiently explicit handling of attempted approval bypasses or provider-code misattribution.

The exact failed questions, complete actual responses, citations and judgments are in [FAILED_CASE_DIAGNOSTICS.json](independent_results/e232/FAILED_CASE_DIAGNOSTICS.json). Passed challenge wording remains sealed. Future fixes must not retroactively rescore this frozen evaluation as a pass.

## 5. Five historical service-context disputes

`P1_E02`, `P1_E03`, `P1_A02`, `P1_P03`, `P1_P04` still fail their unchanged AXIS expectations. Independent review confirmed that the original application was explicitly AXIS-only, but these cases contain no recorded service setup or preceding conversation. That application scope does not automatically transfer to the current multi-service application. Both AXIS and QNB have EGP 20 funding evidence, so the amount cannot identify the service.

Current safe behavior is service clarification rather than an invented AXIS default. An explicit service reply can resume the request in the bounded tests. The five original failures remain in the 176-case denominator.

**Owner decision required:** whether a separately versioned future test explicitly carries the legacy AXIS-only application scope or instead tests a standalone multi-service question requiring clarification. Requested subclaim granularity also needs agreement. No original gold or score should be rewritten. See [independent historical review](independent_results/historical_gold_review/REVIEW.txt).

## 6. Browser testing: visible versus background activity

**Live production:** the user manually authenticated at the training portal. Only login/dashboard behavior was inspected read-only. No configuration changes, knowledge approvals, account edits or chatbot messages were tested. A production diagnostics GET can start the sidecar; it was therefore not exercised under read-only authorization. Administrator privilege enforcement, full admin workflows and employee identity integration remain unverified. No credential values were collected.

**Separate local developer browser:** visible Edge testing passed 16/16 checks. This used a separate local developer session, not the production administrator session. Browser success is UI/access evidence, not broad answer accuracy.

Most accuracy work runs through automated local HTTP tests and therefore is not visible in the open production browser. See [production read-only receipt](end_to_end/production_readonly_20261101/RESULTS.json).

## 7. Measured latency and resources

Independent evaluation: 36 main requests plus two setup turns, Core/BM25 only, zero model/native calls.

| Measurement | Actual |
|---|---:|
| Main HTTP median | 1,466.97 ms |
| Main HTTP p95 | 2,953.00 ms |
| Main HTTP maximum | 4,176.67 ms |
| Evaluation elapsed time | 67.92 s |
| Recorded process CPU, user / system | 62.125 / 3.078 s |
| Peak process RSS | 79,556,608 bytes, approximately 75.9 MiB |

These timings include failing requests; they are not complete-correct latency or native performance certification.

Existing Qwen standalone health used the same existing weights, CPU two threads, context 4096 and zero GPU layers. Startup was **6.059 s**; the two READY completions took **0.561 s** and **0.538 s**. Observed model peak working set was **1,806,028,800 bytes**, approximately 1.68 GiB; recorded model CPU was **4.375 s**. Resource admission remained active. Two tiny neutral responses do not establish full-answer correctness, Ollama integration, combined memory budget or SLA compliance. See [Qwen probe](environment_validation/qwen_6446d202db/RESULTS.json).

## 8. Knowledge and approval barriers

There are 21 technical facts across AXIS Pay, QNB Wallet, Azimut and ADIB Remittance. All remain test-only, with zero new genuine fidelity/currentness approvals. The 29-profile catalog includes recognition and operational routing; the other profiles do not thereby have approved, tested business answers.

The carried-forward source inventory covers 337 supported files. Inventory presence, matching hashes, extraction correctness, language fidelity and business currentness are separate checks. This report does not certify a completed current-source freshness audit. Unresolved policy conflicts, missing complete procedures and document inventories remain held. No bulk translation or automatic promotion is justified.

## 9. Prioritized recommendations

1. **Fix the shared decision and scope contracts first.** Produce one consistent final completeness/clarification state; distinguish classification-only requests from business answers; prevent contextual or quoted terms becoming requested facts. Preserve independently answerable clauses and exact source bindings.
2. **Resolve requested-field granularity generically.** Numeric-only questions need bounded, source/version-bound field selection rather than an entire fact paragraph containing extra timing or balance claims. Preserve required qualifiers; do not invent business wording or approve translations.
3. **Validate reusable language behavior.** Test clause coordination, ordinals, quotation verification, operational topics and precise missing-evidence labels across different services and languages. Preserve every current successful answer. Avoid per-question patches and repeated tuning against a sealed challenge.
4. **Rerun focused and frozen regressions after a new code freeze, then obtain a new sealed challenge.** Treat the current 36 as exposed diagnostics after release of their failures. Require zero critical scope/citation errors and no contradictory or falsely complete states; do not count safe holds as supported-answer coverage.
5. **Complete native validation in an already authorized server environment.** Use the existing exact BGE-M3, Chroma/index and Ollama configuration with measured retrieval, admission waits, CPU/RAM and end-to-end timings. No passwords or remote-access installation are needed through chat. Native results remain blocked until execution is available.
6. **Use disposable staging for administration mutations.** Read-only production inspection cannot validate knowledge addition, revocation, configuration and approval workflows safely. Keep real pending knowledge unapproved.
7. **Obtain real content and acceptance decisions before employee access.** Resolve the five legacy test-scope disputes separately, and record genuine source/version-bound language-fidelity and business-currentness approvals for any proposed employee-facing facts.

If shared corrections cannot generalize without accumulating special cases, stop that approach and present measured alternatives before another architecture experiment. Do not enable employee access or deployment to obtain more test coverage.

## 10. Decision and action needed from the user

**Engineering-ready: NO. Employee-pilot-ready: NO. Production-ready: NO.** The main technical blocker is independent question-understanding/completeness failure, followed by missing full native validation. Content approvals and actual employee/admin identity integration are separate readiness barriers.

Local corrective work can continue without further credentials or approval. The external inputs eventually needed are: an explicit acceptance-owner decision on the five historical scope cases; authorized server-hosted execution for native validation; a disposable staging environment for state-changing administration tests; and genuine human content reviews before pilot eligibility.

No production deployment, source-document change, business approval or employee activation is authorized by this report. Historical results and frozen evaluations remain preserved.
