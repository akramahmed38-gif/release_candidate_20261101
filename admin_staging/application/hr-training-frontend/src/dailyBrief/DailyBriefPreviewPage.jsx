import React, { useEffect, useState } from 'react';
import { ArrowBack } from '@mui/icons-material';
import { Alert, Box, Button, Typography } from '@mui/material';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { dailyBriefService } from '../services/auth';
import DailyBriefArticle from './DailyBriefArticle';

export default function DailyBriefPreviewPage() {
  const { briefId } = useParams(); const navigate = useNavigate(); const location = useLocation(); const [brief, setBrief] = useState(location.state?.brief || null); const [error, setError] = useState('');
  const returnTo = location.state?.returnTo || '/daily-brief';
  const previewSessionKey = location.state?.previewSessionKey;
  const returnToBuilder = () => navigate(returnTo, previewSessionKey ? { state: { previewSessionKey } } : undefined);
  useEffect(() => { if (briefId) dailyBriefService.getBrief(briefId).then((response) => setBrief(response.data.item)).catch((e) => setError(e.response?.data?.detail || 'Unable to load Daily Brief preview.')); }, [briefId]);
  return <Box sx={{ minHeight: '100%', bgcolor: '#fafaf8', py: { xs: 3, md: 5 } }}><Box sx={{ maxWidth: 1300, mx: 'auto', px: { xs: 2, sm: 3 } }}><Button startIcon={<ArrowBack />} onClick={returnToBuilder} sx={{ mb: 2 }}>{previewSessionKey ? 'Back to Builder' : 'Back to Daily Briefs'}</Button>{error && <Alert severity="error">{error}</Alert>}{brief && <DailyBriefArticle brief={brief} apiBase={window.location.origin + (import.meta.env.VITE_BASENAME || '/training')} preview={brief.status !== 'LIVE'} />}</Box></Box>;
}
