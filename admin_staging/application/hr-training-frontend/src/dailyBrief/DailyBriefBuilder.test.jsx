import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import DailyBriefBuilder from './DailyBriefBuilder';
import DailyBriefPreviewPage from './DailyBriefPreviewPage';
import { dailyBriefService } from '../services/auth';
import { clearBriefRecovery, readBriefRecovery } from './briefRecovery';

vi.mock('../services/auth', () => ({
  dailyBriefService: {
    getBrief: vi.fn(), createBrief: vi.fn(), updateBrief: vi.fn(), publishBrief: vi.fn(), uploadImage: vi.fn(),
  },
}));

let saved;
const makeBrief = (id = 'draft-1') => ({
  id, title: 'Original draft', brief_date: '2026-09-21', status: 'DRAFT',
  blocks: [
    { id: 'highlight-1', block_type: 'highlight', content: { heading: 'Original heading', text: 'Saved message', style: 'important' } },
    { id: 'text-1', block_type: 'text', content: { html: '<p>Original rich text</p>' } },
    { id: 'image-1', block_type: 'image', content: { image_url: '/test.png', caption: 'Original caption', alt: 'Test image' } },
  ],
});
const start = (path = '/daily-brief/draft-1/edit') => {
  const router = createMemoryRouter([
    { path: '/daily-brief/new', element: <DailyBriefBuilder /> },
    { path: '/daily-brief/:briefId/edit', element: <DailyBriefBuilder /> },
    { path: '/daily-brief/preview', element: <DailyBriefPreviewPage /> },
    { path: '/daily-brief', element: <div>Brief list</div> },
  ], { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
};
const fill = (label, value) => fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value } });
const click = (name) => fireEvent.click(screen.getByRole('button', { name, exact: true }));
const loaded = () => screen.findByLabelText('Page title', { exact: true });
const previewAndBack = async (router, back = 'button') => {
  click('Preview Retail');
  await screen.findByRole('button', { name: 'Back to Daily Briefs' });
  if (back === 'history') await act(() => router.navigate(-1));
  else click('Back to Daily Briefs');
  await loaded();
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
  window.sessionStorage.clear();
  [undefined, 'draft-1', 'draft-2', 'created-1', 'missing'].forEach(clearBriefRecovery);
  saved = makeBrief();
  dailyBriefService.getBrief.mockImplementation(async (id) => ({ data: { item: id === saved.id ? saved : makeBrief(id) } }));
  dailyBriefService.updateBrief.mockImplementation(async (id, form) => {
    saved = { ...saved, ...structuredClone(form), id };
    return { data: { item: saved } };
  });
  dailyBriefService.createBrief.mockImplementation(async (form) => {
    saved = { ...structuredClone(form), id: 'created-1', status: 'DRAFT' };
    return { data: saved };
  });
});
afterEach(cleanup);

it.each(['button', 'history'])('preserves all unsaved draft content when returning via %s', async (back) => {
  const router = start();
  await loaded();
  fill('Page title', 'Edited title');
  fill('Brief date', '2026-09-22');
  fill('Heading', 'Edited heading');
  fill('Message', 'Unsaved message');
  fill('Caption', 'Edited image caption');
  const richText = screen.getByRole('textbox', { name: 'Text block' });
  richText.innerHTML = '<p><strong>Formatted edit</strong></p>';
  fireEvent.input(richText);
  await previewAndBack(router, back);
  expect(screen.getByLabelText('Page title')).toHaveValue('Edited title');
  expect(screen.getByLabelText('Brief date')).toHaveValue('2026-09-22');
  expect(screen.getByLabelText('Heading')).toHaveValue('Edited heading');
  expect(screen.getByLabelText('Message')).toHaveValue('Unsaved message');
  expect(screen.getByLabelText('Caption')).toHaveValue('Edited image caption');
  expect(screen.getByRole('textbox', { name: 'Text block' }).innerHTML).toBe('<p><strong>Formatted edit</strong></p>');
  expect(dailyBriefService.updateBrief).not.toHaveBeenCalled();
  click('Save Draft');
  await screen.findByText('Draft saved.');
  expect(saved.blocks[0].content.text).toBe('Unsaved message');
  expect(saved.blocks[1].content.html).toContain('<strong>Formatted edit</strong>');
  expect(saved.blocks[2].content.caption).toBe('Edited image caption');
  expect(readBriefRecovery('draft-1')).toBeNull();
});

