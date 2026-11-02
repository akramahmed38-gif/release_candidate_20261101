import React from 'react';
import { Alert, Box, Card, CardContent, Chip, Stack, Typography } from '@mui/material';

const severityColor = {
  high: 'error',
  medium: 'warning',
  low: 'info',
};

const ManagementAlertsPanel = ({ alerts, tr }) => (
  <Card sx={{ borderRadius: 4, height: '100%' }}>
    <CardContent>
      <Typography sx={{ fontSize: '1.35rem', fontWeight: 800, color: '#102a56', mb: 0.5 }}>
        {tr('Management Alerts', 'التنبيهات الإدارية')}
      </Typography>
      <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>
        {tr(
          'Live alerts are calculated from the current dashboard aggregates and ordered by severity.',
          'يتم احتساب التنبيهات مباشرة من المؤشرات الحالية وترتيبها حسب الشدة.'
        )}
      </Typography>

      {alerts.length ? (
        <Stack spacing={1.25}>
          {alerts.map((alert) => (
            <Alert
              key={alert.code}
              severity={severityColor[alert.severity] || 'info'}
              sx={{ borderRadius: 3, alignItems: 'flex-start' }}
            >
              <Stack spacing={0.8}>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                  <Typography sx={{ fontWeight: 800 }}>{alert.title}</Typography>
                  <Chip
                    size="small"
                    label={String(alert.severity || '').toUpperCase()}
                    color={severityColor[alert.severity] || 'info'}
                    variant="outlined"
                  />
                </Stack>
                <Typography variant="body2">{alert.message}</Typography>
              </Stack>
            </Alert>
          ))}
        </Stack>
      ) : (
        <Box
          sx={{
            minHeight: 220,
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
            {tr('No management alerts for the selected filters.', 'لا توجد تنبيهات إدارية للفلاتر المحددة.')}
          </Typography>
        </Box>
      )}
    </CardContent>
  </Card>
);

export default ManagementAlertsPanel;
