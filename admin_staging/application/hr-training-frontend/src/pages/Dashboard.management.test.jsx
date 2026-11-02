import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import Dashboard from './Dashboard';
import { defaultManagementSummary } from './dashboard/managementDashboardUtils';

const mockGetManagementSummary = vi.fn();
const mockGetManagementAttention = vi.fn();
const mockGetDashboardKpis = vi.fn();
const mockGetAudienceHierarchy = vi.fn();

let mockRole = 'admin';

vi.mock('../context/LanguageContext', () => ({
  useLanguage: () => ({
    isArabic: false,
    t: (english) => english,
  }),
}));

vi.mock('../services/auth', () => ({
  analyticsService: {
    getManagementSummary: (...args) => mockGetManagementSummary(...args),
    getManagementAttention: (...args) => mockGetManagementAttention(...args),
    getDashboardKpis: (...args) => mockGetDashboardKpis(...args),
    exportNoAttemptUsers: vi.fn(),
    exportNoLoginUsers: vi.fn(),
  },
  authService: {
    getCurrentUser: () => ({ role: mockRole }),
  },
  userService: {
    getAudienceHierarchy: (...args) => mockGetAudienceHierarchy(...args),
  },
}));

vi.mock('react-chartjs-2', () => ({
  Bar: () => <div data-testid="mock-bar-chart" />,
  Doughnut: () => <div data-testid="mock-doughnut-chart" />,
  Line: () => <div data-testid="mock-line-chart" />,
}));

const legacyPayload = {
  users: { total: 0, employee_total: 0, internal_total: 0, resigned_total: 0, roles_count: {} },
  branches: { total: 0, with_users: 0, without_users: 0, coverage_pct: 0, top_by_users: [] },
  exams: {
    total: 0,
    active_open_total: 0,
    currently_open_total: 0,
    status_distribution: { Open: 0, Closed: 0, 'On Hold': 0 },
    closing_in_7_days: 0,
    overdue_open_configured: 0,
    created_last_30_days: 0,
    total_assigned_users: 0,
  },
  attempts: {
    total_attempts: 0,
    passed_attempts: 0,
    pass_rate_pct: 0,
    average_score_pct: 0,
    assigned_pairs: 0,
    attempted_pairs: 0,
    assignment_coverage_pct: 0,
  },
  engagement: {
    eligible_users: 0,
    users_with_attempts: 0,
    users_without_attempts: 0,
    users_logged_in: 0,
    users_without_login: 0,
    users_active_in_system: 0,
    users_without_activity: 0,
    no_attempt_preview: [],
    no_login_preview: [],
  },
  leaderboards: { employees_high: [], employees_low: [], branches_high: [], branches_low: [] },
  top_scoring_employees: [],
  low_scoring_employees: [],
  top_scoring_branches: [],
  low_scoring_branches: [],
  available_employee_exam_counts: [],
  scoring_period: { period: 'month', start_at: null, end_at: null },
};

