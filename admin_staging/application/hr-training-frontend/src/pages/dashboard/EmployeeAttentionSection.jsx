import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  Typography,
} from '@mui/material';
import { attentionKinds, defaultAttentionKind, safeCount, safeDateTimeLabel, safePercent } from './managementDashboardUtils';

const kindColumns = (tr) => ({
  no_attempts: [
    ['hr_id', tr('HR ID', 'الرقم الوظيفي')],
    ['name', tr('Employee', 'الموظف')],
    ['job_title', tr('Job Title', 'المسمى الوظيفي')],
    ['branch_name', tr('Branch', 'الفرع')],
    ['assigned_exam_count', tr('Assigned Exams', 'الاختبارات المعيّنة')],
    ['last_login_at', tr('Last Login', 'آخر دخول')],
    ['last_activity_at', tr('Last Activity', 'آخر نشاط')],
  ],
  low_scores: [
    ['hr_id', tr('HR ID', 'الرقم الوظيفي')],
    ['name', tr('Employee', 'الموظف')],
    ['branch_name', tr('Branch', 'الفرع')],
    ['exams_attempted', tr('Exams Attempted', 'الاختبارات التي خاضها')],
    ['average_score_pct', tr('Average Score', 'متوسط الدرجات')],
    ['passed_exams', tr('Passed', 'ناجح')],
    ['failed_exams', tr('Failed', 'راسب')],
    ['latest_attempt_at', tr('Latest Attempt', 'آخر محاولة')],
  ],
  repeated_failures: [
    ['hr_id', tr('HR ID', 'الرقم الوظيفي')],
    ['name', tr('Employee', 'الموظف')],
    ['branch_name', tr('Branch', 'الفرع')],
    ['exam_title', tr('Exam', 'الاختبار')],
    ['failure_count', tr('Failure Count', 'عدد مرات الرسوب')],
    ['latest_score_pct', tr('Latest Score', 'آخر درجة')],
    ['latest_attempt_at', tr('Latest Attempt', 'آخر محاولة')],
    ['average_exam_score_pct', tr('Exam Avg', 'متوسط الاختبار')],
  ],
  never_logged_in: [
    ['hr_id', tr('HR ID', 'الرقم الوظيفي')],
    ['name', tr('Employee', 'الموظف')],
    ['branch_name', tr('Branch', 'الفرع')],
    ['job_title', tr('Job Title', 'المسمى الوظيفي')],
    ['created_at', tr('Account Created', 'تاريخ إنشاء الحساب')],
    ['employment_status', tr('Status', 'الحالة')],
  ],
  never_active: [
    ['hr_id', tr('HR ID', 'الرقم الوظيفي')],
    ['name', tr('Employee', 'الموظف')],
    ['branch_name', tr('Branch', 'الفرع')],
    ['job_title', tr('Job Title', 'المسمى الوظيفي')],
    ['last_login_at', tr('Last Login', 'آخر دخول')],
    ['last_activity_at', tr('Last Activity', 'آخر نشاط')],
  ],
});

const renderValue = (column, value) => {
  if (['average_score_pct', 'latest_score_pct', 'average_exam_score_pct'].includes(column)) {
    return safePercent(value);
  }
  if (column.endsWith('_at') || column === 'created_at') {
    return safeDateTimeLabel(value);
  }
  if (['assigned_exam_count', 'exams_attempted', 'passed_exams', 'failed_exams', 'failure_count'].includes(column)) {
    return safeCount(value);
  }
  return value || '-';
};

