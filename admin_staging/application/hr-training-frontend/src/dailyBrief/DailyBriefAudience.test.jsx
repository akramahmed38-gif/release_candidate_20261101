import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DailyBriefAudience from './DailyBriefAudience';
import { dailyBriefService } from '../services/auth';
import { encodeDailyBriefEnvelope } from '../services/dailyBriefTransport';
vi.mock('../services/auth', () => ({ dailyBriefService: { getAudience: vi.fn(), saveAudience: vi.fn() } }));
beforeEach(() => {
  vi.resetAllMocks();
  dailyBriefService.getAudience.mockResolvedValue({ data: { recipients: [{ name: 'Team', email: 'team@example.test' }], revision: 2 } });
});
afterEach(cleanup);

it('saves the edited audience with its revision without sending email', async () => {
  dailyBriefService.saveAudience.mockResolvedValue({ data: { recipients: [{ name: 'Team', email: 'new@example.test' }], revision: 3 } });
  render(<MemoryRouter><DailyBriefAudience /></MemoryRouter>);
  const email = await screen.findByDisplayValue('team@example.test');
  fireEvent.change(email, { target: { value: 'new@example.test' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save audience' }));
  expect(await screen.findByText('Audience saved. No email was sent.')).toBeInTheDocument();
  expect(dailyBriefService.saveAudience).toHaveBeenCalledWith({ recipients: [{ name: 'Team', email: 'new@example.test' }], revision: 2 });
});

it('retains edited emails if saving is rejected', async () => {
  dailyBriefService.saveAudience.mockRejectedValue({ response: { status: 409 } });
  render(<MemoryRouter><DailyBriefAudience /></MemoryRouter>);
  fireEvent.change(await screen.findByDisplayValue('team@example.test'), { target: { value: 'new@example.test' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save audience' }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Another administrator'));
  expect(screen.getByDisplayValue('new@example.test')).toBeInTheDocument();
});

it('encodes audience emails and Unicode names into a single bounded envelope', () => {
  const input = { recipients: [{ name: 'فريق', email: 'team@example.test' }], revision: 2 };
  const wire = encodeDailyBriefEnvelope(input);
  expect(Object.keys(wire)).toEqual(['payload_b64']);
  expect(JSON.stringify(wire)).not.toContain('team@example.test');
  expect(JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(wire.payload_b64), c => c.charCodeAt(0))))).toEqual(input);
});