const buildSummaryPayload = (accessOverrides = {}) => ({
  ...defaultManagementSummary,
  signal: 'success',
  generated_at: '2026-07-22T12:00:00Z',
  access: {
    access_role: mockRole,
    can_view_employee_attention: mockRole !== 'manager',
    can_export_attention_lists: mockRole !== 'manager',
    ...accessOverrides,
  },
  filter_options: {
    regions: ['Alex', 'Cairo'],
    areas: ['North Delta', 'South Delta'],
    branches: [
      { branch_code: '1116', branch_name: 'Branch A', employee_count: 10 },
      { branch_code: '0056', branch_name: 'Branch B', employee_count: 8 },
      { branch_code: '1124', branch_name: 'Branch C', employee_count: 7 },
    ],
    months: ['2026-08', '2026-07', '2026-06'],
  },
  overview: {
    active_employees: 10,
    resigned_employees: 4,
    users_with_attempts: 5,
    training_participation_rate: 60,
    average_exam_score_pct: 80,
    pass_rate_pct: 70,
    no_exam_attempts: 2,
    never_logged_in: 1,
    never_active: 1,
    active_open_exams: 3,
    overdue_open_exams: 1,
  },
  exam_status_mix: {
    Open: 3,
    Closed: 5,
    'On Hold': 1,
  },
  branches: {
    ...defaultManagementSummary.branches,
    comparison: [
      { branch_code: '1116', branch_name: 'Branch A', pass_rate_pct: 91.4, average_score_pct: 78.6, participating_employees: 8 },
      { branch_code: '0056', branch_name: 'Branch B', pass_rate_pct: 88.0, average_score_pct: 74.5, participating_employees: 7 },
      { branch_code: '1124', branch_name: 'Branch C', pass_rate_pct: 83.0, average_score_pct: 73.8, participating_employees: 6 },
    ],
  },
  mistake_topics: [
    {
      topic_key: 'operations',
      topic: 'Operations',
      wrong_answers: 8,
      total_answers: 10,
      error_rate_pct: 80,
      accuracy_pct: 20,
      branches: [
        { branch_code: '1116', branch_name: 'Branch A', wrong_answers: 4, total_answers: 4, error_rate_pct: 100 },
        { branch_code: '0056', branch_name: 'Branch B', wrong_answers: 3, total_answers: 4, error_rate_pct: 75 },
      ],
    },
    {
      topic_key: 'compliance',
      topic: 'Compliance',
      wrong_answers: 5,
      total_answers: 10,
      error_rate_pct: 50,
      accuracy_pct: 50,
      branches: [
        { branch_code: '1124', branch_name: 'Branch C', wrong_answers: 2, total_answers: 3, error_rate_pct: 66.7 },
      ],
    },
  ],
  attention: {
    no_attempts_count: 2,
    low_score_count: 1,
    repeated_failure_count: 0,
    never_logged_in_count: 1,
    never_active_count: 1,
  },
});