const EmployeeAttentionSection = ({ enabled, filters, counts, onLoad, snapshotId, updating, blocked, tr }) => {
  const [activeKind, setActiveKind] = useState(defaultAttentionKind);
  const [interactionId, setInteractionId] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [rows, setRows] = useState([]);
  const tabs = useMemo(() => attentionKinds(tr), [tr]);
  const columns = useMemo(() => kindColumns(tr)[activeKind] || [], [activeKind, tr]);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    const controller = new AbortController();
    let cancelled = false;
    setRows([]);
    if (updating) {
      setLoading(true);
      setError('');
      return () => { cancelled = true; controller.abort(); };
    }
    if (blocked) {
      setLoading(false);
      setError(tr('Attention data is unavailable until the dashboard reloads.', 'بيانات المتابعة غير متاحة حتى إعادة تحميل لوحة المعلومات.'));
      return () => { cancelled = true; controller.abort(); };
    }
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const response = await onLoad(activeKind, filters, { snapshotId, interactionId, signal: controller.signal });
        if (cancelled) {
          return;
        }
        setRows(response?.data?.rows || []);
      } catch (requestError) {
        if (cancelled) {
          return;
        }
        setRows([]);
        setError(
            tr('Unable to load employee attention list.', 'تعذر تحميل قائمة المتابعة الخاصة بالموظفين.')
        );
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    load();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [activeKind, blocked, enabled, filters.area, filters.branch_code, filters.month,
      filters.period, filters.region, filters.role, interactionId, onLoad, snapshotId, tr, updating]);

  if (!enabled) {
    return (
      <Card sx={{ borderRadius: 4 }}>
        <CardContent>
          <Typography sx={{ fontSize: '1.35rem', fontWeight: 800, color: '#102a56', mb: 1 }}>
            {tr('Employee Attention', 'متابعة الموظفين')}
          </Typography>
          <Typography color="text.secondary">
            {tr(
              'Managers receive only the aggregated attention counts in this phase. Employee-level drill-down remains limited to Admin and HR.',
              'في هذه المرحلة يظهر للمديرين ملخص الأعداد فقط، بينما يظل التفصيل على مستوى الموظف متاحاً للإدارة وموارد بشرية فقط.'
            )}
          </Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card sx={{ borderRadius: 4 }}>
      <CardContent>
        <Typography sx={{ fontSize: '1.35rem', fontWeight: 800, color: '#102a56', mb: 0.5 }}>
          {tr('Employee Attention', 'متابعة الموظفين')}
        </Typography>
        <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>
          {tr(
            'Lists load only when the tab is opened, keeping the main summary request fast.',
            'يتم تحميل القوائم فقط عند فتح التبويب للحفاظ على سرعة الملخص الرئيسي.'
          )}
        </Typography>

        <Tabs
          value={activeKind}
          onChange={(_event, value) => { setActiveKind(value); setInteractionId((id) => id + 1); }}
          variant="scrollable"
          allowScrollButtonsMobile
          sx={{ mb: 1.5 }}
        >
          {tabs.map((tab) => {
            const countKey =
              tab.value === 'no_attempts'
                ? 'no_attempts_count'
                : tab.value === 'low_scores'
                  ? 'low_score_count'
                  : tab.value === 'repeated_failures'
                    ? 'repeated_failure_count'
                    : tab.value === 'never_logged_in'
                      ? 'never_logged_in_count'
                      : 'never_active_count';
            return <Tab key={tab.value} value={tab.value} label={`${tab.label} (${safeCount(counts[countKey])})`} />;
          })}
        </Tabs>

        {error ? (
          <Alert severity="error" sx={{ mb: 1.5 }} action={!blocked ? (
            <Button color="inherit" size="small" onClick={() => setInteractionId((id) => id + 1)}>
              {tr('Retry loading data', 'إعادة تحميل البيانات')}
            </Button>
          ) : null}>{error}</Alert>
        ) : null}
        {loading ? (
          <Box sx={{ minHeight: 260, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <CircularProgress size={28} />
          </Box>
        ) : (
          <TableContainer sx={{ maxHeight: 360, overflow: 'auto', borderRadius: 3, border: '1px solid rgba(16,42,86,0.08)' }}>
            <Table stickyHeader size="small" sx={{ minWidth: 920 }}>
              <TableHead>
                <TableRow>
                  {columns.map(([column, label]) => (
                    <TableCell key={`${activeKind}-${column}`}>{label}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.length ? (
                  rows.map((row, index) => (
                    <TableRow key={`${activeKind}-${row.employee_id || row.hr_id || index}`} hover>
                      {columns.map(([column]) => (
                        <TableCell key={`${activeKind}-${row.employee_id || row.hr_id || index}-${column}`}>
                          {renderValue(column, row[column])}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={columns.length}>
                      {tr('No rows available for the selected attention list.', 'لا توجد بيانات لهذه القائمة حالياً.')}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </CardContent>
    </Card>
  );
};

export default EmployeeAttentionSection;
