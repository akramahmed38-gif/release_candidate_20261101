import React from 'react';
import { Box, Card, CardContent, Skeleton, Stack } from '@mui/material';

const DashboardLoadingState = () => (
  <Stack spacing={2.5}>
    <Card>
      <CardContent>
        <Stack spacing={1.2}>
          <Skeleton variant="text" width={260} height={44} />
          <Skeleton variant="text" width="45%" height={28} />
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(5, 1fr)' }, gap: 1.5, mt: 1 }}>
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} variant="rounded" height={56} />
            ))}
          </Box>
        </Stack>
      </CardContent>
    </Card>

    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'repeat(3, 1fr)' }, gap: 2 }}>
      {Array.from({ length: 6 }).map((_, index) => (
        <Card key={index}>
          <CardContent>
            <Skeleton variant="text" width="50%" height={24} />
            <Skeleton variant="text" width="35%" height={48} />
            <Skeleton variant="text" width="70%" height={22} />
          </CardContent>
        </Card>
      ))}
    </Box>

    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', xl: '2fr 1fr' }, gap: 2 }}>
      <Card>
        <CardContent>
          <Skeleton variant="text" width={220} height={34} />
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' }, gap: 2 }}>
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} variant="rounded" height={240} />
            ))}
          </Box>
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          <Skeleton variant="text" width={200} height={34} />
          <Stack spacing={1.4} sx={{ mt: 1 }}>
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} variant="rounded" height={72} />
            ))}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  </Stack>
);

export default DashboardLoadingState;
