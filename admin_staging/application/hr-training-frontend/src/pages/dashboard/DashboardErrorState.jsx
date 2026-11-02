import React from 'react';
import { Alert, Box, Button, Stack, Typography } from '@mui/material';

const DashboardErrorState = ({ error, onRetry, tr }) => (
  <Alert severity="error" sx={{ borderRadius: 3, '& .MuiAlert-message': { width: '100%' } }}>
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      alignItems={{ xs: 'flex-start', sm: 'center' }}
      justifyContent="space-between"
      spacing={1.5}
      sx={{ width: '100%' }}
    >
      <Box>
        <Typography sx={{ fontWeight: 700, mb: 0.4 }}>
          {tr('Management dashboard failed to load.', 'تعذر تحميل لوحة المعلومات.')}
        </Typography>
        <Typography variant="body2">
          {error || tr('Please retry the request.', 'يُرجى إعادة المحاولة.')}
        </Typography>
      </Box>
      <Button variant="outlined" color="error" onClick={onRetry}>
        {tr('Retry loading data', 'إعادة تحميل البيانات')}
      </Button>
    </Stack>
  </Alert>
);

export default DashboardErrorState;