describe('Dashboard management section', () => {
  beforeEach(() => {
    mockRole = 'admin';
    mockGetManagementSummary.mockResolvedValue({ data: buildSummaryPayload() });
    mockGetManagementAttention.mockResolvedValue({ data: { rows: [] } });
    mockGetDashboardKpis.mockResolvedValue({ data: legacyPayload });
    mockGetAudienceHierarchy.mockResolvedValue({
      data: {
        data: {
          regions: [],
          filters: { departments: ['Retail', 'Employee'] },
        },
      },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it.each(['admin', 'auditor'])('renders the %s overview dashboard with neutral copy and no chatbot content', async (role) => {
    mockRole = role;
    render(<Dashboard />);

    expect(await screen.findByText('Dashboard')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Active Users')).toBeInTheDocument();
    });
    expect(screen.getByText('Dashboard Insights')).toBeInTheDocument();
    expect(screen.queryByText('Manager Dashboard')).not.toBeInTheDocument();
    expect(screen.queryByText('Manager Insights')).not.toBeInTheDocument();
    expect(screen.queryByText('Existing Operational Widgets')).not.toBeInTheDocument();
    expect(screen.queryByText(/chatbot/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Chat with us now/i)).not.toBeInTheDocument();
    expect(mockGetDashboardKpis).not.toHaveBeenCalled();
  });

  it('renders the simplified manager dashboard without legacy widgets or attention lists', async () => {
    mockRole = 'manager';
    mockGetManagementSummary.mockResolvedValue({ data: buildSummaryPayload() });

    render(<Dashboard />);

    expect(await screen.findByText('Manager Dashboard')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Active Users')).toBeInTheDocument();
    });
    expect(screen.getByText('Top 10 Branches by Average Success')).toBeInTheDocument();
    expect(screen.getByText('10 Branches with Lowest Total Exam Scores')).toBeInTheDocument();
    expect(screen.getByText('Topics Employees Mistake In')).toBeInTheDocument();
    expect(screen.getByText('Branches Behind Topic Mistakes')).toBeInTheDocument();
    expect(screen.getAllByText('Branch').length).toBeGreaterThan(0);
    expect(screen.getByText('Branch A (1116)')).toBeInTheDocument();
    expect(screen.getByText('Exam Status Mix')).toBeInTheDocument();
    expect(screen.getByText('62.5%')).toBeInTheDocument();
    expect(screen.queryByText('Employee Attention')).not.toBeInTheDocument();
    expect(screen.queryByText('Existing Operational Widgets')).not.toBeInTheDocument();
    expect(screen.queryByText(/Temporary manager formula/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Calculated from active users/i)).not.toBeInTheDocument();
    expect(mockGetDashboardKpis).not.toHaveBeenCalled();
  });

  it('filters the topic mistake widget without reloading the dashboard', async () => {
    mockRole = 'manager';
    mockGetManagementSummary.mockResolvedValue({ data: buildSummaryPayload() });

    render(<Dashboard />);

    expect(await screen.findByText('Manager Dashboard')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Operations')).toBeInTheDocument();
      expect(screen.getByText('Compliance')).toBeInTheDocument();
    });

    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Topic' }));
    fireEvent.click(screen.getByRole('option', { name: 'Compliance' }));

    await waitFor(() => {
      expect(screen.queryByText('Operations')).not.toBeInTheDocument();
      expect(screen.queryAllByText('Compliance').length).toBeGreaterThan(0);
      expect(screen.queryByText('Branch A (1116)')).not.toBeInTheDocument();
      expect(screen.getByText('Branch C (1124)')).toBeInTheDocument();
    });

    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Topic' }));
    fireEvent.click(screen.getByRole('option', { name: 'All Topics' }));

    await waitFor(() => {
      expect(screen.getByText('Operations')).toBeInTheDocument();
      expect(screen.getByText('Compliance')).toBeInTheDocument();
      expect(screen.getByText('Branch A (1116)')).toBeInTheDocument();
    });
  });

  it('sends exact month and location filters from the overview filter bar', async () => {
    mockRole = 'manager';
    mockGetManagementSummary.mockResolvedValue({ data: buildSummaryPayload() });

    render(<Dashboard />);

    expect(await screen.findByText('Manager Dashboard')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Active Users')).toBeInTheDocument();
    });

    const getOverviewFilterComboboxes = () => screen.getAllByRole('combobox').slice(0, 4);
    const waitForOverviewReload = async () => {
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled();
      });
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Refresh' })).not.toBeDisabled();
      });
    };
    let [periodSelect, regionSelect, areaSelect, branchSelect] = getOverviewFilterComboboxes();

    fireEvent.mouseDown(periodSelect);
    fireEvent.click(screen.getByRole('option', { name: 'July 2026' }));

    await waitFor(() => {
      expect(mockGetManagementSummary).toHaveBeenLastCalledWith(
        expect.objectContaining({ period: 'month', month: '2026-07' }),
        expect.any(Object)
      );
    });
    await waitForOverviewReload();

    [, regionSelect] = getOverviewFilterComboboxes();
    fireEvent.mouseDown(regionSelect);
    fireEvent.click(screen.getByRole('option', { name: 'Cairo' }));
    await waitFor(() => {
      expect(mockGetManagementSummary).toHaveBeenLastCalledWith(
        expect.objectContaining({ region: 'Cairo' }),
        expect.any(Object)
      );
    });
    await waitForOverviewReload();

    [, , areaSelect] = getOverviewFilterComboboxes();
    fireEvent.mouseDown(areaSelect);
    fireEvent.click(screen.getByRole('option', { name: 'North Delta' }));
    await waitFor(() => {
      expect(mockGetManagementSummary).toHaveBeenLastCalledWith(
        expect.objectContaining({ region: 'Cairo', area: 'North Delta' }),
        expect.any(Object)
      );
    });
    await waitForOverviewReload();

    [, , , branchSelect] = getOverviewFilterComboboxes();
    fireEvent.mouseDown(branchSelect);
    fireEvent.click(screen.getByRole('option', { name: 'Branch A (1116)' }));

    await waitFor(() => {
      expect(mockGetManagementSummary).toHaveBeenLastCalledWith(
        expect.objectContaining({
          period: 'month',
          month: '2026-07',
          region: 'Cairo',
          area: 'North Delta',
          branch_code: '1116',
        }),
        expect.any(Object)
      );
    });
  });
});
