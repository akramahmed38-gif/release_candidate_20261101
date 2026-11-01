# Phase 2 isolated multi-source source-view pilot

Authorized scope: ten unapproved test facts, three services, three original documents/evidence units. No production integration. Phase 1 code/results remain unchanged; PHASE1_FROZEN.zip and PHASE1_BASELINE_PINS.json preserve the known-good reference.

Added code:

- engine.py: service/topic slots, scoped fact selection, dependency completeness, grouped bilingual assembly, source/view/eligibility checks.
- retrieval.py: independent BGE/Chroma/BM25 retrieval for each requested service/topic. Exact source vectors are reused from the verified repair overlay's base collection. No document embeddings are computed.
- workflow_view.py: fingerprint-bound normalization of the grammatical reference “to do so” for the existing closed-vocabulary workflow checker. Displayed source-view text is unchanged. Added actions, missing steps, changed order and lost conditions remain rejected. The underlying validator is unchanged.
- run_phase2.py: actual private HTTP runner, fixed expected facts, frozen Phase 1 regressions, six integrity checks and per-response timing/resources.
- fixture_data/definition.json: original IDs, quotes, source fingerprints, scopes, dependencies, sequence, citations and pending approvals.

## Included and held evidence

AXIS: F0010–F0012 unchanged. QNB: F0073 only, immediate activation conditional on at least 20 EGP deposit. Azimut: F0037–F0042, six ordered app-navigation steps including conditional branch visit. These are test representations, not approved policy.

QNB source: KnowledgeBase/Articles/Wallets_ART.md, lines 161–165. Azimut: KnowledgeBase/Articles/AZIMUT_ART.md, line 434. AXIS: daily_brief/axis_wallet_sales_guide.pdf, page 1. Exact original hashes and evidence IDs are in the fixture definition. Markdown quotes were checked in the exact original line ranges. The existing AXIS visually reviewed source is reused unchanged.

QNB provider tariff-label conflict, QNB opening fees/balance disposition, broader KYC/document inventories and all other facts remain unavailable. Approved fixture coverage is financial funding/navigation only; answers do not claim full activation eligibility.

## Run

Local core checks (no BGE/Chroma proof):

    & 'D:\FawryChatbotPreparation\Scripts\python.exe' -B 'D:\FawryChatbotPreparation\multi_source_pilot_20261027\run_phase2.py' --backend core

Server, using the existing local environment:

    & 'C:\Users\FWPLUS.Auto\Desktop\Projects\Production\FP Branches + Forms\HR Training App\maintenance\chatbot_multi_source_20261027\run_multi_source_pilot.ps1'

The server launcher verifies package hashes. It writes only its isolated runs. Query embeddings use existing BGE-M3, two threads and CPU/RAM guards; shared model work can delay admin replies. No Qwen calls, translation calls, model switches or document re-embedding occur.

RESULTS.json contains actual answers, slots, per-claim citations, expected facts and stage/HTTP timings. SUMMARY.json separates core-only and native decisions. This finite test is not independent human approval, broad-corpus coverage or a production latency/concurrency certificate. Mixed-language replies follow the existing language policy.

Stop after review. No automatic expansion, broad benchmark or deployment follows.
