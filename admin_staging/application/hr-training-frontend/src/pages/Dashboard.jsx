import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from 'chart.js';
import { Bar, Doughnut } from 'react-chartjs-2';
import { Download, Insights } from '@mui/icons-material';
import { analyticsService, authService, userService } from '../services/auth';
import { useLanguage } from '../context/LanguageContext';
import ManagementDashboardHeader from './dashboard/ManagementDashboardHeader';
import ManagementFilterBar from './dashboard/ManagementFilterBar';
import ManagerFilterBar from './dashboard/ManagerFilterBar';
import DashboardLoadingState from './dashboard/DashboardLoadingState';
import DashboardErrorState from './dashboard/DashboardErrorState';
import ExecutiveKpiGrid from './dashboard/ExecutiveKpiGrid';
import AttentionKpiGrid from './dashboard/AttentionKpiGrid';
import ManagementAlertsPanel from './dashboard/ManagementAlertsPanel';
import PerformanceTrendsSection from './dashboard/PerformanceTrendsSection';
import BranchPerformanceSection from './dashboard/BranchPerformanceSection';
import EmployeeAttentionSection from './dashboard/EmployeeAttentionSection';
import { createDashboardSnapshotCoordinator } from './dashboard/dashboardSnapshotCoordinator';
import ExamInsightsSection from './dashboard/ExamInsightsSection';
import ManagerOverviewSection from './dashboard/ManagerOverviewSection';
import {
  defaultManagementSummary,
  managementPeriodOptions,
  safePercent,
} from './dashboard/managementDashboardUtils';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
  PointElement,
  LineElement,
  Filler
);

const defaultLegacyPayload = {
  users: { total: 0, employee_total: 0, internal_total: 0, resigned_total: 0, roles_count: {} },
  branches: {
    total: 0,
    with_users: 0,
    without_users: 0,
    coverage_pct: 0,
    top_by_users: [],
  },
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
  leaderboards: {
    employees_high: [],
    employees_low: [],
    branches_high: [],
    branches_low: [],
  },
  top_scoring_employees: [],
  low_scoring_employees: [],
  top_scoring_branches: [],
  low_scoring_branches: [],
  available_employee_exam_counts: [],
  scoring_period: {
    period: 'month',
    start_at: null,
    end_at: null,
  },
};

const defaultFilters = {
  period: 'all',
  month: '',
  region: '',
  area: '',
  branch_code: '',
  role: '',
};

const legacyPeriodDefault = 'month';

const barOptions = (theme, isArabic = false, maxValue = 100) => ({
  responsive: true,
  maintainAspectRatio: false,
  indexAxis: 'y',
  plugins: {
    legend: { display: false },
    tooltip: { rtl: isArabic },
  },
  scales: {
    x: {
      min: 0,
      max: Math.max(100, Math.ceil(maxValue / 10) * 10),
      ticks: {
        callback: (value) => `${value}%`,
        color: theme.palette.text.secondary,
      },
      grid: { color: alpha(theme.palette.secondary.main, 0.08) },
    },
    y: {
      ticks: { color: theme.palette.text.primary },
      grid: { display: false },
    },
  },
});

const donutOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'bottom' },
  },
};

