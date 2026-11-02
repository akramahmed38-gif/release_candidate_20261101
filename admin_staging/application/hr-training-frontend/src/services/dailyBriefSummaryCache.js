// Short-lived, session-scoped counts. Invalidate after every brief mutation.
export function createDailyBriefSummaryCache(fetchSummary, sessionKey, maxAge = 15000) {
  let owner, cached, expires = 0, pending, generation = 0;
  const invalidate = () => { cached = undefined; expires = 0; pending = undefined; generation += 1; };
  const checkSession = () => {
    const key = sessionKey();
    if (key !== owner) { owner = key; invalidate(); }
  };
  const peek = () => {
    checkSession();
    return cached && Date.now() < expires ? cached.data : null;
  };
  const get = () => {
    checkSession();
    if (peek()) return Promise.resolve(cached);
    if (pending) return pending;
    const started = generation;
    const job = Promise.resolve().then(fetchSummary).then(response => {
      checkSession();
      if (started !== generation) return get();
      const counts = response?.data;
      if (!counts || !['drafts', 'live', 'archived'].every(key => Number.isInteger(counts[key]) && counts[key] >= 0)) {
        throw new Error('Unable to load Daily Brief counts. Please retry.');
      }
      cached = response;
      expires = Date.now() + maxAge;
      return response;
    }).finally(() => { if (pending === job) pending = undefined; });
    pending = job;
    return job;
  };
  return { get, peek, invalidate };
}
