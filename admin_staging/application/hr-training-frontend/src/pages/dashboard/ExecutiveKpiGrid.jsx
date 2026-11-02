import React from 'react';
import { Assessment, Group, TaskAlt, WarningAmber } from '@mui/icons-material';
import { alpha } from '@mui/material/styles';
import { Box, Card, CardContent, Typography } from '@mui/material';
import { safeCount, safePercent } from './managementDashboardUtils';

const ExecutiveKpiGrid = ({ overview, theme, tr }) => {
  const cards = [
    {
      key: 'active_employees',
      label: tr('Active Employees', 'الموظفون النشطون'),
      value: safeCount(overview.active_employees),
      subtitle: tr('Current non-resigned employee accounts.', 'الحسابات الحالية للموظفين غير المستقيلين.'),
      accent: theme.palette.primary.dark,
      icon: <Group fontSize="small" />,
    },
    {
      key: 'training_participation_rate',
      label: tr('Training Participation', 'مشاركة التدريب'),
      value: safePercent(overview.training_participation_rate),
      subtitle: tr(
        'Eligible employees with at least one submitted attempt.',
        'الموظفون المؤهلون الذين لديهم محاولة اختبار واحدة على الأقل.'
      ),
      accent: theme.palette.success.main,
      icon: <Assessment fontSize="small" />,
    },
    {
      key: 'average_exam_score_pct',
      label: tr('Average Exam Score', 'متوسط درجات الاختبارات'),
      value: safePercent(overview.average_exam_score_pct),
      subtitle: tr(
        'Average percentage score across submitted attempts.',
        'متوسط النسبة المئوية لجميع المحاولات المسلّمة.'
      ),
      accent: '#0b4fa8',
      icon: <Assessment fontSize="small" />,
    },
    {
      key: 'pass_rate_pct',
      label: tr('Pass Rate', 'معدل النجاح'),
      value: safePercent(overview.pass_rate_pct),
      subtitle: tr(
        'Submitted attempts that reached the passing score.',
        'المحاولات المسلّمة التي حققت درجة النجاح.'
      ),
      accent: '#D8AE00',
      icon: <TaskAlt fontSize="small" />,
    },
    {
      key: 'active_open_exams',
      label: tr('Active/Open Exams', 'الاختبارات المفتوحة'),
      value: safeCount(overview.active_open_exams),
      subtitle: tr('Exams currently available or configured as open.', 'الاختبارات المتاحة حالياً أو المهيأة كمفتوحة.'),
      accent: '#7B61FF',
      icon: <Assessment fontSize="small" />,
    },
    {
      key: 'overdue_open_exams',
      label: tr('Overdue Open Exams', 'اختبارات مفتوحة متأخرة'),
      value: safeCount(overview.overdue_open_exams),
      subtitle: tr(
        'Open exams with an end date earlier than today.',
        'اختبارات مفتوحة تاريخ انتهائها قبل اليوم.'
      ),
      accent: '#B45309',
      icon: <WarningAmber fontSize="small" />,
      valueColor: overview.overdue_open_exams > 0 ? '#B45309' : theme.palette.text.primary,
    },
  ];

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))', xl: 'repeat(6, minmax(0, 1fr))' },
        gap: 2,
      }}
    >
      {cards.map((card) => (
        <Card key={card.key} sx={{ borderRadius: 4, border: `1px solid ${alpha(card.accent, 0.14)}` }}>
          <CardContent>
            <Box
              sx={{
                width: 42,
                height: 42,
                borderRadius: '50%',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                bgcolor: alpha(card.accent, 0.12),
                color: card.accent,
                mb: 1,
              }}
            >
              {card.icon}
            </Box>
            <Typography color="text.secondary" sx={{ fontSize: '0.9rem', fontWeight: 700 }}>
              {card.label}
            </Typography>
            <Typography sx={{ fontSize: { xs: '1.9rem', md: '2.2rem' }, fontWeight: 800, color: card.valueColor || '#102a56' }}>
              {card.value}
            </Typography>
            <Typography color="text.secondary" variant="body2" sx={{ mt: 0.5 }}>
              {card.subtitle}
            </Typography>
          </CardContent>
        </Card>
      ))}
    </Box>
  );
};

export default ExecutiveKpiGrid;
