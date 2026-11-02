import { TextEncoder } from 'node:util';
import { dailyBriefService } from './auth';
import api from './api';
vi.mock('./api', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }));
const form = { title: 'Draft', blocks: [] };
beforeEach(() => {
  globalThis.TextEncoder = TextEncoder;
  vi.clearAllMocks();
  api.post.mockImplementation(async url => ({ data: url.endsWith('/publish')
    ? { message: 'Daily Brief published' }
    : url.endsWith('/restore-live') ? { message: 'Daily Brief restored as live' } : { id: '1' } }));
  api.delete.mockResolvedValue({ data: {} });
  api.get.mockResolvedValue({ data: { drafts: 1, live: 1, archived: 0 } });
});

it.each([
  ['createBrief', form], ['updateBrief', '1', form], ['deleteBrief', '1'],
  ['duplicateBrief', '1'], ['publishBrief', '1'], ['archiveBrief', '1'], ['restoreLiveBrief', '1'],
])('invalidates counts after %s', async (method, ...args) => {
  await dailyBriefService.deleteBrief('setup-cache-reset');
  await dailyBriefService.getSummary();
  await dailyBriefService.getSummary();
  expect(api.get).toHaveBeenCalledTimes(1);
  await dailyBriefService[method](...args);
  expect(dailyBriefService.peekSummary()).toBeNull();
  api.get.mockResolvedValue({ data: { drafts: 2, live: 0, archived: 1 } });
  expect((await dailyBriefService.getSummary()).data.drafts).toBe(2);
  expect(api.get).toHaveBeenCalledTimes(2);
});
