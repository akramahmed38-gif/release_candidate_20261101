import { TextEncoder } from 'node:util';
import { encodeBriefPayload, requireBriefSaveResponse } from './dailyBriefTransport';
import { dailyBriefService } from './auth';
import api from './api';

vi.mock('./api', () => ({ default: { post: vi.fn(), put: vi.fn() } }));
beforeEach(() => { globalThis.TextEncoder = TextEncoder; vi.clearAllMocks(); });

const form = { title: '\u0645\u0644\u062e\u0635', brief_date: '2026-09-27', blocks: [
  { id: 'temporary-id', position: 0, block_type: 'text', content: { html: '<p><strong>\u0645\u0631\u062d\u0628\u0627</strong> & notes</p>' } },
] };

it('preserves Unicode and rich text without transmitting raw HTML or editor IDs', () => {
  const wire = encodeBriefPayload(form);
  expect(JSON.stringify(wire)).not.toContain('<p>');
  const decoded = JSON.parse(Buffer.from(wire.payload_b64, 'base64').toString('utf8'));
  expect(decoded.title).toBe(form.title);
  expect(decoded.blocks[0].content).toEqual(form.blocks[0].content);
  expect(decoded.blocks[0]).not.toHaveProperty('id');
});

it('uses encoded POST for both create and edit', async () => {
  api.post.mockResolvedValueOnce({ data: { id: 'new-1' } }).mockResolvedValueOnce({ data: { item: { id: 'new-1' } } });
  await dailyBriefService.createBrief(form);
  await dailyBriefService.updateBrief('new-1', form);
  expect(api.post.mock.calls.map(call => call[0])).toEqual(['/api/v1/daily-briefs', '/api/v1/daily-briefs/new-1/save']);
  for (const call of api.post.mock.calls) expect(call[1]).toEqual(encodeBriefPayload(form));
  expect(api.put).not.toHaveBeenCalled();
});

it.each(['<html>Request blocked</html>', {}, { message: 'blocked' }, { item: { id: 'other-id' } }])('rejects an unconfirmed save response: %j', data => {
  expect(() => requireBriefSaveResponse({ data }, 'expected-id')).toThrow('did not confirm');
});

it('rejects oversized content before sending it', () => {
  expect(() => encodeBriefPayload({ ...form, title: 'x'.repeat(2 * 1024 * 1024) })).toThrow('too large');
});

it('does not retry a blocked request automatically', async () => {
  api.post.mockRejectedValue({ response: { status: 403 } });
  await expect(dailyBriefService.updateBrief('new-1', form)).rejects.toMatchObject({ response: { status: 403 } });
  expect(api.post).toHaveBeenCalledTimes(1);
});

it('requires a confirmed publish response and sends a valid JSON body', async () => {
  api.post.mockResolvedValueOnce({ data: '<html>Blocked</html>' });
  await expect(dailyBriefService.publishBrief('draft-1')).rejects.toThrow('did not confirm');
  api.post.mockResolvedValueOnce({ data: { message: 'Daily Brief published' } });
  await dailyBriefService.publishBrief('draft-1');
  expect(api.post).toHaveBeenLastCalledWith('/api/v1/daily-briefs/draft-1/publish', {});
});