const Dashboard = () => {
  const theme = useTheme();
  const { t, isArabic } = useLanguage();
  const tr = useCallback((en, ar) => t(en, ar), [t]);
  const currentUser = authService.getCurrentUser();
  const currentRole = String(currentUser?.role || currentUser?.department || '').toLowerCase();
  const isManagerDashboard = currentRole === 'manager';
  const isAdminOverviewDashboard = ['admin', 'auditor'].includes(currentRole);
  const isOverviewDashboard = isManagerDashboard || isAdminOverviewDashboard;
  const canViewAttentionLists = ['admin', 'auditor'].includes(currentRole) || currentRole === 'hr';

  const [filters, setFilters] = useState(defaultFilters);
  const [managementData, setManagementData] = useState(defaultManagementSummary);
  const [managementLoading, setManagementLoading] = useState(true);
  const [managementError, setManagementError] = useState('');
  const [hasLoadedManagementData, setHasLoadedManagementData] = useState(false);

  const [legacyData, setLegacyData] = useState(defaultLegacyPayload);
  const [legacyLoading, setLegacyLoading] = useState(true);
  const [legacyError, setLegacyError] = useState('');
  const [legacyPeriod, setLegacyPeriod] = useState(legacyPeriodDefault);
  const [legacyExamsJoined, setLegacyExamsJoined] = useState('');
  const [exporting, setExporting] = useState({
    noAttempts: false,
    noLogin: false,
    noActivity: false,
  });

  const [audienceRegions, setAudienceRegions] = useState([]);
  const [audienceFilters, setAudienceFilters] = useState({});
  const dashboardCoordinatorRef = useRef(null);
  if (!dashboardCoordinatorRef.current) {
    dashboardCoordinatorRef.current = createDashboardSnapshotCoordinator({
      api: analyticsService,
      onCommit: (data) => {
        setManagementData({ ...defaultManagementSummary, ...data });
        setHasLoadedManagementData(true);
      },
      onBusy: setManagementLoading,
      onError: setManagementError,
    });
  }

  const audienceAreas = useMemo(() => {
    const regionPool = filters.region
      ? audienceRegions.filter((region) => region.region === filters.region)
      : audienceRegions;
    const areaMap = new Map();
    regionPool.forEach((region) => {
      (region.areas || []).forEach((area) => {
        if (!areaMap.has(area.area)) {
          areaMap.set(area.area, area);
        }
      });
    });
    return Array.from(areaMap.values());
  }, [audienceRegions, filters.region]);

  const audienceBranches = useMemo(() => {
    const regionPool = filters.region
      ? audienceRegions.filter((region) => region.region === filters.region)
      : audienceRegions;
    const branchMap = new Map();
    regionPool.forEach((region) => {
      (region.areas || []).forEach((area) => {
        if (filters.area && area.area !== filters.area) {
          return;
        }
        (area.branches || []).forEach((branch) => {
          if (!branchMap.has(branch.branch_code)) {
            branchMap.set(branch.branch_code, branch);
          }
        });
      });
    });
    return Array.from(branchMap.values());
  }, [audienceRegions, filters.area, filters.region]);

  const overviewRegionOptions = useMemo(
    () => managementData.filter_options?.regions || [],
    [managementData.filter_options]
  );

  const overviewAreaOptions = useMemo(
    () => managementData.filter_options?.areas || [],
    [managementData.filter_options]
  );

  const overviewBranchOptions = useMemo(
    () => managementData.filter_options?.branches || [],
    [managementData.filter_options]
  );

  const managementMonthOptions = useMemo(
    () => managementData.filter_options?.months || [],
    [managementData.filter_options]
  );

  const loadAudienceSettings = useCallback(async () => {
    try {
      const response = await userService.getAudienceHierarchy();
      const payload = response?.data?.data || {};
      setAudienceRegions(payload.regions || []);
      setAudienceFilters(payload.filters || {});
    } catch (error) {
      console.error('Failed to load audience hierarchy', error);
    }
  }, []);

  useEffect(() => {
    if (isOverviewDashboard) {
      return undefined;
    }
    loadAudienceSettings();
    return undefined;
  }, [isOverviewDashboard, loadAudienceSettings]);

  const loadManagementSummary = useCallback(
    (nextFilters = filters) => dashboardCoordinatorRef.current.load(nextFilters),
    [filters]
  );
  const loadLegacyWidgets = useCallback(async () => {
    if (isOverviewDashboard) {
      setLegacyLoading(false);
      setLegacyError('');
      setLegacyData(defaultLegacyPayload);
      return;
    }
    setLegacyLoading(true);
    setLegacyError('');
    try {
      const params = { period: legacyPeriod };
      if (legacyExamsJoined) {
        params.exams_joined = Number(legacyExamsJoined);
      }
      const response = await analyticsService.getDashboardKpis(params);
      setLegacyData(response?.data || defaultLegacyPayload);
    } catch (error) {
      setLegacyData(defaultLegacyPayload);
      setLegacyError(
        error?.response?.data?.message ||
          tr('Failed to load legacy dashboard widgets.', 'تعذر تحميل عناصر لوحة التشغيل الحالية.')
      );
      } finally {
        setLegacyLoading(false);
      }
    }, [isOverviewDashboard, legacyExamsJoined, legacyPeriod, tr]);

  useEffect(() => {
    loadManagementSummary(filters).catch(() => {});
    return () => dashboardCoordinatorRef.current.cancel();
  }, [filters, loadManagementSummary]);

  useEffect(() => {
    if (isOverviewDashboard) {
      setLegacyLoading(false);
      setLegacyError('');
      setLegacyData(defaultLegacyPayload);
      return undefined;
    }
    loadLegacyWidgets();
    return undefined;
  }, [isOverviewDashboard, loadLegacyWidgets]);

  const handleFilterChange = useCallback((field, value) => {
    dashboardCoordinatorRef.current.cancel();
    setFilters((current) => {
      if (field === 'periodSelection') {
        if (String(value || '').startsWith('month:')) {
          return {
            ...current,
            period: 'month',
            month: String(value).slice('month:'.length),
          };
        }
        return {
          ...current,
          period: String(value || 'preset:all').replace(/^preset:/, '') || 'all',
          month: '',
        };
      }
      if (field === 'region') {
        return { ...current, region: value, area: '', branch_code: '' };
      }
      if (field === 'area') {
        return { ...current, area: value, branch_code: '' };
      }
      return { ...current, [field]: value };
    });
  }, []);

  const handleResetFilters = useCallback(() => {
    dashboardCoordinatorRef.current.cancel();
    setFilters(defaultFilters);
  }, []);

  const fetchAttentionList = useCallback((kind, nextFilters, context) =>
    dashboardCoordinatorRef.current.loadAttention(
      kind, nextFilters, context.snapshotId, context.interactionId, context.signal
    ), []);

  const downloadBlobResponse = useCallback((response, fallbackName) => {
    const contentDisposition = response?.headers?.['content-disposition'] || '';
    const filenameMatch = contentDisposition.match(/filename="([^"]+)"/i);
    const filename = filenameMatch?.[1] || fallbackName;
    const blob = new Blob([response.data], {
      type:
        response?.headers?.['content-type'] ||
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  }, []);

  const runExport = useCallback(
    async (key, exporter, fallbackName) => {
      setExporting((current) => ({ ...current, [key]: true }));
      try {
        const response = await exporter();
        downloadBlobResponse(response, fallbackName);
      } catch (error) {
        setLegacyError(
          error?.response?.data?.message ||
            tr('Failed to export the requested list.', 'تعذر تصدير القائمة المطلوبة.')
        );
      } finally {
        setExporting((current) => ({ ...current, [key]: false }));
      }
    },
    [downloadBlobResponse, tr]
  );

  const legacyExamStatusData = useMemo(() => {
    const status = legacyData.exams?.status_distribution || {};
    return {
      labels: [tr('Open', 'مفتوح'), tr('On Hold', 'معلق'), tr('Closed', 'مغلق')],
      datasets: [
        {
          data: [status.Open || 0, status['On Hold'] || 0, status.Closed || 0],
          backgroundColor: [theme.palette.primary.dark, '#B45309', theme.palette.secondary.main],
          borderColor: '#ffffff',
          borderWidth: 2,
        },
      ],
    };
  }, [legacyData.exams?.status_distribution, theme.palette.primary.dark, theme.palette.secondary.main, tr]);

  const legacyEmployeeHighRows = useMemo(
    () => (legacyData.top_scoring_employees || legacyData.leaderboards?.employees_high || []).slice(0, 10),
    [legacyData]
  );
  const legacyEmployeeLowRows = useMemo(
    () => (legacyData.low_scoring_employees || legacyData.leaderboards?.employees_low || []).slice(0, 10),
    [legacyData]
  );
  const legacyBranchHighRows = useMemo(
    () => (legacyData.top_scoring_branches || legacyData.leaderboards?.branches_high || []).slice(0, 10),
    [legacyData]
  );
  const legacyBranchLowRows = useMemo(
    () => (legacyData.low_scoring_branches || legacyData.leaderboards?.branches_low || []).slice(0, 10),
    [legacyData]
  );

  const legacyBranchHighChart = useMemo(() => {
    const maxValue = Math.max(100, ...legacyBranchHighRows.map((row) => Number(row.average_percentage ?? row.average_score_pct ?? 0)));
    return {
      chart: {
        labels: legacyBranchHighRows.map((row) => `${row.branch_name || '-'} (${row.branch_code || '-'})`),
        datasets: [
          {
            data: legacyBranchHighRows.map((row) => Number(row.average_percentage ?? row.average_score_pct ?? 0)),
            backgroundColor: theme.palette.primary.dark,
            borderRadius: 6,
          },
        ],
      },
      maxValue,
    };
  }, [legacyBranchHighRows, theme.palette.primary.dark]);

  const legacyBranchLowChart = useMemo(() => {
    const maxValue = Math.max(100, ...legacyBranchLowRows.map((row) => Number(row.average_percentage ?? row.average_score_pct ?? 0)));
    return {
      chart: {
        labels: legacyBranchLowRows.map((row) => `${row.branch_name || '-'} (${row.branch_code || '-'})`),
        datasets: [
          {
            data: legacyBranchLowRows.map((row) => Number(row.average_percentage ?? row.average_score_pct ?? 0)),
            backgroundColor: '#B45309',
            borderRadius: 6,
          },
        ],
      },
      maxValue,
    };
  }, [legacyBranchLowRows]);

  const legacyExamCountOptions = useMemo(() => {
    const counts = legacyData.available_employee_exam_counts || [];
    return Array.from(
      new Set(
        [1, 2, 3, ...counts]
          .filter((value) => Number.isFinite(Number(value)) && Number(value) > 0)
          .map((value) => String(Number.parseInt(value, 10)))
      )
    ).sort((left, right) => Number(left) - Number(right));
  }, [legacyData.available_employee_exam_counts]);

  const renderLegacyEmployeeTable = (rows, emptyText) => (
    <TableContainer sx={{ maxHeight: 360, overflow: 'auto', borderRadius: 3, border: '1px solid rgba(16,42,86,0.08)' }}>
      <Table stickyHeader size="small" sx={{ minWidth: 760 }}>
        <TableHead>
          <TableRow>
            <TableCell>{tr('HR ID', 'الرقم الوظيفي')}</TableCell>
            <TableCell>{tr('Employee name', 'اسم الموظف')}</TableCell>
            <TableCell>{tr('Branch Code', 'كود الفرع')}</TableCell>
            <TableCell align="right">{tr('Avg %', 'المتوسط %')}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.length ? (
            rows.map((row, index) => (
              <TableRow key={`${row.employee_id || row.hr_id || index}`} hover>
                <TableCell>{row.hr_id || '-'}</TableCell>
                <TableCell>{row.employee_name || row.name || row.email || '-'}</TableCell>
                <TableCell>{row.branch_code || row.branch_name || '-'}</TableCell>
                <TableCell align="right">{safePercent(row.average_percentage ?? row.average_score_pct)}</TableCell>
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={4}>{emptyText}</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );

  const renderLegacyBranchChart = (rows, chartData) =>
    rows.length ? (
      <Box sx={{ height: 320 }}>
        <Bar data={chartData.chart} options={barOptions(theme, isArabic, chartData.maxValue)} />
      </Box>
    ) : (
      <Box
        sx={{
          minHeight: 320,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          px: 2,
        }}
      >
        <Typography color="text.secondary">
          {tr('No exam data available for the selected filters.', 'لا توجد بيانات اختبارات متاحة للفلاتر المحددة.')}
        </Typography>
      </Box>
    );

  const showManagementSkeleton = managementLoading && !hasLoadedManagementData;
  const overviewHeaderProps = useMemo(() => {
    if (!isOverviewDashboard || isManagerDashboard) {
      return {};
    }
    return {
      title: tr('Dashboard', 'لوحة المعلومات'),
      description: tr(
        'Live dashboard focused on active exams, active users, exam success, and branch performance.',
        'عرض مباشر يركز على الاختبارات النشطة، والمستخدمين النشطين، ونجاح الاختبارات، وأداء الفروع.'
      ),
    };
  }, [isManagerDashboard, isOverviewDashboard, tr]);

  return (
    <Box sx={{ direction: isArabic ? 'rtl' : 'ltr', p: { xs: 1.25, md: 2.5 }, maxWidth: 1600, mx: 'auto' }}>
      <Stack spacing={2.5}>
        <ManagementDashboardHeader
          generatedAt={managementData.generated_at}
          loading={managementLoading}
          onRefresh={() => loadManagementSummary(filters).catch(() => {})}
          tr={tr}
          title={isManagerDashboard ? tr('Manager Dashboard', 'لوحة المدير') : undefined}
          description={
            isManagerDashboard
              ? tr(
                  'Manager-facing view focused on active exams, active users, exam success, and branch performance.',
                  'عرض المدير يركز على الاختبارات النشطة، والمستخدمين النشطين، ونجاح الاختبارات، وأداء الفروع.'
                )
              : undefined
          }
          {...overviewHeaderProps}
        />

        {managementLoading && hasLoadedManagementData ? (
          <Alert severity="info" role="status">
            {tr('Updating dashboard data...', 'جارٍ تحديث بيانات لوحة المعلومات...')}
          </Alert>
        ) : null}

        {managementData.snapshot?.source_as_of ? (
          <Alert severity={managementData.snapshot.is_stale ? 'warning' : 'info'}>
            {tr('Data updated', 'تم تحديث البيانات')}: {new Intl.DateTimeFormat(
              isArabic ? 'ar-EG' : 'en-EG',
              { timeZone: 'Africa/Cairo', dateStyle: 'medium', timeStyle: 'short' }
            ).format(new Date(managementData.snapshot.source_as_of))}
            {managementData.snapshot.is_stale
              ? ` · ${tr('Data may be stale. Try Refresh or contact support.', 'قد تكون البيانات قديمة. حاول التحديث أو تواصل مع الدعم.')}`
              : ''}
          </Alert>
        ) : null}

        {isOverviewDashboard ? (
          <ManagerFilterBar
            filters={filters}
            regionOptions={overviewRegionOptions}
            areaOptions={overviewAreaOptions}
            branchOptions={overviewBranchOptions}
            monthOptions={managementMonthOptions}
            onChange={handleFilterChange}
            disabled={managementLoading}
            tr={tr}
            isArabic={isArabic}
            audience={isManagerDashboard ? 'manager' : 'admin'}
          />
        ) : (
          <ManagementFilterBar
            filters={filters}
            audienceRegions={audienceRegions}
            audienceAreas={audienceAreas}
            audienceBranches={audienceBranches}
            audienceDepartments={audienceFilters.departments || []}
            monthOptions={managementMonthOptions}
            onChange={handleFilterChange}
            onReset={handleResetFilters}
            disabled={managementLoading}
            tr={tr}
            isArabic={isArabic}
          />
        )}

        {managementError ? (
          <DashboardErrorState
            error={managementError?.response?.status === 401 || managementError?.response?.status === 403
              ? tr('You are not authorized to view this data.', 'ليس لديك صلاحية لعرض هذه البيانات.')
              : tr('Could not load prepared dashboard data. Please retry.', 'تعذر تحميل بيانات لوحة المعلومات المُعدّة. يُرجى إعادة المحاولة.')}
            onRetry={() => loadManagementSummary(filters).catch(() => {})}
            tr={tr}
          />
        ) : null}

        {showManagementSkeleton ? (
          <DashboardLoadingState />
        ) : (
          isOverviewDashboard ? (
              <ManagerOverviewSection
                overview={managementData.overview}
                branches={managementData.branches}
                mistakeTopics={managementData.mistake_topics}
                examStatusMix={managementData.exam_status_mix}
                activeBranchCode={filters.branch_code}
                theme={theme}
                isArabic={isArabic}
                tr={tr}
                audience={isManagerDashboard ? 'manager' : 'admin'}
              />
          ) : (
            <>
              <ExecutiveKpiGrid overview={managementData.overview} theme={theme} tr={tr} />

              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', xl: '2fr 1fr' }, gap: 2 }}>
                <PerformanceTrendsSection trends={managementData.trends} theme={theme} isArabic={isArabic} tr={tr} />
                <ManagementAlertsPanel alerts={managementData.alerts || []} tr={tr} />
              </Box>

              <AttentionKpiGrid
                overview={managementData.overview}
                attention={managementData.attention}
                theme={theme}
                tr={tr}
              />

              <BranchPerformanceSection branches={managementData.branches} tr={tr} />

              <EmployeeAttentionSection
                enabled={Boolean(managementData.access?.can_view_employee_attention && canViewAttentionLists)}
                filters={filters}
                counts={managementData.attention}
                onLoad={fetchAttentionList}
                snapshotId={managementData.snapshot?.snapshot_id}
                updating={managementLoading}
                blocked={Boolean(managementError)}
                tr={tr}
              />

              <ExamInsightsSection examInsights={managementData.exam_insights} tr={tr} />
            </>
          )
        )}

        {!isOverviewDashboard ? <Divider sx={{ pt: 0.5 }} /> : null}

        {!isOverviewDashboard ? (
        <Card sx={{ borderRadius: 4 }}>
          <CardContent>
            <Stack
              direction={{ xs: 'column', lg: 'row' }}
              justifyContent="space-between"
              alignItems={{ xs: 'flex-start', lg: 'center' }}
              spacing={1.5}
              sx={{ mb: 2 }}
            >
              <Box>
                <Typography sx={{ fontSize: '1.35rem', fontWeight: 800, color: '#102a56' }}>
                  {tr('Existing Operational Widgets', 'العناصر التشغيلية الحالية')}
                </Typography>
                <Typography color="text.secondary" variant="body2">
                  {tr(
                    'Legacy score widgets remain below the new management section for continuity during this phase.',
                    'تظل عناصر الدرجات الحالية أسفل قسم الإدارة الجديد لضمان الاستمرارية خلال هذه المرحلة.'
                  )}
                </Typography>
              </Box>

              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ width: { xs: '100%', lg: 'auto' } }}>
                <FormControl sx={{ minWidth: 160 }}>
                  <InputLabel>{tr('Scoring Period', 'فترة الدرجات')}</InputLabel>
                  <Select
                    label={tr('Scoring Period', 'فترة الدرجات')}
                    value={legacyPeriod}
                    onChange={(event) => setLegacyPeriod(event.target.value)}
                    disabled={legacyLoading}
                  >
                    {managementPeriodOptions(tr).map((option) => (
                      <MenuItem key={option.value} value={option.value}>
                        {option.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <FormControl sx={{ minWidth: 180 }}>
                  <InputLabel>{tr('Exact Exams Joined', 'عدد الاختبارات')}</InputLabel>
                  <Select
                    label={tr('Exact Exams Joined', 'عدد الاختبارات')}
                    value={legacyExamsJoined}
                    onChange={(event) => setLegacyExamsJoined(event.target.value)}
                    disabled={legacyLoading}
                  >
                    <MenuItem value="">{tr('All Employees', 'كل الموظفين')}</MenuItem>
                    {legacyExamCountOptions.map((option) => (
                      <MenuItem key={option} value={option}>
                        {tr(`Exact ${option}`, `مطابق ${option}`)}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Stack>
            </Stack>

            {legacyError ? <Alert severity="error" sx={{ mb: 2 }}>{legacyError}</Alert> : null}

            <Stack direction={{ xs: 'column', lg: 'row' }} spacing={1} sx={{ mb: 2 }}>
              <Button
                variant="outlined"
                startIcon={exporting.noAttempts ? <CircularProgress size={16} /> : <Download />}
                onClick={() =>
                  runExport('noAttempts', analyticsService.exportNoAttemptUsers, 'no_exam_attempt_users.xlsx')
                }
                disabled={exporting.noAttempts}
              >
                {tr('No Exam Attempts', 'بدون محاولات')}
              </Button>
              <Button
                variant="outlined"
                startIcon={exporting.noLogin ? <CircularProgress size={16} /> : <Download />}
                onClick={() => runExport('noLogin', () => analyticsService.exportNoLoginUsers('login'), 'no_login_users.xlsx')}
                disabled={exporting.noLogin}
              >
                {tr('No Login Users', 'لم يسجلوا الدخول')}
              </Button>
              <Button
                variant="outlined"
                startIcon={exporting.noActivity ? <CircularProgress size={16} /> : <Download />}
                onClick={() =>
                  runExport('noActivity', () => analyticsService.exportNoLoginUsers('activity'), 'no_activity_users.xlsx')
                }
                disabled={exporting.noActivity}
              >
                {tr('No Activity Users', 'بدون نشاط')}
              </Button>
            </Stack>

            {legacyLoading ? (
              <Box sx={{ minHeight: 280, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <CircularProgress />
              </Box>
            ) : (
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', xl: 'repeat(4, minmax(0, 1fr))' },
                  gap: 2,
                }}
              >
                <Card sx={{ borderRadius: 4 }}>
                  <CardContent>
                    <Typography sx={{ fontSize: '1.25rem', fontWeight: 800, color: '#102a56', mb: 1.5 }}>
                      {tr('Exam Status Mix', 'توزيع حالة الاختبارات')}
                    </Typography>
                    <Box sx={{ height: 300 }}>
                      <Doughnut data={legacyExamStatusData} options={donutOptions} />
                    </Box>
                  </CardContent>
                </Card>

                <Card sx={{ borderRadius: 4 }}>
                  <CardContent>
                    <Typography sx={{ fontSize: '1.25rem', fontWeight: 800, color: '#102a56', mb: 1.5 }}>
                      {tr('Top Scoring Employees', 'أفضل الموظفين في الدرجات')}
                    </Typography>
                    {renderLegacyEmployeeTable(
                      legacyEmployeeHighRows,
                      tr('No scoring rows available.', 'لا توجد صفوف درجات متاحة.')
                    )}
                  </CardContent>
                </Card>

                <Card sx={{ borderRadius: 4 }}>
                  <CardContent>
                    <Typography sx={{ fontSize: '1.25rem', fontWeight: 800, color: '#102a56', mb: 1.5 }}>
                      {tr('Low Scoring Employees', 'أقل الموظفين في الدرجات')}
                    </Typography>
                    {renderLegacyEmployeeTable(
                      legacyEmployeeLowRows,
                      tr('No scoring rows available.', 'لا توجد صفوف درجات متاحة.')
                    )}
                  </CardContent>
                </Card>

                <Card sx={{ borderRadius: 4 }}>
                  <CardContent>
                    <Typography sx={{ fontSize: '1.25rem', fontWeight: 800, color: '#102a56', mb: 1.5 }}>
                      {tr('Top Scoring Branches', 'أفضل الفروع في الدرجات')}
                    </Typography>
                    {renderLegacyBranchChart(legacyBranchHighRows, legacyBranchHighChart)}
                  </CardContent>
                </Card>

                <Card sx={{ borderRadius: 4, gridColumn: { xs: '1', xl: 'span 2' } }}>
                  <CardContent>
                    <Typography sx={{ fontSize: '1.25rem', fontWeight: 800, color: '#102a56', mb: 1.5 }}>
                      {tr('Low Scoring Branches', 'أقل الفروع في الدرجات')}
                    </Typography>
                    {renderLegacyBranchChart(legacyBranchLowRows, legacyBranchLowChart)}
                  </CardContent>
                </Card>
              </Box>
            )}
          </CardContent>
        </Card>
        ) : null}
      </Stack>
    </Box>
  );
};

export default Dashboard;
