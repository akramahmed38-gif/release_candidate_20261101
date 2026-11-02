import { createDailyBriefSummaryCache } from './dailyBriefSummaryCache';
const counts = (drafts = 1) => ({ data: { drafts, live: 1, archived: 2 } });

it('shares a pending request and reuses recent counts', async () => {
  let resolve;
  const fetch = vi.fn(() => new Promise(done => { resolve = done; }));
  const cache = createDailyBriefSummaryCache(fetch, () => 'session');
  const first = cache.get(); const second = cache.get();
  expect(first).toBe(second);
  await Promise.resolve(); resolve(counts());
  await first;
  expect(cache.peek()).toEqual(counts().data);
  await cache.get(); expect(fetch).toHaveBeenCalledTimes(1);
});

it('expires and separates sessions', async () => {
  let key = 'first'; let now = 1000;
  const clock = vi.spyOn(Date, 'now').mockImplementation(() => now);
  try {
    const fetch = vi.fn().mockResolvedValue(counts());
    const cache = createDailyBriefSummaryCache(fetch, () => key);
    await cache.get(); now += 15001;
    expect(cache.peek()).toBeNull(); await cache.get();
    key = 'second'; expect(cache.peek()).toBeNull(); await cache.get();
    expect(fetch).toHaveBeenCalledTimes(3);
  } finally { clock.mockRestore(); }
});

it('does not restore pre-mutation counts from an older in-flight response', async () => {
  let resolveOld;
  const fetch = vi.fn().mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }))
    .mockResolvedValueOnce(counts(2));
  const cache = createDailyBriefSummaryCache(fetch, () => 'session');
  const old = cache.get(); await Promise.resolve();
  cache.invalidate(); await cache.get(); resolveOld(counts(1));
  expect((await old).data.drafts).toBe(2);
  expect(cache.peek().drafts).toBe(2);
});

it('rejects HTML error pages and allows retry after failures', async () => {
  const fetch = vi.fn().mockResolvedValueOnce({ data: '<html>Blocked</html>' }).mockResolvedValueOnce(counts());
  const cache = createDailyBriefSummaryCache(fetch, () => 'session');
  await expect(cache.get()).rejects.toThrow('Unable to load');
  expect(cache.peek()).toBeNull(); await cache.get();
  expect(cache.peek()).toEqual(counts().data);
});
