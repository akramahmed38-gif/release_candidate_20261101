import { TextEncoder, TextDecoder } from 'node:util';
import { businessVocabularyService } from './auth';
import api from './api';
vi.mock('./api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
beforeEach(() => { globalThis.TextEncoder = TextEncoder; vi.clearAllMocks(); });

it.each([
  ['createCategory', null, '/categories'], ['updateCategory', 'cat', '/categories/cat/save'],
  ['createItem', null, '/items'], ['updateItem', 'item', '/items/item/save'],
])('encodes %s and verifies the saved ID', async (method, id, path) => {
  const payload = { name: 'Banking', arabic_name: 'الفروع', english_text: 'user@example.test' };
  api.post.mockResolvedValue({ data: { id: id || 'new' } });
  await businessVocabularyService[method](...(id ? [id, payload] : [payload]));
  const [url, wire] = api.post.mock.calls[0];
  expect(url).toBe('/api/v1/business-vocabulary' + path);
  expect(Object.keys(wire)).toEqual(['payload_b64']);
  expect(JSON.stringify(wire)).not.toContain('user@example.test');
  expect(JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(wire.payload_b64), c => c.charCodeAt(0))))).toEqual(payload);
});

it('rejects an HTML proxy response instead of reporting a successful save', async () => {
  api.post.mockResolvedValue({ data: '<html>Request blocked</html>' });
  await expect(businessVocabularyService.createCategory({ name: 'test' })).rejects.toThrow('not confirmed');
});

it('rejects a mismatched ID and oversized payload without retrying', async () => {
  api.post.mockResolvedValue({ data: { item: { id: 'wrong' } } });
  await expect(businessVocabularyService.updateItem('expected', {})).rejects.toThrow('not confirmed');
  await expect(businessVocabularyService.createItem({ english_text: 'a'.repeat(65536) })).rejects.toThrow('too large');
  expect(api.post).toHaveBeenCalledTimes(1);
});
