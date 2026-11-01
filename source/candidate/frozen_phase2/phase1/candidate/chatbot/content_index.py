"""Build a shadow index, reusing embeddings across automatic content refreshes."""
from __future__ import annotations
from contextlib import closing
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import time

from .content_state import atomic_json, generation_directory


class EmbeddingCache:
    def __init__(self, path, model):
        self.path, self.model = Path(path), model
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS vectors (model TEXT, digest TEXT, vector BLOB, PRIMARY KEY(model,digest))")

    @staticmethod
    def digest(text): return hashlib.sha256(text.encode()).hexdigest()

    def get(self, texts):
        with closing(sqlite3.connect(self.path)) as connection:
            result=[]
            for text in texts:
                row=connection.execute("SELECT vector FROM vectors WHERE model=? AND digest=?",(self.model,self.digest(text))).fetchone()
                result.append(list(struct.unpack('<'+'f'*(len(row[0])//4),row[0])) if row else None)
            return result

    def put(self, texts, vectors):
        if len(texts)!=len(vectors): raise ValueError("Embedding count mismatch")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            for text, vector in zip(texts,vectors):
                if not vector: raise ValueError("Empty embedding")
                connection.execute("INSERT OR REPLACE INTO vectors VALUES(?,?,?)",(self.model,self.digest(text),struct.pack('<'+'f'*len(vector),*vector)))


def build_candidate(root, prepared, manifest, logger, batch_size=16):
    from .config import load_config
    from .generation import OllamaClient, InferenceBusy
    from .vector_store import ChromaVectorStore
    root, prepared = Path(root), Path(prepared)
    if not 1<=batch_size<=32:raise ValueError('Embedding batch size must be between one and 32')
    if not manifest.get("complete"): raise ValueError("Source extraction is incomplete")
    generation=manifest["signature"][:24]
    target=generation_directory(root,generation)
    target.mkdir(parents=True,exist_ok=True)
    config=replace(load_config(root),data_path=target,chroma_path=root/'data/chatbot_content/chroma',manifest_path=target/"index_manifest.json",collection_name="learning_"+generation,generation_threads=2)
    store=ChromaVectorStore(config,logger)
    client=OllamaClient(config,logger)
    cache=EmbeddingCache(root/"data/chatbot_content/embedding_cache.sqlite",config.embedding_model)
    rows=[json.loads(line) for line in (prepared/"chunks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if len({row["id"] for row in rows})!=len(rows):raise ValueError("Duplicate chunk identifiers")
    reused=generated=0
    for start in range(0,len(rows),batch_size):
        batch=rows[start:start+batch_size]
        existing=store.collection.get(ids=[row["id"] for row in batch],include=[])
        found=set(existing.get("ids",[]))
        batch=[row for row in batch if row["id"] not in found]
        if not batch:continue
        texts=[row["text"] for row in batch]
        vectors=cache.get(texts)
        missing=[index for index,vector in enumerate(vectors) if vector is None]
        reused+=len(batch)-len(missing)
        if missing:
            while True:
                try:
                    fresh=client.embed_texts([texts[index] for index in missing])
                    break
                except InferenceBusy:
                    time.sleep(2)
            cache.put([texts[index] for index in missing],fresh)
            for index,vector in zip(missing,fresh):vectors[index]=vector
            generated+=len(missing)
        store.add_chunks(batch,vectors)
        try:
            atomic_json(root/"data/chatbot_content/sync_progress.json",{"phase":"embedding","processed":min(start+batch_size,len(rows)),"total":len(rows),"batch_size":batch_size,"reused_embeddings":reused,"generated_embeddings":generated})
        except OSError as exc:
            # Optional UI telemetry must not abort durable vector work. Final
            # manifests and publication still require successful atomic writes.
            logger.warning("Index progress report deferred; error_type=%s",type(exc).__name__)
        time.sleep(.1)
    expected_ids={row["id"] for row in rows}
    indexed=set()
    for start in range(0,len(rows),500):indexed.update(store.collection.get(ids=[row["id"] for row in rows[start:start+500]],include=[]).get("ids",[]))
    if store.count()!=len(rows) or indexed!=expected_ids:raise ValueError("Candidate chunk coverage mismatch")
    # Verify all curated aliases survived serialization into the candidate.
    from .question_lookup import QuestionLookup
    stored_rows=store.fetch_all_chunks()
    # Older writers used Python repr for lists; repair alias metadata in place.
    # Existing vectors and chunk text are retained, so this needs no model calls.
    from .index_metadata import encode_metadata
    expected_by_id={row['id']:row for row in rows}
    repairs=[]
    for stored in stored_rows:
        expected=expected_by_id[stored['id']]
        if not expected['metadata'].get('qa_id'):continue
        encoded=encode_metadata(expected['metadata'])
        if any(stored['metadata'].get(key)!=encoded.get(key) for key in
               ('qa_id','question_text','answer_text','alternate_questions')):
            repairs.append((stored['id'],encoded))
            stored['metadata']=encoded
    for start in range(0,len(repairs),100):
        batch=repairs[start:start+100]
        store.collection.update(ids=[row[0] for row in batch],metadatas=[row[1] for row in batch])
    lookup=QuestionLookup(store.fetch_all_chunks() if repairs else stored_rows)
    for row in rows:
        meta=row["metadata"]
        if not meta.get("qa_id"):continue
        alternates=meta.get("alternate_questions",[])
        if isinstance(alternates,str): alternates=json.loads(alternates)
        for question in [meta.get("question_text",""),*alternates]:
            if question and not any(match["metadata"].get("qa_id")==meta["qa_id"] and match["metadata"].get("answer_text")==meta["answer_text"] for match in lookup.match(question)):
                raise ValueError("Candidate curated-answer coverage mismatch")
    content_manifest={**manifest,"validated":True,"index_storage":"shared_collections","collection_name":config.collection_name,"embedding_model":config.embedding_model,"reused_embeddings":reused,"generated_embeddings":generated}
    atomic_json(target/"content_manifest.json",content_manifest)
    atomic_json(config.manifest_path,{"collection_name":config.collection_name,"index_version":"full_learning_content_v1","files":manifest["files"],"chunk_count":len(rows)})
    return generation,content_manifest
