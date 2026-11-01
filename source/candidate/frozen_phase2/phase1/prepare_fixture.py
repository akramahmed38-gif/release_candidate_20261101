"""Create only the three explicitly authorized pending-approval test records."""
import csv,hashlib,json,shutil,sqlite3
from pathlib import Path
ROOT=Path(__file__).parent;BASE=ROOT.parent;SOURCE=BASE/'source_evidence_readiness_20261027'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
facts={f['fact_id']:f for f in [json.loads(x) for x in (SOURCE/'02_STRUCTURED_FACTS.jsonl').read_text(encoding='utf-8').splitlines()]}
with (SOURCE/'pilot_approval_readiness/02_HUMAN_REVIEW_QUEUE.csv').open(encoding='utf-8-sig',newline='') as stream:queue={r['fact_id']:r for r in csv.DictReader(stream) if r['fact_id']}
ids=['F0010','F0011','F0012'];rows=[]
for fid,aspect in zip(ids,['opening_fee','initial_deposit','balance_treatment']):
    f=facts[fid];q=queue[fid]
    assert not f['runtime_eligible'] and q['translation_status']==q['business_status']=='PENDING'
    ar=f['original_arabic_evidence'];en=q['english_rendering_for_review']
    rows.append({'fact_id':fid,'service_id':f['service_id'],'aspect':aspect,'arabic':ar,'english':en,
        'arabic_sha256':hashlib.sha256(ar.encode()).hexdigest(),'english_sha256':hashlib.sha256(en.encode()).hexdigest(),
        'source_unit_id':f['source_unit_id'],'unit_text_sha256':f['evidence_unit_text_sha256'],'scope':f['scope'],
        'normal_runtime_eligible':False,'business_approved':False,'human_fidelity_approved':False,'test_fixture_only':True})
db=sqlite3.connect((BASE/'canonical_plain_experiment_20261027/package/artifacts/canonical_topic_views_v4.sqlite').as_uri()+'?mode=ro',uri=True)
profiles={k:json.loads(v) for k,v in db.execute('select service_id,payload from profiles')};db.close()
profiles['axis_pay']['aliases']=list(set(profiles['axis_pay'].get('aliases',[])+['اكسيس','اكسيس باي','AXIS Pay']))
doc=facts['F0010']['source_document'];path=BASE/'source_snapshot'/doc;assert sha(path)==facts['F0010']['source_sha256']
out=ROOT/'fixture_data/source_files'/doc;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,out)
definition={'schema':'EXPLICIT_UNAPPROVED_THREE_FACT_TEST_FIXTURE','authorization_reference':'User task: AUTHORIZE FIRST WORKING ARCHITECTURE PILOT, 2026-10-27; technical fixture only, no business approval',
 'source_document':doc,'source_sha256':sha(path),'facts':rows,'service_profiles':profiles,
 'existing_anchor_chunk_id':'learning-0174474637be11ae3b9072d96dfa4efb0a464ee1ade431cabc206d6ecaf2ed53',
 'source_content_generation':'9551abd14708840e63481c7d','expected_embedding_model':'bge-m3:latest',
 'expected_embedding_digest':'7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab',
 'source_evidence_unit_id':rows[0]['source_unit_id'],'source_unit_text_sha256':rows[0]['unit_text_sha256']}
(ROOT/'fixture_data/fixture_definition.json').write_text(json.dumps(definition,ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(BASE/'canonical_acceptance_20261027/native_support.py',ROOT/'native_support.py')
assert sha(ROOT/'candidate/chatbot/reference_validation.py')=='9eb736461247aaa7f89347bb8284113c9bd51b5d3e6f954b31b4e4d665ac2848'
print(json.dumps({'fixture_records':len(rows),'source_sha256':sha(out),'approval_promotions':0,'document_embeddings_created':0}))
