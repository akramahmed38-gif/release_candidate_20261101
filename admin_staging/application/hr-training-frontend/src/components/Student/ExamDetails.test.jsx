import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ExamDetails from './ExamDetails';

const mockGetExamById = vi.fn();
const mockGetExamResultsDetails = vi.fn();

vi.mock('../../context/LanguageContext', () => ({
  useLanguage: () => ({
    isArabic: false,
    t: (english) => english,
  }),
}));

vi.mock('../../utils/examChatLock', () => ({
  broadcastExamChatLockState: vi.fn(),
}));

vi.mock('../../services/auth', () => ({
  examService: {
    getExamById: (...args) => mockGetExamById(...args),
    getExamResultsDetails: (...args) => mockGetExamResultsDetails(...args),
    downloadExamResultsExcel: vi.fn(),
    startExam: vi.fn(),
    submitExam: vi.fn(),
  },
  authService: {
    getCurrentUser: () => ({
      role: 'admin',
      email: 'admin@fawry.com',
    }),
  },
}));

const createDeferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

const buildExam = (examId, title) => ({
  exam_id: examId,
  title,
  description: `${title} description`,
  exam_status: 'Open',
  duration_minutes: 30,
  number_of_attempts_allowed: 1,
  attempts_used: 0,
  attempts_left: 1,
  start_date: '2026-08-20T09:00:00Z',
  end_date: '2026-08-31T21:00:00Z',
  questions: [],
  audience: {
    mode: 'filters',
    filters: {
      departments: ['Retail'],
    },
  },
  audience_summary: {
    count: 3,
    hr_ids: ['23614', '23615', '23616'],
  },
});

const buildResultsPayload = ({
  employeesAssigned,
  employeesAttempted,
  attemptRate,
  passRate,
  totalPassed,
  averageScore,
  totalAttempts,
  averageDurationSeconds,
  lastSubmissionAt,
  topPerformer,
}) => ({
  results_summary: {
    employees_assigned: employeesAssigned,
    employees_attempted: employeesAttempted,
    attempt_rate_percentage: attemptRate,
    pass_rate_percentage: passRate,
    total_passed: totalPassed,
    average_score_percentage: averageScore,
    total_attempts: totalAttempts,
    average_duration_seconds: averageDurationSeconds,
    max_possible_score: 35,
    questions_count: 35,
    last_submission_at: lastSubmissionAt,
    top_performer: topPerformer,
  },
  results_details: [],
  participants_overview: [],
});

const RouteHarness = () => {
  const navigate = useNavigate();

  return (
    <>
      <button type="button" onClick={() => navigate('/hr/exams/exam-b')}>
        Go to exam B
      </button>
      <ExamDetails />
    </>
  );
};

describe('ExamDetails', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('keeps copied exam analytics isolated when the previous exam responds late', async () => {
    const examADetails = createDeferred();
    const examAResults = createDeferred();
    const examBDetails = createDeferred();
    const examBResults = createDeferred();

    mockGetExamById.mockImplementation((examId) => {
      if (examId === 'exam-a') {
        return examADetails.promise;
      }
      if (examId === 'exam-b') {
        return examBDetails.promise;
      }
      throw new Error(`Unexpected exam id: ${examId}`);
    });

    mockGetExamResultsDetails.mockImplementation((examId) => {
      if (examId === 'exam-a') {
        return examAResults.promise;
      }
      if (examId === 'exam-b') {
        return examBResults.promise;
      }
      throw new Error(`Unexpected exam id: ${examId}`);
    });

    render(
      <MemoryRouter initialEntries={['/hr/exams/exam-a']}>
        <Routes>
          <Route path="/hr/exams/:examId" element={<RouteHarness />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(mockGetExamById).toHaveBeenCalledWith(
        'exam-a',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
    });
    await waitFor(() => {
      expect(mockGetExamResultsDetails).toHaveBeenCalledWith(
        'exam-a',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
    });

    await userEvent.click(screen.getByRole('button', { name: 'Go to exam B' }));

    await waitFor(() => {
      expect(mockGetExamById).toHaveBeenCalledWith(
        'exam-b',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
    });
    await waitFor(() => {
      expect(mockGetExamResultsDetails).toHaveBeenCalledWith(
        'exam-b',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
    });

    await act(async () => {
      examBDetails.resolve({ data: { exam: buildExam('exam-b', 'Copied Exam B') } });
      examBResults.resolve({
        data: buildResultsPayload({
          employeesAssigned: 3,
          employeesAttempted: 0,
          attemptRate: 0,
          passRate: 0,
          totalPassed: 0,
          averageScore: 0,
          totalAttempts: 0,
          averageDurationSeconds: null,
          lastSubmissionAt: null,
          topPerformer: null,
        }),
      });
      await Promise.resolve();
    });

    expect(await screen.findByText('Copied Exam B')).toBeInTheDocument();
    expect(screen.getByText('No submissions yet')).toBeInTheDocument();
    expect(screen.queryByText('Mai Abdel Moneam Mohamed El Gamal')).not.toBeInTheDocument();
    expect(screen.queryByText('Original Exam A')).not.toBeInTheDocument();

    await act(async () => {
      examADetails.resolve({ data: { exam: buildExam('exam-a', 'Original Exam A') } });
      examAResults.resolve({
        data: buildResultsPayload({
          employeesAssigned: 2115,
          employeesAttempted: 986,
          attemptRate: 46.6,
          passRate: 74.3,
          totalPassed: 732,
          averageScore: 83.4,
          totalAttempts: 985,
          averageDurationSeconds: 740,
          lastSubmissionAt: '2026-08-23T14:16:00+03:00',
          topPerformer: {
            employee_name: 'Mai Abdel Moneam Mohamed El Gamal',
            employee_hr_id: '23614',
            submitted_at: '2026-08-21T19:36:00+03:00',
            score_percentage: 100,
            total_score: 35,
          },
        }),
      });
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByText('Copied Exam B')).toBeInTheDocument();
      expect(screen.getByText('No submissions yet')).toBeInTheDocument();
    });

    expect(screen.queryByText('Mai Abdel Moneam Mohamed El Gamal')).not.toBeInTheDocument();
    expect(screen.queryByText('Original Exam A')).not.toBeInTheDocument();
  });
});
