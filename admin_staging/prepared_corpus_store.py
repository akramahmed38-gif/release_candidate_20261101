"""Read-only adapter for existing prepared chunks, not a replacement responder.
No source extraction, model call, eligibility promotion or production pointer write.
"""
from pathlib import Path
import hashlib,json
EXPECTED_SIGNATURE='f94922ad76121a7b142b09da91b3d9c5bf3c04b6fab8c9e35267db593275ae37'
EXPECTED_CHUNKS_SHA256='46608db273d6314a529440a3d1ac70fa51786bc3611b588f3d4ed72c2e01a8a0'
class PreparedCorpusStore:
 def __init__(self,root):
  self.root=Path(root).resolve();self.collection_name='prepared_readonly_'+EXPECTED_SIGNATURE[:24]
  manifest=json.loads((self.root/'preparation_manifest.json').read_text(encoding='utf-8'))
  if manifest.get('signature')!=EXPECTED_SIGNATURE or not manifest.get('complete'):raise RuntimeError('Prepared corpus identity or completeness differs')
  raw=(self.root/'chunks.jsonl').read_bytes()
  if hashlib.sha256(raw).hexdigest()!=EXPECTED_CHUNKS_SHA256:raise RuntimeError('Prepared chunks differ from frozen existing source generation')
  self.rows=[json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
  if len(self.rows)!=manifest['chunks'] or len({r['id'] for r in self.rows})!=len(self.rows):raise RuntimeError('Prepared corpus row identity/count mismatch')
  self.manifest=manifest
 def fetch_all_chunks(self):
  # Existing retriever enriches metadata in memory; disk stays immutable.
  return self.rows
 def count(self):return len(self.rows)
 def query(self,*args,**kwargs):
  raise RuntimeError('Semantic vector query is unavailable: this is a prepared-content adapter, not Chroma/BGE validation')
 def add_chunks(self,*args,**kwargs):raise RuntimeError('Prepared source snapshot is read-only')
 def reset_collection(self,*args,**kwargs):raise RuntimeError('Prepared source snapshot is read-only')
