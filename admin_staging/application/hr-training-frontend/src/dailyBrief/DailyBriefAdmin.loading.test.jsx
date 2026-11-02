import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DailyBriefAdmin from './DailyBriefAdmin';
import { dailyBriefService } from '../services/auth';
vi.mock('../services/auth', () => ({ dailyBriefService: {
  peekSummary: vi.fn(), getSummary: vi.fn(), listBriefs: vi.fn(), archiveBrief: vi.fn(),
} }));
const counts = { drafts: 3, live: 1, archived: 7 };
const start = (state) => render(<MemoryRouter initialEntries={[{ pathname: '/', state }]}><DailyBriefAdmin /></MemoryRouter>);
beforeEach(() => {
  vi.resetAllMocks();
  dailyBriefService.peekSummary.mockReturnValue(null);
  dailyBriefService.getSummary.mockResolvedValue({ data: counts });
});
afterEach(cleanup);

it('renders counts while the list request is still pending', async () => {
  dailyBriefService.listBriefs.mockReturnValue(new Promise(() => {}));
  start();
  await waitFor(() => expect(screen.getByLabelText('Draft count')).toHaveTextContent('3'));
  expect(screen.getByLabelText('Loading Daily Briefs')).toBeInTheDocument();
});

it('renders the list without waiting for counts and never shows placeholder zeros', async () => {
  dailyBriefService.getSummary.mockReturnValue(new Promise(() => {}));
  dailyBriefService.listBriefs.mockResolvedValue({ data: { items: [{ id: '1', title: 'Ready first', status: 'DRAFT' }] } });
  start();
  expect(await screen.findByText('Ready first')).toBeInTheDocument();
  expect(screen.getByLabelText('Draft count')).not.toHaveTextContent('0');
});

it('shows cached counts immediately and avoids refetching them on tab switches', async () => {
  dailyBriefService.peekSummary.mockReturnValue(counts);
  dailyBriefService.listBriefs.mockResolvedValue({ data: { items: [] } });
  start();
  expect(screen.getByLabelText('Archived count')).toHaveTextContent('7');
  expect(screen.getByRole('tab', { name: 'Live', exact: true })).toHaveAttribute('aria-selected', 'true');
  expect(dailyBriefService.listBriefs).toHaveBeenCalledWith({ status: 'LIVE', search: '' });
  fireEvent.click(screen.getByRole('tab', { name: 'Draft', exact: true }));
  await waitFor(() => expect(dailyBriefService.listBriefs).toHaveBeenCalledTimes(2));
  expect(dailyBriefService.getSummary).toHaveBeenCalledTimes(1);
});

it('ignores a slow previous tab response', async () => {
  let resolveDrafts;
  dailyBriefService.listBriefs.mockImplementationOnce(() => new Promise(resolve => { resolveDrafts = resolve; }))
    .mockResolvedValueOnce({ data: { items: [{ id: 'live', title: 'Current Live', status: 'LIVE' }] } });
  start({ tab: 'DRAFT' }); fireEvent.click(screen.getByRole('tab', { name: 'Live', exact: true }));
  expect(await screen.findByText('Current Live')).toBeInTheDocument();
  await act(async () => resolveDrafts({ data: { items: [{ id: 'draft', title: 'Old tab result', status: 'DRAFT' }] } }));
  expect(screen.queryByText('Old tab result')).not.toBeInTheDocument();
  expect(screen.getByText('Current Live')).toBeInTheDocument();
});

it('shows a summary failure without hiding a successfully loaded list', async () => {
  dailyBriefService.getSummary.mockRejectedValue(new Error('offline'));
  dailyBriefService.listBriefs.mockResolvedValue({ data: { items: [{ id: '1', title: 'Available brief', status: 'DRAFT' }] } });
  start();
  expect(await screen.findByText('Counts could not be refreshed.')).toBeInTheDocument();
  expect(screen.getByText('Available brief')).toBeInTheDocument();
});
