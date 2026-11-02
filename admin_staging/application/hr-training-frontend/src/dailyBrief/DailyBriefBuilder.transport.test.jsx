import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import DailyBriefBuilder from './DailyBriefBuilder';
import { dailyBriefService } from '../services/auth';

vi.mock('../services/auth', () => ({ dailyBriefService: {
  createBrief: vi.fn(), updateBrief: vi.fn(), getBrief: vi.fn(), publishBrief: vi.fn(), uploadImage: vi.fn(),
} }));

beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function start() {
  render(<MemoryRouter initialEntries={['/daily-brief/new']}><Routes>
    <Route path="/daily-brief/new" element={<DailyBriefBuilder />} />
    <Route path="/daily-brief/:briefId/edit" element={<div>Saved brief editor</div>} />
    <Route path="/daily-brief" element={<Result />} />
  </Routes></MemoryRouter>);
  fireEvent.change(screen.getByLabelText('Page title'), { target: { value: 'Keep my work' } });
}

function Result() {
  const location = useLocation();
  return <div>{location.state?.tab}: {location.state?.message}</div>;
}

function fillPublishableBrief() {
  fireEvent.click(screen.getByRole('button', { name: 'Highlight', exact: true }));
  fireEvent.change(screen.getByLabelText('Heading'), { target: { value: 'News' } });
  fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Retail update' } });
}

async function publish() {
  fireEvent.click(await screen.findByRole('button', { name: 'Publish to Retail' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Publish', exact: true }));
}

it('shows the missing Highlight message before saving or publishing', async () => {
  start();
  fireEvent.click(screen.getByRole('button', { name: 'Highlight', exact: true }));
  fireEvent.change(screen.getByLabelText('Heading'), { target: { value: 'News' } });
  await publish();
  expect(await screen.findByText('Block 1 (highlight): Message is required before publishing.')).toBeInTheDocument();
  expect(dailyBriefService.createBrief).not.toHaveBeenCalled();
  expect(dailyBriefService.publishBrief).not.toHaveBeenCalled();
});

it('keeps publish errors visible and reuses the saved draft on retry', async () => {
  dailyBriefService.createBrief.mockResolvedValue({ data: { id: 'created-1', status: 'DRAFT' } });
  dailyBriefService.updateBrief.mockResolvedValue({ data: { item: { id: 'created-1', status: 'DRAFT' } } });
  dailyBriefService.publishBrief.mockRejectedValueOnce({ response: { data: { detail: 'Publishing validation failed' } } })
    .mockResolvedValueOnce({ data: { message: 'Daily Brief published' } });
  start();
  fillPublishableBrief();
  await publish();
  expect(await screen.findByText('Publishing validation failed')).toBeInTheDocument();
  expect(screen.queryByText('Saved brief editor')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Message')).toHaveValue('Retail update');
  await publish();
  expect(await screen.findByText('LIVE: Daily Brief is now Live. No email has been sent.')).toBeInTheDocument();
  expect(dailyBriefService.createBrief).toHaveBeenCalledTimes(1);
  expect(dailyBriefService.updateBrief).toHaveBeenCalledWith('created-1', expect.any(Object));
});

it('keeps the new brief and displays an unconfirmed-save error', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  dailyBriefService.createBrief.mockRejectedValue(new Error('The server did not confirm the save.'));
  start();
  fireEvent.click(screen.getByRole('button', { name: 'Save Draft' }));
  expect(await screen.findByText('The server did not confirm the save.')).toBeInTheDocument();
  expect(screen.getByLabelText('Page title')).toHaveValue('Keep my work');
  expect(JSON.parse(sessionStorage.getItem('daily-brief:new-brief-recovery')).title).toBe('Keep my work');
});

it('displays structured validation errors without crashing the editor', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  dailyBriefService.createBrief.mockRejectedValue({ response: { data: { detail: [{ msg: 'Title is too long' }] } } });
  start();
  fireEvent.click(screen.getByRole('button', { name: 'Save Draft' }));
  expect(await screen.findByText('Title is too long')).toBeInTheDocument();
});

it('does not send a second save while the first is pending', () => {
  dailyBriefService.createBrief.mockReturnValue(new Promise(() => {}));
  start();
  const button = screen.getByRole('button', { name: 'Save Draft' });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(dailyBriefService.createBrief).toHaveBeenCalledTimes(1);
  expect(button).toBeDisabled();
});
