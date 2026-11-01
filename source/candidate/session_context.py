"""Bind candidate business context to both conversation and session identity.

The inherited store retains its owner isolation, expiry and locking. Its
conversation-only key is adapted here without editing the preserved store.
"""
import hashlib
import json


class SessionScopedBusinessContext:
    def __init__(self, store):
        self._store = store

    @staticmethod
    def _identity(conversation_id, session_id):
        conversation = str(conversation_id or "").strip()
        session = str(session_id or "").strip()
        if not conversation and not session:
            return None
        encoded = json.dumps([conversation, session], ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
        return "candidate-session:" + hashlib.sha256(encoded).hexdigest()

    def get_business_context(self, conversation_id, session_id):
        return self._store.get_business_context(self._identity(conversation_id, session_id), None)

    def set_business_context(self, conversation_id, session_id, value):
        return self._store.set_business_context(self._identity(conversation_id, session_id), None, value)

    def get_snapshot(self, conversation_id, session_id):
        return self._store.get_snapshot(self._identity(conversation_id, session_id), None)

    def clear(self, conversation_id, session_id):
        return self._store.clear(self._identity(conversation_id, session_id), None)

    def __getattr__(self, name):
        # Preserve existing checkpoint/inspection access to the inherited
        # private store. No alternate business-context lookup is introduced.
        return getattr(self._store, name)


def scoped_business_context(store):
    return store if isinstance(store, SessionScopedBusinessContext) else SessionScopedBusinessContext(store)