it('preserves a new brief through preview, creation, editing, and reopening', async () => {
  const router = start('/daily-brief/new');
  await loaded();
  fill('Page title', 'New brief title');
  click('Highlight');
  fill('Heading', 'New heading');
  fill('Message', 'New message');
  await previewAndBack(router);
  expect(screen.getByLabelText('Message')).toHaveValue('New message');
  click('Save Draft');
  await waitFor(() => expect(router.state.location.pathname).toBe('/daily-brief/created-1/edit'));
  await loaded();
  fill('Message', 'Updated new message');
  click('Save Draft');
  await screen.findByText('Draft saved.');
  expect(dailyBriefService.createBrief).toHaveBeenCalledTimes(1);
  expect(dailyBriefService.updateBrief).toHaveBeenCalledWith('created-1', expect.objectContaining({ title: 'New brief title' }));
  expect(readBriefRecovery()).toBeNull();
  cleanup();
  start('/daily-brief/created-1/edit');
  await loaded();
  expect(screen.getByLabelText('Message')).toHaveValue('Updated new message');
});

it('keeps the existing ID when an update response contains only a success message', async () => {
  dailyBriefService.updateBrief.mockResolvedValue({ data: { message: 'Daily Brief updated' } });
  const router = start();
  await loaded();
  fill('Message', 'First save');
  click('Save Draft');
  await screen.findByText('Draft saved.');
  fill('Message', 'Second save');
  click('Save Draft');
  await screen.findByText('Draft saved.');
  expect(router.state.location.pathname).toBe('/daily-brief/draft-1/edit');
  expect(dailyBriefService.updateBrief.mock.calls.map(([id]) => id)).toEqual(['draft-1', 'draft-1']);
});

it('preserves preview content and saves successfully when session storage is unavailable', async () => {
  for (const method of ['getItem', 'setItem', 'removeItem']) {
    vi.spyOn(Storage.prototype, method).mockImplementation(() => { throw new DOMException('Blocked', 'SecurityError'); });
  }
  const router = start('/daily-brief/new');
  await loaded();
  fill('Page title', 'Storage unavailable');
  click('Highlight');
  fill('Message', 'Keep this message');
  await previewAndBack(router, 'history');
  expect(screen.getByLabelText('Message')).toHaveValue('Keep this message');
  click('Save Draft');
  await waitFor(() => expect(router.state.location.pathname).toBe('/daily-brief/created-1/edit'));
  await screen.findByText('Draft saved.');
  expect(readBriefRecovery()).toBeNull();
});

it('retains changes after a failed save and restores them on reopening the editor', async () => {
  dailyBriefService.updateBrief.mockRejectedValue({ response: { status: 500, data: { detail: 'Temporary save failure' } } });
  start();
  await loaded();
  fill('Message', 'Recover after failure');
  click('Save Draft');
  await screen.findByText('Temporary save failure');
  expect(readBriefRecovery('draft-1').form.blocks[0].content.text).toBe('Recover after failure');
  cleanup();
  start();
  await loaded();
  expect(screen.getByLabelText('Message')).toHaveValue('Recover after failure');
});

it('does not overwrite edits entered while a save request is in flight', async () => {
  let completeSave;
  dailyBriefService.updateBrief.mockImplementationOnce(() => new Promise((resolve) => { completeSave = resolve; }));
  start();
  await loaded();
  fill('Message', 'Submitted edit');
  click('Save Draft');
  fill('Message', 'Newer unsaved edit');
  await act(async () => completeSave({ data: { message: 'Saved' } }));
  await screen.findByText('Saved. Your latest changes still need to be saved.');
  expect(screen.getByLabelText('Message')).toHaveValue('Newer unsaved edit');
  expect(readBriefRecovery('draft-1').form.blocks[0].content.text).toBe('Newer unsaved edit');
  click('Save Draft');
  await screen.findByText('Draft saved.');
  expect(saved.blocks[0].content.text).toBe('Newer unsaved edit');
});

it('isolates recovery between different drafts and a new brief', async () => {
  const router = start();
  await loaded();
  fill('Message', 'Draft one only');
  await act(() => router.navigate('/daily-brief/draft-2/edit'));
  await loaded();
  expect(screen.getByLabelText('Message')).toHaveValue('Saved message');
  await act(() => router.navigate('/daily-brief/new'));
  await loaded();
  expect(screen.getByLabelText('Page title')).toHaveValue('');
  expect(screen.queryByLabelText('Message')).not.toBeInTheDocument();
  await act(() => router.navigate('/daily-brief/draft-1/edit'));
  await loaded();
  expect(screen.getByLabelText('Message')).toHaveValue('Draft one only');
});

it('blocks saving if the requested draft could not be loaded', async () => {
  dailyBriefService.getBrief.mockRejectedValue({ response: { status: 404, data: { detail: 'Daily Brief not found' } } });
  start('/daily-brief/missing/edit');
  await screen.findByText('Daily Brief not found');
  expect(screen.getByRole('button', { name: 'Save Draft' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Publish to Retail' })).toBeDisabled();
  expect(dailyBriefService.updateBrief).not.toHaveBeenCalled();
});
