import React, { useMemo, useState } from 'react';
import { ArrowDownward, ArrowUpward } from '@mui/icons-material';
import {
  Box,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Typography,
} from '@mui/material';
import { safeCount, safePercent } from './managementDashboardUtils';

const BranchMiniList = ({ title, rows, valueKey, tr }) => (
  <Card sx={{ borderRadius: 4, height: '100%' }}>
    <CardContent>
      <Typography sx={{ fontSize: '1.08rem', fontWeight: 800, color: '#102a56', mb: 1.2 }}>{title}</Typography>
      {rows.length ? (
        <Box sx={{ display: 'grid', gap: 1 }}>
          {rows.map((row) => (
            <Box
              key={`${title}-${row.branch_code}`}
              sx={{
                borderRadius: 2.5,
                border: '1px solid rgba(16,42,86,0.08)',
                px: 1.25,
                py: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 1.5,
              }}
            >
              <Box sx={{ minWidth: 0 }}>
                <Typography sx={{ fontWeight: 700 }} noWrap>
                  {row.branch_name || '-'}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {row.branch_code || '-'}
                </Typography>
              </Box>
              <Typography sx={{ fontWeight: 800, color: '#102a56', whiteSpace: 'nowrap' }}>
                {valueKey === 'no_attempt_employees'
                  ? safeCount(row[valueKey])
                  : safePercent(row[valueKey])}
              </Typography>
            </Box>
          ))}
        </Box>
      ) : (
        <Typography color="text.secondary">{tr('No branches in scope.', 'لا توجد فروع ضمن النطاق.')}</Typography>
      )}
    </CardContent>
  </Card>
);

const BranchPerformanceSection = ({ branches, tr }) => {
  const [sortBy, setSortBy] = useState('average_score_pct');
  const [sortDir, setSortDir] = useState('desc');

  const comparisonRows = branches.comparison || [];
  const sortedRows = useMemo(() => {
    const direction = sortDir === 'asc' ? 1 : -1;
    return [...comparisonRows].sort((left, right) => {
      const leftValue = left?.[sortBy];
      const rightValue = right?.[sortBy];
      if (typeof leftValue === 'number' && typeof rightValue === 'number') {
        return (leftValue - rightValue) * direction;
      }
      return String(leftValue || '').localeCompare(String(rightValue || '')) * direction;
    });
  }, [comparisonRows, sortBy, sortDir]);

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortDir((current) => (current === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortBy(column);
    setSortDir(column === 'branch_name' ? 'asc' : 'desc');
  };

  return (
    <Card sx={{ borderRadius: 4 }}>
      <CardContent>
        <Typography sx={{ fontSize: '1.35rem', fontWeight: 800, color: '#102a56', mb: 0.5 }}>
          {tr('Branch Performance', 'أداء الفروع')}
        </Typography>
        <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>
          {tr(
            'Branch rankings and comparison stay aligned with the same global period and employee filters.',
            'يتم تحديث ترتيب الفروع وجدول المقارنة بنفس الفترة ونفس نطاق الموظفين المختار.'
          )}
        </Typography>

        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))', xl: 'repeat(4, minmax(0, 1fr))' },
            gap: 2,
            mb: 2,
          }}
        >
          <BranchMiniList title={tr('Top 5 by Score', 'أفضل 5 حسب الدرجات')} rows={branches.top || []} valueKey="average_score_pct" tr={tr} />
          <BranchMiniList title={tr('Bottom 5 by Score', 'أقل 5 حسب الدرجات')} rows={branches.low || []} valueKey="average_score_pct" tr={tr} />
          <BranchMiniList
            title={tr('Lowest Participation', 'أقل مشاركة')}
            rows={branches.lowest_participation || []}
            valueKey="participation_rate_pct"
            tr={tr}
          />
          <BranchMiniList
            title={tr('Highest No-Attempt Count', 'أعلى عدد بدون محاولات')}
            rows={branches.highest_no_attempts || []}
            valueKey="no_attempt_employees"
            tr={tr}
          />
        </Box>

        <TableContainer sx={{ maxHeight: 420, overflow: 'auto', borderRadius: 3, border: '1px solid rgba(16,42,86,0.08)' }}>
          <Table stickyHeader size="small" sx={{ minWidth: 980 }}>
            <TableHead>
              <TableRow>
                {[
                  ['branch_name', tr('Branch Name', 'اسم الفرع')],
                  ['total_employees', tr('Total Employees', 'إجمالي الموظفين')],
                  ['participating_employees', tr('Participating Employees', 'الموظفون المشاركون')],
                  ['participation_rate_pct', tr('Participation %', 'نسبة المشاركة')],
                  ['average_score_pct', tr('Average Score', 'متوسط الدرجات')],
                  ['pass_rate_pct', tr('Pass Rate', 'معدل النجاح')],
                  ['no_attempt_employees', tr('No Attempts', 'بدون محاولات')],
                  ['never_logged_in', tr('Never Logged In', 'لم يسجل الدخول')],
                  ['never_active', tr('Never Active', 'بدون نشاط')],
                ].map(([column, label]) => (
                  <TableCell key={column}>
                    <TableSortLabel
                      active={sortBy === column}
                      direction={sortBy === column ? sortDir : 'desc'}
                      onClick={() => handleSort(column)}
                    >
                      {label}
                    </TableSortLabel>
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {sortedRows.length ? (
                sortedRows.map((row) => (
                  <TableRow key={`branch-${row.branch_code}`} hover>
                    <TableCell>{row.branch_name || '-'}</TableCell>
                    <TableCell>{safeCount(row.total_employees)}</TableCell>
                    <TableCell>{safeCount(row.participating_employees)}</TableCell>
                    <TableCell>{safePercent(row.participation_rate_pct)}</TableCell>
                    <TableCell>{safePercent(row.average_score_pct)}</TableCell>
                    <TableCell>{safePercent(row.pass_rate_pct)}</TableCell>
                    <TableCell>{safeCount(row.no_attempt_employees)}</TableCell>
                    <TableCell>{safeCount(row.never_logged_in)}</TableCell>
                    <TableCell>{safeCount(row.never_active)}</TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={9}>{tr('No branch data available for the selected filters.', 'لا توجد بيانات فروع للفلاتر المحددة.')}</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
};

export default BranchPerformanceSection;
