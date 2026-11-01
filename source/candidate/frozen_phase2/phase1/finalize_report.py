"""Offline review of completed, preserved observations; no inference or reruns."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parent
run=root/'native_results/20261027_182451_e6a97063'
rows=json.loads((run/'RESULTS.json').read_text(encoding='utf-8'))
summary=json.loads((run/'SUMMARY.json').read_text(encoding='utf-8'))
facts={f['fact_id']:f for f in json.loads((root/'fixture_data/fixture_definition.json').read_text(encoding='utf-8'))['facts']}
assert summary['technical_checks_passed'] and len(rows)==28
for row in rows:
    value=row.get('response',{})
    for fid in value.get('supported_fact_ids',[]):
        field='english' if value['reply_language']=='en' else 'arabic'
        assert facts[fid][field] in value['answer']
        cite=next(c for c in value['citations'] if c['fact_id']==fid)
        assert cite['page']==1 and cite['source_sha256']=='198dffbc8ab1ce2887356e91fab9d241ea3f08c35216d2b32a1062e64439abce'
    assert not value.get('normal_runtime_eligible',False)
parent=root.parent/'source_evidence_readiness_20261027'
assert hashlib.sha256((parent/'02_STRUCTURED_FACTS.jsonl').read_bytes()).hexdigest()=='8739ced3bb3b093191e2a77d8444aab215f694527138e894d7b14f45d5440b28'
assert hashlib.sha256((parent/'03_APPROVAL_REGISTER.csv').read_bytes()).hexdigest()=='2f4513ed9febe61f8621af68fc66bd59b013dc9680e72f961cac5b32c9444c8e'
def pct(values,p):
    values=sorted(values);i=(len(values)-1)*p;lo=int(i)
    return values[lo]+(values[min(lo+1,len(values)-1)]-values[lo])*(i-lo)
complete=[r for r in rows if r.get('response',{}).get('complete') and r['passed']]
text='''# Three-fact AXIS source-view pilot — technical GO for review

27 October 2026. Native run `20261027_182451_e6a97063`. **28/28 bounded checks passed.** This demonstrates the authorized three-fact technical fixture; it does not approve its facts, authorize a broader implementation, or establish production readiness. Stop for user review.

## Observed correctness

24 main requests included 13 complete supported answers, two correctly scoped partial answers and nine unavailable answers. Four additional source/eligibility/isolation checks passed. Two separate setup turns were retained. Actual main and mutation responses used private loopback HTTP; normal-mode rejection was a constructor check. No exact question-to-answer lookup or Qwen generation was used.

Offline inspection verified each emitted business statement is its exact source-bound Arabic or pending-review English representation, and each has the correct fact/source/page citation. No unsupported financial assertion was observed in these cases. The minimum 20 EGP deposit is conditional activation funding and remains balance; it is not rendered as a fee. Financial-only scope is disclosed, without implying a complete KYC checklist.

Expected fact sets were fixed before execution and include additional paraphrases. This is source-based technical checking, **not independent human fidelity/currentness approval or broad unseen-language certification**. General interpretation remains rule-based and bounded.

## Actual answer examples
'''
for case in ['E04','A03','M01','N05']:
    r=next(r for r in rows if r['id']==case)
    text+='\n### '+case+'\n\n'+r['question']+'\n\n'+r['response']['answer']+'\n\n'
    text+='Citation: `daily_brief/axis_wallet_sales_guide.pdf`, page 1; facts '+', '.join(r['response']['supported_fact_ids'])+'. HTTP '+str(round(r['measurements']['http_ms'],2))+' ms.\n'
text+='''
Source SHA-256: `198dffbc8ab1ce2887356e91fab9d241ea3f08c35216d2b32a1062e64439abce`. Evidence unit `source-verified-axis-guide-activation-198dffbc8ab1`; unit text SHA-256 `779db86d8e0f6b628bf7a5a5da67273da01490af86a8137ec6cabcb0a525774b`. Full per-fact citations and all expected/actual records are in `native_results/20261027_182451_e6a97063/RESULTS.json`.

## Measured latency and resources

Complete-correct responses: 13 observations, HTTP p50 **266.04 ms**, p95 **311.06 ms**. Startup/snapshot/model verification: **5.159 s**, separate from request latency. Query caches are cleared before supported requests; no answer or translation cache is used. Unsupported holds are excluded from these complete-answer latency figures.

'''
for language in ['ar','en']:
    group=[r for r in complete if r['response']['reply_language']==language]
    values=[r['measurements']['http_ms'] for r in group]
    text+=f'- {language}: {len(values)} complete-correct samples; HTTP p50 {pct(values,.5):.2f} ms, p95 {pct(values,.95):.2f} ms.\n'
    keys=['interpretation_ms','source_and_test_authorization_ms','retrieval_ms','validation_and_assembly_ms']
    text+='  Mean stage times: '+', '.join(f'{k} {sum(r["response"]["timings_ms"].get(k,0) for r in group)/len(group):.2f} ms' for k in keys)+'.\n'
    text+='  Mean embedding '+f'{sum(r["response"]["retrieval"].get("query_embedding_ms",0) for r in group)/len(group):.2f} ms'+', resource wait '+f'{sum(r["response"]["retrieval"].get("resource_wait_ms",0) for r in group)/len(group):.2f} ms'+'.\n'
cpu=[r['measurements']['process_cpu_ms'] for r in rows if 'measurements' in r]
text+=f'\nMeasured Python/Chroma peak working set: **{summary["process_memory"]["peak_working_set_bytes"]/1024**2:.2f} MiB**. Process CPU across recorded main/mutation requests: **{sum(cpu):.2f} ms** (setup/startup excluded; per-request values retained). Shared Ollama embedding-model CPU/RAM is not attributable from this process measurement. No inference-generation queue, prompt or decode work occurred.\n'
text+='''
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
'''
(root/'FINAL_REPORT.md').write_text(text,encoding='utf-8')
print(json.dumps({'offline_statement_and_citation_review_passed':True,'final_report':str(root/'FINAL_REPORT.md'),'decision':'TECHNICAL_GO_FOR_USER_REVIEW_PRODUCTION_NO_GO'}))
