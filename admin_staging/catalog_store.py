"""Data-driven pending-evidence import for the existing staging admin app.

No source discovery result, hash match or AI review grants runtime approval.
"""
from pathlib import Path,PurePosixPath
import csv,hashlib,json,re,sqlite3,time
ROOT=Path(__file__).resolve().parent
if ROOT.name=='next_revision':ROOT=ROOT.parent
RELEASE=ROOT.parent
LIBRARY=Path(r'D:\FawryChatbotPreparation\Canonical Library\Fawry_Canonical_Knowledge_Library_v1')
DB=ROOT/'state/databases/knowledge.sqlite'
SENSITIVE=re.compile(r'(?i)(?:password|passwd|api[_ -]?key|bearer\s+[a-z0-9]|كلمة\s*(?:المرور|السر)|(?<!\d)\d{14}(?!\d)|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}|(?<!\d)01[0125]\d{8}(?!\d)|ignore.{0,35}(?:instructions|approvals))')

def db():
 DB.parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;c.execute('pragma foreign_keys=on')
 c.executescript('CREATE TABLE IF NOT EXISTS record(kind TEXT NOT NULL,id TEXT NOT NULL,version TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(kind,id,version));CREATE INDEX IF NOT EXISTS record_kind ON record(kind);CREATE TABLE IF NOT EXISTS event(id INTEGER PRIMARY KEY,at REAL NOT NULL,kind TEXT NOT NULL,target TEXT NOT NULL,data TEXT NOT NULL);')
 return c

def rows(kind):
 with db() as c:return [json.loads(r['data']) for r in c.execute('select data from record where kind=? order by id,version',(kind,))]

def get(kind,identifier,version=None):
 with db() as c:
  found=c.execute('select data from record where kind=? and id=?'+(' and version=?' if version else '')+' order by version desc',(kind,identifier,version) if version else (kind,identifier)).fetchall()
 if len(found)!=1:raise ValueError('Exact source version required or record unavailable')
 return json.loads(found[0]['data'])

def put(c,kind,identifier,version,data):
 # Imports never overwrite locally edited review revisions.
 c.execute('insert or ignore into record(kind,id,version,data) values(?,?,?,?)',(kind,identifier,version,json.dumps(data,ensure_ascii=False)))

def norm(path):return PurePosixPath(path.replace('\\','/')).as_posix()

def safe_view(body):
 reason='restricted_credentials_personal_data_or_embedded_instruction' if SENSITIVE.search(body or '') else None
 return '' if reason else body,reason

