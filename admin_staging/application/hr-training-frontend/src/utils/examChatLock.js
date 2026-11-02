const EXAM_SESSION_STORAGE_PREFIX = 'exam_session_';
export const EXAM_CHAT_LOCK_EVENT = 'hr-training-exam-chat-lock-change';

function normalizeRole(user) {
  const rawRole = (user?.role || user?.department || '').toLowerCase().trim();
  return rawRole === 'employee' ? 'retail' : rawRole;
}

function getUserSessionIdentities(user) {
  return [
    user?.hrid,
    user?.hr_id,
    user?.employee_id,
    user?.email,
  ]
    .map((value) => String(value || '').trim())
    .filter(Boolean);
}

function parseStoredSession(rawValue) {
  if (!rawValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawValue);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (_error) {
    return null;
  }
}

function isMatchingKeyForUser(key, identities) {
  const normalizedKey = String(key || '').toLowerCase();
  return identities.some((identity) => normalizedKey.endsWith(`_${identity.toLowerCase()}`));
}

export function broadcastExamChatLockState() {
  if (typeof window === 'undefined') {
    return;
  }

  window.dispatchEvent(new CustomEvent(EXAM_CHAT_LOCK_EVENT));
}

export function getActiveExamChatLock(user) {
  if (typeof window === 'undefined') {
    return { locked: false };
  }

  const normalizedRole = normalizeRole(user);
  if (normalizedRole !== 'retail') {
    return { locked: false };
  }

  const identities = getUserSessionIdentities(user);
  if (!identities.length) {
    return { locked: false };
  }

  const nowMs = Date.now();
  const keysToRemove = [];

  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index);
    if (!key || !key.startsWith(EXAM_SESSION_STORAGE_PREFIX)) {
      continue;
    }
    if (!isMatchingKeyForUser(key, identities)) {
      continue;
    }

    const storedSession = parseStoredSession(window.localStorage.getItem(key));
    if (!storedSession) {
      keysToRemove.push(key);
      continue;
    }

    if (storedSession.status !== 'in-progress') {
      continue;
    }

    const expiresAtMs = Date.parse(storedSession.expiresAt || storedSession.expires_at || '');
    if (Number.isFinite(expiresAtMs) && expiresAtMs <= nowMs) {
      keysToRemove.push(key);
      continue;
    }

    return {
      locked: true,
      sessionKey: key,
      expiresAt: storedSession.expiresAt || storedSession.expires_at || null,
      attemptId: storedSession.attemptId || storedSession.attempt_id || null,
    };
  }

  if (keysToRemove.length) {
    keysToRemove.forEach((key) => window.localStorage.removeItem(key));
    broadcastExamChatLockState();
  }

  return { locked: false };
}
