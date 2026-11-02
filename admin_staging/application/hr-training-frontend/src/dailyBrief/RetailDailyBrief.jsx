import React, { useEffect, useState } from 'react';
import { Alert, Box, Card, CardContent, Typography } from '@mui/material';
import { dailyBriefService } from '../services/auth';
import DailyBriefArticle from './DailyBriefArticle';

export default function RetailDailyBrief() {
  const [brief, setBrief] = useState(null); const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  useEffect(() => { dailyBriefService.getCurrent().then((response) => setBrief(response.data.item)).catch((e) => setError(e.response?.data?.detail || 'Unable to load Daily Brief.')).finally(() => setLoading(false)); }, []);
  if (loading) return <Typography>Loading Daily Brief...</Typography>;
  return <Box sx={{ minHeight: '100%', bgcolor: '#fafaf8', py: { xs: 3, md: 5 } }}><Box sx={{ maxWidth: 1300, mx: 'auto', px: { xs: 2, sm: 3 } }}>{error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}{brief ? <DailyBriefArticle brief={brief} apiBase={window.location.origin + (import.meta.env.VITE_BASENAME || '/training')} /> : <Card variant="outlined" sx={{ maxWidth: 900, mx: 'auto', borderRadius: 3 }}><CardContent sx={{ p: 5, textAlign: 'center' }}><Typography variant="h6" fontWeight={800}>No Daily Brief has been published yet.</Typography><Typography color="text.secondary" sx={{ mt: 1 }}>Check again later.</Typography></CardContent></Card>}</Box></Box>;
}
