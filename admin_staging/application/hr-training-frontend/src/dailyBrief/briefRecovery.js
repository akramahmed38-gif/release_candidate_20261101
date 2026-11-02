// Keep a tab-local fallback when browser storage is disabled or full.
const recovery = new Map();
const recoveryKey = (briefId) => briefId
  ? `daily-brief:edit-recovery:${briefId}`
  : 'daily-brief:new-brief-recovery';

export function readBriefRecovery(briefId) {
  const key = recoveryKey(briefId);
  if (recovery.has(key)) return recovery.get(key);
  try {
    const saved = JSON.parse(window.sessionStorage.getItem(key) || 'null');
    // Accept the original new-brief recovery format as well.
    const snapshot = saved?.form ? saved : { form: saved, status: 'DRAFT' };
    if (typeof snapshot.form?.title !== 'string' || !Array.isArray(snapshot.form?.blocks)) return null;
    return snapshot;
  } catch {
    return null;
  }
}

export function writeBriefRecovery(briefId, snapshot) {
  const key = recoveryKey(briefId);
  recovery.set(key, snapshot);
  try {
    window.sessionStorage.setItem(key, JSON.stringify(snapshot));
  } catch {
    // Navigation still preserves the form through the in-memory fallback.
  }
}

export function clearBriefRecovery(briefId) {
  const key = recoveryKey(briefId);
  recovery.delete(key);
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    // A storage failure must not turn a successful API save into an error.
  }
}
