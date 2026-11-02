import React from 'react';
import { PersonOff, WarningAmber } from '@mui/icons-material';
import { alpha } from '@mui/material/styles';
import { Box, Card, CardContent, Typography } from '@mui/material';
import { safeCount } from './managementDashboardUtils';

const AttentionKpiGrid = ({ overview, attention, theme, tr }) => {
  const cards = [
    {
      key: 'resigned_employees',
      label: tr('Resigned Employees', 'الموظفون المستقيلون'),
      value: safeCount(overview.resigned_employees),
      accent: '#F2BF00',
      icon: <PersonOff fontSize="small" />,
      subtitle: tr('Employees currently recorded as resigned.', 'الموظفون المسجلون حالياً كمستقيلين.'),
    },
    {
      key: 'no_exam_attempts',
      label: tr('No Exam Attempts', 'بدون محاولات اختبار'),
      value: safeCount(overview.no_exam_attempts),
      accent: '#B45309',
      icon: <WarningAmber fontSize="small" />,
      subtitle: tr(
        'Assigned eligible employees with no submitted attempt.',
        'الموظفون المؤهلون المعيّنون الذين لم يرسلوا أي محاولة.'
      ),
    },
    {
      key: 'never_logged_in',
      label: tr('Never Logged In', 'لم يسجل الدخول'),
      value: safeCount(overview.never_logged_in),
      accent: '#0b4fa8',
      icon: <WarningAmber fontSize="small" />,
      subtitle: tr('Employees with no recorded login evidence.', 'الموظفون الذين لا يوجد لهم أي دليل تسجيل دخول.'),
    },
    {
      key: 'never_active',
      label: tr('Never Active', 'بدون نشاط'),
      value: safeCount(overview.never_active),
      accent: '#7C3AED',
      icon: <WarningAmber fontSize="small" />,
      subtitle: tr('Employees with no recorded activity evidence.', 'الموظفون الذين لا يوجد لهم أي نشاط مسجل.'),
    },
  ];

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))', xl: 'repeat(4, minmax(0, 1fr))' },
        gap: 2,
      }}
    >
      {cards.map((card) => (
        <Card key={card.key} sx={{ borderRadius: 4, border: `1px solid ${alpha(card.accent, 0.14)}` }}>
          <CardContent>
            <Box
              sx={{
                width: 40,
                height: 40,
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
            <Typography sx={{ fontSize: { xs: '1.8rem', md: '2rem' }, fontWeight: 800, color: '#102a56' }}>
              {card.value}
            </Typography>
            <Typography color="text.secondary" variant="body2" sx={{ mt: 0.5 }}>
              {card.subtitle}
            </Typography>
            {card.key === 'no_exam_attempts' ? (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                {tr(
                  `Low scores: ${safeCount(attention.low_score_count)} | Repeated failures: ${safeCount(attention.repeated_failure_count)}`,
                  `الدرجات المنخفضة: ${safeCount(attention.low_score_count)} | الرسوب المتكرر: ${safeCount(attention.repeated_failure_count)}`
                )}
              </Typography>
            ) : null}
          </CardContent>
        </Card>
      ))}
    </Box>
  );
};

export default AttentionKpiGrid;