def import_pending():
 library_db=LIBRARY/'canonical_library_preview.sqlite'
 source=sqlite3.connect(library_db.as_uri()+'?mode=ro&immutable=1',uri=True);source.row_factory=sqlite3.Row
 audit=json.loads((RELEASE/'knowledge_coverage/audit_5fb9bc7779/RESULTS.json').read_text(encoding='utf-8'))
 snapshots={norm(r['source_path']):r for r in audit['sources']}
 definition=json.loads((RELEASE/'source/candidate/fixture_data/definition.json').read_text(encoding='utf-8'))
 fixture={r['fact_id']:r for r in definition['facts']}
 metadata={}
 with (RELEASE/'knowledge_coverage/ALL_29_SERVICE_COVERAGE.csv').open(encoding='utf-8-sig',newline='') as f:
  for r in csv.DictReader(f):metadata[r['service_id']]=r
 sources={};quarantined=0;verified=0
 with db() as c:
  for r in source.execute('select * from service'):
   sid=r['service_id'];meta=metadata.get(sid,{})
   data={'service_id':sid,'name':r['name'],'family':r['family'],'aliases':json.loads(r['aliases_json']),'observed_topics':json.loads(r['covered_topics_json']),
     'source_approval':'NOT_INFERRED','normal_runtime_eligible':False,'existing_scoped_approval_references':json.loads(meta.get('existing_scoped_approval_boundaries') or '[]'),
     'entity_kind':meta.get('entity_kind','canonical_profile'),'business_currentness':'PENDING_AUTHORIZED_OWNER','human_fidelity':'PENDING','fixture_count':sum(x['service_id']==sid for x in fixture.values())}
   put(c,'profile',sid,'catalog-reference',data)
  for r in source.execute('select * from source'):
   data=dict(r);path=norm(data['source_path']);snap=snapshots.get(path);match=bool(snap and snap['status']=='MATCH' and snap['current_sha256']==data['source_sha256'])
   data.update(source_path=path,current_snapshot_match=match,current_snapshot_sha256=snap.get('current_sha256') if snap else None,
    freshness='CONTENT_HASH_IDENTITY_ONLY' if match else 'SOURCE_VERSION_REVIEW_REQUIRED',normal_runtime_eligible=False,review_status='pending',currentness_approved=False,fidelity_approved=False)
   sources[data['source_id']]=data;put(c,'source',data['source_id'],data['source_sha256'],data)
  for r in source.execute('select * from unit'):
   original=dict(r);body=original.pop('body') or '';parent=sources[original['source_id']];view,hold=safe_view(body)
   if hold:quarantined+=1
   if parent['current_snapshot_match']:verified+=1
   data={**original,'body':view,'body_sha256':hashlib.sha256(body.encode()).hexdigest(),'source_path':parent['source_path'],'source_sha256':parent['source_sha256'],
    'service_ids':json.loads(original['service_ids_json']),'topic_ids':json.loads(original['topic_ids_json']),
    'review_status':'restricted_hold' if hold else 'pending','hold_reason':hold or (None if parent['current_snapshot_match'] else 'source_version_identity_not_current'),
    'arabic_view':'original_source_reference' if re.search(r'[\u0621-\u064a]',body) else 'not_verified','english_view':'NO_REVIEWED_TRANSLATION',
    'extraction_fidelity':'NOT_ESTABLISHED_BY_HASH','normal_runtime_eligible':False,'business_approved':False,'fidelity_approved':False,'completeness':'UNASSESSED'}
   put(c,'unit',data['unit_id'],parent['source_sha256'],data)
  for r in source.execute('select * from pdf_page_reference'):
   data=dict(r);preview,hold=safe_view(data.pop('text_preview') or '');data.update(text_preview=preview,hold_reason=hold,normal_runtime_eligible=False,review_status='pending')
   put(c,'pdf_page',data['unit_id']+':'+str(data['page']),data['source_sha256'],data)
  # Audited image and other source references absent from the 330-file canonical
  # export stay visible without inventing extraction, units or associations.
  canonical_paths={s['source_path'] for s in sources.values()}
  for path,snap in snapshots.items():
   if path in canonical_paths:continue
   sid='snapshot-only-'+hashlib.sha256(path.encode()).hexdigest()[:16]
   put(c,'source',sid,snap['current_sha256'],{'source_id':sid,'source_path':path,'source_sha256':snap['current_sha256'],'current_snapshot_match':snap['status']=='MATCH','review_status':'pending','hold_reason':'NO_CANONICAL_UNIT_OR_REPAIRED_EXTRACTION_IMPORTED','normal_runtime_eligible':False})
  inventory=Path(r'D:\FawryChatbotPreparation\source_evidence_readiness_20261027\02_STRUCTURED_FACTS.jsonl')
  for line in inventory.read_text(encoding='utf-8-sig').splitlines():
   original=json.loads(line);body=original['original_arabic_evidence'];view,hold=safe_view(body);f=fixture.get(original['fact_id'])
   if original.get('evidence_quote_sha256') and hashlib.sha256(body.encode()).hexdigest()!=original['evidence_quote_sha256']:hold='QUOTE_HASH_MISMATCH';view=''
   test_view=f if f and f['source_sha256']==original['source_sha256'] and f['source_unit_id']==original['source_unit_id'] else None
   data={k:v for k,v in original.items() if k not in {'original_arabic_evidence','draft_english_rendering'}}
   data.update(arabic=view,english_test_view=test_view['english'] if test_view and not hold else '',source_english_draft_present=bool(original.get('draft_english_rendering')),
    english_view_status='UNAPPROVED_VERIFIED_TECHNICAL_FIXTURE' if test_view else 'NOT_IMPORTED_AS_VERIFIED_VIEW',review_status='restricted_hold' if hold else 'pending',quarantine_reason=hold,
    runtime_eligible=False,normal_runtime_eligible=False,business_approved=False,fidelity_approved=False,test_fixture_only=bool(test_view))
   put(c,'fact',data['fact_id'],data['source_sha256'],data)
  c.execute('insert into event(at,kind,target,data) values(?,?,?,?)',(time.time(),'pending_review_import','canonical_existing_library',json.dumps({'no_approvals':True,'no_translation':True,'no_embedding':True})))
 source.close()
 counts={k:len(rows(k)) for k in ['profile','source','unit','pdf_page','fact']}
 result={'counts':counts,'quarantined_units':quarantined,'source_hash_matching_units':verified,'library_sha256':hashlib.sha256(library_db.read_bytes()).hexdigest(),'normal_runtime_eligible':0,'new_approvals':0,'new_translations':0,'new_embeddings':0,'extraction_fidelity_not_inferred':True}
 (ROOT/'PENDING_CATALOG_IMPORT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
 return result

if __name__=='__main__':import_pending()
