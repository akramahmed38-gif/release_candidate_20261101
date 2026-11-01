# Isolated AXIS source-view prototype

Only F0010–F0012 are answer data. Their fidelity and business-currentness approvals remain pending. Every response is labelled UNAPPROVED TEST FIXTURE. This program is not connected to the portal or normal chatbot runtime.

The application interprets service/aspect concepts, selects reusable source-bound records and assembles their exact Arabic or review-only English views. It never calls Qwen. Existing service planning, conversation storage, normalization, BM25 scoring and numerical/semantic checks are reused. The numerical validator is unchanged. No exact question/answer lookup is used.

## Local executable

```powershell
& 'D:\FawryChatbotPreparation\Scripts\python.exe' -B 'D:\FawryChatbotPreparation\axis_source_view_pilot_20261027\run_pilot.py' --backend core
```

Add `--serve` for a loopback-only test interface; open the printed local URL. Ctrl+C stops it. This core backend tests interpretation, assembly and safety with the existing BM25 scorer; it does not prove BGE/Chroma retrieval.

The server launcher runs `--backend native` with the existing chatbot venv and BGE-M3 model. It snapshots an existing private repaired index, verifies the exact original page anchor, and copies its existing vector into a separate three-record fixture collection. All facts share one source page/vector; no new document embeddings are computed. Each supported request uses a real query embedding, Chroma query and existing BM25 scorer. Candidate thresholds are unchanged. No automatic lexical fallback is used if native initialization fails.

## Fixed checks and outputs

24 main cases plus two setup turns, three mutation requests and one normal-mode rejection check. Expected fact IDs were fixed before execution; they are technical source-based expectations, not human policy approvals. Additional paraphrases supplement the user examples. No claim of independent human business acceptance is made.

`RESULTS.json` retains actual answers, citations, expected/actual results and timing. `SUMMARY.json` reports complete-correct response timings, process memory, numerical regressions and isolation results. Startup is separate from HTTP latency. Shared Ollama resource use is not attributed to this process. Small-sample latency is descriptive, not a production SLA or an accuracy-preserving 20% comparison.

Original citation: `daily_brief/axis_wallet_sales_guide.pdf`, page 1, SHA-256 `198dffbc8ab1ce2887356e91fab9d241ea3f08c35216d2b32a1062e64439abce`.

Questions outside these financial terms are partial or unavailable. These facts do not establish all opening/KYC requirements. Source changes and test eligibility revocation invalidate affected fixture outputs. No approval is granted and normal-runtime entry is rejected.
