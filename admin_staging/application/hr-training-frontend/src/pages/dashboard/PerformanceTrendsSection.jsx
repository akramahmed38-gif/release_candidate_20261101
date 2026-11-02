import React, { useMemo } from 'react';
import { Box, Card, CardContent, Typography } from '@mui/material';
import { alpha } from '@mui/material/styles';
import { Bar, Line } from 'react-chartjs-2';
import { safePercent } from './managementDashboardUtils';

const buildLineOptions = (theme, isArabic, percent = false) => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: { rtl: isArabic },
  },
  scales: {
    x: {
      ticks: { color: theme.palette.text.secondary, maxRotation: 0 },
      grid: { color: alpha(theme.palette.secondary.main, 0.08) },
    },
    y: {
      ticks: {
        color: theme.palette.text.secondary,
        callback: (value) => (percent ? `${value}%` : value),
      },
      grid: { color: alpha(theme.palette.secondary.main, 0.08) },
    },
  },
});

const TrendChartCard = ({ title, subtitle, height = 240, children }) => (
  <Card sx={{ borderRadius: 4 }}>
    <CardContent>
      <Typography sx={{ fontSize: '1.08rem', fontWeight: 800, color: '#102a56' }}>{title}</Typography>
      <Typography color="text.secondary" variant="body2" sx={{ mb: 1.5 }}>
        {subtitle}
      </Typography>
      <Box sx={{ height }}>{children}</Box>
    </CardContent>
  </Card>
);

const PerformanceTrendsSection = ({ trends, theme, isArabic, tr }) => {
  const items = trends.items || [];
  const labels = useMemo(() => items.map((item) => item.label), [items]);

  const participantsData = useMemo(
    () => ({
      labels,
      datasets: [
        {
          data: items.map((item) => Number(item.participants || 0)),
          borderColor: theme.palette.primary.dark,
          backgroundColor: alpha(theme.palette.primary.main, 0.12),
          pointRadius: 2,
          tension: 0.28,
          fill: true,
        },
      ],
    }),
    [items, labels, theme.palette.primary.dark, theme.palette.primary.main]
  );

  const attemptsData = useMemo(
    () => ({
      labels,
      datasets: [
        {
          data: items.map((item) => Number(item.attempts || 0)),
          backgroundColor: theme.palette.secondary.main,
          borderRadius: 6,
        },
      ],
    }),
    [items, labels, theme.palette.secondary.main]
  );

  const scoreData = useMemo(
    () => ({
      labels,
      datasets: [
        {
          data: items.map((item) => Number(item.average_score_pct || 0)),
          borderColor: theme.palette.success.main,
          backgroundColor: alpha(theme.palette.success.main, 0.12),
          pointRadius: 2,
          tension: 0.28,
          fill: true,
        },
      ],
    }),
    [items, labels, theme.palette.success.main]
  );

  const passRateData = useMemo(
    () => ({
      labels,
      datasets: [
        {
          data: items.map((item) => Number(item.pass_rate_pct || 0)),
          borderColor: '#D8AE00',
          backgroundColor: alpha('#D8AE00', 0.12),
          pointRadius: 2,
          tension: 0.28,
          fill: true,
        },
      ],
    }),
    [items, labels]
  );

  return (
    <Card sx={{ borderRadius: 4 }}>
      <CardContent>
        <Typography sx={{ fontSize: '1.35rem', fontWeight: 800, color: '#102a56', mb: 0.5 }}>
          {tr('Performance Trends', 'اتجاهات الأداء')}
        </Typography>
        <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>
          {tr(
            'Participants, attempts, average score, and pass rate all follow the selected period and filters.',
            'تعكس أعداد المشاركين والمحاولات ومتوسط الدرجات ومعدل النجاح نفس الفترة والفلاتر المختارة.'
          )}
        </Typography>

        {items.length ? (
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', xl: 'repeat(2, minmax(0, 1fr))' },
              gap: 2,
            }}
          >
            <TrendChartCard
              title={tr('Exam Participants Over Time', 'المشاركون في الاختبارات عبر الوقت')}
              subtitle={tr('Distinct employees with at least one submitted attempt.', 'عدد الموظفين المختلفين الذين قدّموا محاولة واحدة على الأقل.')}
            >
              <Line data={participantsData} options={buildLineOptions(theme, isArabic)} />
            </TrendChartCard>

            <TrendChartCard
              title={tr('Exam Attempts Over Time', 'محاولات الاختبارات عبر الوقت')}
              subtitle={tr('Submitted exam attempts in each time bucket.', 'عدد المحاولات المسلّمة داخل كل فترة زمنية.')}
            >
              <Bar data={attemptsData} options={buildLineOptions(theme, isArabic)} />
            </TrendChartCard>

            <TrendChartCard
              title={tr('Average Score Over Time', 'متوسط الدرجات عبر الوقت')}
              subtitle={tr('Average percentage score for submitted attempts.', 'متوسط النسبة المئوية للمحاولات المسلّمة.')}
            >
              <Line data={scoreData} options={buildLineOptions(theme, isArabic, true)} />
            </TrendChartCard>

            <TrendChartCard
              title={tr('Pass Rate Over Time', 'معدل النجاح عبر الوقت')}
              subtitle={tr('Passing attempts as a percentage of submitted attempts.', 'نسبة المحاولات الناجحة من إجمالي المحاولات المسلّمة.')}
            >
              <Line data={passRateData} options={buildLineOptions(theme, isArabic, true)} />
            </TrendChartCard>
          </Box>
        ) : (
          <Box
            sx={{
              minHeight: 240,
              borderRadius: 3,
              border: '1px dashed rgba(16,42,86,0.18)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center',
              px: 2,
            }}
          >
            <Typography color="text.secondary">
              {tr('No data available for the selected filters.', 'لا توجد بيانات متاحة للفلاتر المحددة.')}
            </Typography>
          </Box>
        )}

        {items.length ? (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
            {tr('Latest pass rate', 'أحدث معدل نجاح')}: {safePercent(items[items.length - 1]?.pass_rate_pct)}
          </Typography>
        ) : null}
      </CardContent>
    </Card>
  );
};

export default PerformanceTrendsSection;
