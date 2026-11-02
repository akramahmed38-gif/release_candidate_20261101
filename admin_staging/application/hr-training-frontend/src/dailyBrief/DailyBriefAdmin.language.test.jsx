import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LanguageProvider, useLanguage } from '../context/LanguageContext';
import { dailyBriefService } from '../services/auth';
import DailyBriefAdmin from './DailyBriefAdmin';

vi.mock('../services/auth', () => ({ dailyBriefService: {
  peekSummary: vi.fn(), getSummary: vi.fn(), listBriefs: vi.fn(), getAnalytics: vi.fn(),
  deleteBrief: vi.fn(), notifyRetail: vi.fn(), getAudience: vi.fn(),
} }));

function LanguageSwitch() {
  const { setLanguage } = useLanguage();
  return <><button onClick={() => setLanguage('en')}>EN</button><button onClick={() => setLanguage('ar')}>AR</button></>;
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.setItem('app_lang', 'ar');
  dailyBriefService.peekSummary.mockReturnValue({ live: 1, drafts: 1234, archived: 9876 });
  dailyBriefService.getSummary.mockResolvedValue({ data: { live: 1, drafts: 1234, archived: 9876 } });
  dailyBriefService.listBriefs.mockResolvedValue({ data: { items: [{ id: '1', title: 'Original title', status: 'LIVE', brief_date: '2026-09-27' }] } });
  dailyBriefService.getAudience.mockResolvedValue({ data: { recipients: [{ email: 'a@example.test' }], revision: 1 } });
  dailyBriefService.getAnalytics.mockResolvedValue({ data: { viewed: 0, eligible_retail_users: 2, viewed_users: [] } });
});
afterEach(() => { cleanup(); localStorage.clear(); vi.restoreAllMocks(); });

const start = () => render(<LanguageProvider><MemoryRouter><LanguageSwitch /><DailyBriefAdmin /></MemoryRouter></LanguageProvider>);

it('translates the page and viewer dialog and switches back to English without refetching', async () => {
  start();
  expect(await screen.findByText('Original title')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'الملخص اليومي' })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'المنشور' })).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByLabelText('عدد المسودة')).toHaveTextContent('1234');
  expect(screen.getByLabelText('البحث بالعنوان')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'إنشاء ملخص يومي' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'إرسال الملخص بالبريد' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'المشاهدون' }));
  expect(await screen.findByText('لم يشاهد أي مستخدم من الفروع هذا الملخص بعد.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'تصدير إلى Excel' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'إغلاق' }));
  fireEvent.click(await screen.findByRole('button', { name: 'EN' }));
  expect(screen.getByRole('heading', { name: 'Daily Brief' })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'Live' })).toHaveAttribute('aria-selected', 'true');
  expect(dailyBriefService.listBriefs).toHaveBeenCalledTimes(1);
});

it('uses Arabic confirmations without performing cancelled actions', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  start();
  fireEvent.click(await screen.findByRole('button', { name: 'حذف' }));
  expect(confirm).toHaveBeenLastCalledWith('هل تريد حذف هذا الملخص المنشور؟ لن يعود ظاهرًا لمستخدمي الفروع.');
  fireEvent.click(screen.getByRole('button', { name: 'إرسال الملخص بالبريد' }));
  await waitFor(() => expect(confirm).toHaveBeenLastCalledWith('هل تريد إرسال الملخص اليومي «Original title» باللغة العربية إلى المستلمين المحفوظين وعددهم 1؟'));
  expect(dailyBriefService.deleteBrief).not.toHaveBeenCalled();
  expect(dailyBriefService.notifyRetail).not.toHaveBeenCalled();
});
