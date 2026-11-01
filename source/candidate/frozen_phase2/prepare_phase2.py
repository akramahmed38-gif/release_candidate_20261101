from pathlib import Path
import json,hashlib,shutil,sqlite3,re
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
def sha(v):return hashlib.sha256(v).hexdigest()
records={r['fact_id']:r for r in map(json.loads,(BASE/'source_evidence_readiness_20261027/02_STRUCTURED_FACTS.jsonl').read_text(encoding='utf-8').splitlines())}
old=json.loads((ROOT/'phase1/fixture_data/fixture_definition.json').read_text(encoding='utf-8'))
facts=[dict(f) for f in old['facts']]
for f in facts:
    r=records[f['fact_id']];f.update(source_document=r['source_document'],source_sha256=r['source_sha256'],locator=r['locator'],dependencies=r['prerequisite_fact_ids'],sequence_order=None)
for fid in ['F0073']+[f'F{i:04d}' for i in range(37,43)]:
    r=records[fid]
    facts.append({'fact_id':fid,'service_id':r['service_id'],'aspect':'initial_deposit' if fid=='F0073' else 'workflow','arabic':r['original_arabic_evidence'],'english':r['draft_english_rendering'],'arabic_sha256':r['evidence_quote_sha256'],'english_sha256':sha(r['draft_english_rendering'].encode()),'source_document':r['source_document'],'source_sha256':r['source_sha256'],'source_unit_id':r['source_unit_id'],'unit_text_sha256':r['evidence_unit_text_sha256'],'locator':r['locator'],'scope':r['scope'],'dependencies':r['prerequisite_fact_ids'],'sequence_order':r['sequence_order'],'normal_runtime_eligible':False,'business_approved':False,'human_fidelity_approved':False,'test_fixture_only':True})
sources={}
for f in facts:
    relative=f['source_document']
    if relative in sources:continue
    src=BASE/'source_snapshot'/relative
    if not src.exists():src=BASE/'axis_source_view_pilot_20261027/fixture_data/source_files'/relative
    assert sha(src.read_bytes())==f['source_sha256']
    out=ROOT/'fixture_data/source_files'/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,out)
    sources[relative]=f['source_sha256']
    if src.suffix=='.md':
        lines=src.read_text(encoding='utf-8-sig').splitlines()
        for fact in [x for x in facts if x['source_document']==relative]:
            loc=fact['locator'];region='\n'.join(lines[loc['line_start']-1:loc['line_end']])
            assert ' '.join(fact['arabic'].split()) in ' '.join(region.split()),fact['fact_id']
# Select existing anchor IDs by exact original source version and source region.
c=sqlite3.connect((BASE/'axis_source_view_pilot_20261027/failed_native_snapshot.sqlite').as_uri()+'?mode=ro',uri=True)
anchors={}
for unit in {f['source_unit_id'] for f in facts}:
    f=next(f for f in facts if f['source_unit_id']==unit)
    rows=c.execute('SELECT e.id,e.embedding_id FROM embeddings e JOIN segments s ON s.id=e.segment_id JOIN collections c ON c.id=s.collection JOIN embedding_metadata m ON m.id=e.id WHERE c.name=? AND m.key=? AND m.string_value=?',('learning_f94922ad76121a7b142b09da','source_path',f['source_document'])).fetchall()
    candidates=[]
    for rowid,chunk in rows:
        meta={k:s if s is not None else i for k,s,i in c.execute('SELECT key,string_value,int_value FROM embedding_metadata WHERE id=?',(rowid,))}
        if meta.get('source_sha256')!=f['source_sha256']:continue
        text=meta.get('prompt_text') or meta.get('chroma:document','')
        if f['service_id']=='axis_pay':valid=chunk==old['existing_anchor_chunk_id']
        elif f['service_id']=='azimut':valid='MyFawry' in text and 'إضافة صندوق' in text and 'توجيه التطبيق' in text
        else:
            clean=lambda value:re.sub(r'[\s*#_]+','',value)
            valid=clean(f['arabic']) in clean(text)
        if valid:candidates.append({'chunk_id':chunk,'metadata':{k:v for k,v in meta.items() if k not in ['prompt_text','chroma:document']},'prompt_text_sha256':sha(text.encode()),'anchor_text_length':len(text)})
    assert candidates,unit
    # Location/quote evidence, never arbitrary similarity, determines the anchor.
    # Overlapping chunks can both contain the same exact passage. Prefer the
    # smaller verified passage window; retain all verified anchor IDs for audit.
    selected=min(candidates,key=lambda r:(r['anchor_text_length'],r['chunk_id']))
    anchors[unit]={**selected,'verified_overlapping_anchor_ids':[r['chunk_id'] for r in candidates]}
c.close()
definition={**{k:v for k,v in old.items() if k not in ['facts','source_document','source_sha256','existing_anchor_chunk_id']},'schema':'ISOLATED_PHASE2_TEN_FACT_FIXTURE','facts':facts,'sources':sources,'anchors':anchors,'held':['QNB provider tariff label conflict','QNB complete KYC/eligibility checklist','Azimut KYC document inventory','All other original facts outside selected ten'],'authorization_reference':'User Phase 2 bounded technical expansion only; approvals pending'}
(ROOT/'fixture_data/definition.json').write_text(json.dumps(definition,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'facts':len(facts),'sources':len(sources),'independent_units':len(anchors),'all_test_only':True}))
