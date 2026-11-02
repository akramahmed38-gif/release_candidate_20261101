import React from 'react';
import { AccessTime, Refresh } from '@mui/icons-material';
import { Box, Button, Stack, Typography } from '@mui/material';
import { safeDateTimeLabel } from './managementDashboardUtils';

const ManagementDashboardHeader = ({
  generatedAt,
  loading,
  onRefresh,
  tr,
  title,
  description,
}) => (
  <Stack
    direction={{ xs: 'column', lg: 'row' }}
    justifyContent="space-between"
    alignItems={{ xs: 'flex-start', lg: 'center' }}
    spacing={1.5}
  >
    <Box>
      <Typography sx={{ fontSize: { xs: '2rem', md: '2.6rem' }, fontWeight: 800, color: '#102a56' }}>
        {title || tr('Management Dashboard', 'لوحة الإدارة')}
      </Typography>
      <Typography color="text.secondary" sx={{ mt: 0.7, maxWidth: 760 }}>
        {description ||
          tr(
            'Executive view across employees, exam participation, branch performance, resigned users, and current management alerts.',
            'عرض تنفيذي لمتابعة الموظفين، ومشاركة الاختبارات، وأداء الفروع، والمستقيلين، والتنبيهات الإدارية الحالية.'
          )}
      </Typography>
    </Box>

    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ xs: 'flex-start', sm: 'center' }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ color: 'text.secondary' }}>
        <AccessTime fontSize="small" />
        <Typography variant="body2">
          {tr('Last refreshed', 'آخر تحديث')}: {safeDateTimeLabel(generatedAt)}
        </Typography>
      </Stack>
      <Button
        variant="outlined"
        startIcon={<Refresh />}
        onClick={onRefresh}
        disabled={loading}
        sx={{ borderRadius: 999 }}
      >
        {tr('Refresh', 'تحديث')}
      </Button>
    </Stack>
  </Stack>
);

export default ManagementDashboardHeader;
