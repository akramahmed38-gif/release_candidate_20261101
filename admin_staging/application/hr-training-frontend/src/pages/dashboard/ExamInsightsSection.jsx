import React, { useMemo, useState } from 'react';
import { Box, Card, CardContent, Tab, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tabs, Typography } from '@mui/material';
import { examInsightTabs, safeCount, safeDateTimeLabel, safePercent } from './managementDashboardUtils';

const columnsByTab = (tr) => ({
  highest_participation: [
    ['exam_name', tr('Exam', 'الاختبار')],
    ['assigned_employees', tr('Assigned', 'المعيّنون')],
    ['participating_employees', tr('Participating', 'المشاركون')],
    ['participation_rate_pct', tr('Participation %', 'نسبة المشاركة')],
    ['average_score_pct', tr('Average Score', 'متوسط الدرجات')],
  ],
  lowest_participation: [
    ['exam_name', tr('Exam', 'الاختبار')],
    ['assigned_employees', tr('Assigned', 'المعيّنون')],
    ['participating_employees', tr('Participating', 'المشاركون')],
    ['participation_rate_pct', tr('Participation %', 'نسبة المشاركة')],
    ['average_score_pct', tr('Average Score', 'متوسط الدرجات')],
  ],
  highest_failure_rate: [
    ['exam_name', tr('Exam', 'الاختبار')],
    ['attempt_count', tr('Attempts', 'المحاولات')],
    ['failure_rate_pct', tr('Failure %', 'نسبة الرسوب')],
    ['average_score_pct', tr('Average Score', 'متوسط الدرجات')],
  ],
  lowest_average_score: [
    ['exam_name', tr('Exam', 'الاختبار')],
    ['attempt_count', tr('Attempts', 'المحاولات')],
    ['average_score_pct', tr('Average Score', 'متوسط الدرجات')],
    ['failure_rate_pct', tr('Failure %', 'نسبة الرسوب')],
  ],
  active_open: [
    ['exam_name', tr('Exam', 'الاختبار')],
    ['start_date', tr('Start', 'البداية')],
    ['end_date', tr('End', 'النهاية')],
    ['assigned_employees', tr('Assigned', 'المعيّنون')],
    ['participating_employees', tr('Participating', 'المشاركون')],
    ['participation_rate_pct', tr('Participation %', 'نسبة المشاركة')],
  ],
  overdue_open: [
    ['exam_name', tr('Exam', 'الاختبار')],
    ['end_date', tr('End', 'النهاية')],
    ['days_overdue', tr('Days Overdue', 'أيام التأخير')],
    ['assigned_employees', tr('Assigned', 'المعيّنون')],
    ['employees_with_no_attempt', tr('No Attempts', 'بدون محاولات')],
  ],
});

const renderCellValue = (column, value) => {
  if (column.endsWith('_pct')) {
    return safePercent(value);
  }
  if (column.endsWith('_date')) {
    return safeDateTimeLabel(value);
  }
  if (['assigned_employees', 'participating_employees', 'attempt_count', 'days_overdue', 'employees_with_no_attempt'].includes(column)) {
    return safeCount(value);
  }
  return value || '-';
};

const ExamInsightsSection = ({ examInsights, tr }) => {
  const tabs = useMemo(() => examInsightTabs(tr), [tr]);
  const [activeTab, setActiveTab] = useState('highest_participation');
  const rows = examInsights?.[activeTab] || [];
  const columns = useMemo(() => columnsByTab(tr)[activeTab] || [], [activeTab, tr]);

  return (
    <Card sx={{ borderRadius: 4 }}>
      <CardContent>
        <Typography sx={{ fontSize: '1.35rem', fontWeight: 800, color: '#102a56', mb: 0.5 }}>
          {tr('Exam Insights', 'رؤى الاختبارات')}
        </Typography>
        <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>
          {tr(
            'Exam participation, failure, scoring, and open-window risks come from submitted attempts and current exam windows.',
            'تعتمد المشاركة والرسوب ومتوسط الدرجات ومخاطر النوافذ المفتوحة على المحاولات المسلّمة وحالة الاختبارات الحالية.'
          )}
        </Typography>

        <Tabs
          value={activeTab}
          onChange={(_event, value) => setActiveTab(value)}
          variant="scrollable"
          allowScrollButtonsMobile
          sx={{ mb: 1.5 }}
        >
          {tabs.map((tab) => (
            <Tab key={tab.value} value={tab.value} label={tab.label} />
          ))}
        </Tabs>

        <TableContainer sx={{ maxHeight: 360, overflow: 'auto', borderRadius: 3, border: '1px solid rgba(16,42,86,0.08)' }}>
          <Table stickyHeader size="small" sx={{ minWidth: 860 }}>
            <TableHead>
              <TableRow>
                {columns.map(([column, label]) => (
                  <TableCell key={`${activeTab}-${column}`}>{label}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.length ? (
                rows.map((row, index) => (
                  <TableRow key={`${activeTab}-${row.exam_id || index}`} hover>
                    {columns.map(([column]) => (
                      <TableCell key={`${activeTab}-${row.exam_id || index}-${column}`}>
                        {renderCellValue(column, row[column])}
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={columns.length}>
                    {tr('No exam insight rows available for the selected filters.', 'لا توجد صفوف رؤى للاختبارات ضمن الفلاتر المحددة.')}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
};

export default ExamInsightsSection;
