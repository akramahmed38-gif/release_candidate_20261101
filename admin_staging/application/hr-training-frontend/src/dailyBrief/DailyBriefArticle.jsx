import React from 'react';
import { CampaignOutlined, FiberManualRecord, VisibilityOutlined } from '@mui/icons-material';
import { Box, Stack, Typography } from '@mui/material';
import { useLanguage } from '../context/LanguageContext';
import DailyBriefRenderer from './DailyBriefRenderer';
import DailyBriefFeedback from './DailyBriefFeedback';

const dateOnly = (value) => value ? new Intl.DateTimeFormat(undefined, { month: 'long', day: 'numeric', year: 'numeric' }).format(new Date(`${value}T12:00:00`)) : '';

export default function DailyBriefArticle({ brief, apiBase = '', preview = false }) {
  const { t } = useLanguage();
  const isRtl = /[\u0600-\u06FF]/.test(brief?.title || '');
  const hasViewCount = !preview && Number.isFinite(brief?.total_view_count);
  const canGiveFeedback = !preview && brief?.status === 'LIVE' && Object.prototype.hasOwnProperty.call(brief, 'current_user_reaction');
  return <Box component="article" dir={isRtl ? 'rtl' : 'auto'} sx={{ maxWidth: 1240, mx: 'auto' }}>
    <Box component="header" sx={{ pb: { xs: 2.5, md: 3 }, borderBottom: '1px solid #dfe4ea' }}>
      <Box sx={{ minWidth: 0 }}>
        <Typography component="h1" sx={{ color: '#102a56', fontWeight: 800, fontSize: { xs: '1.9rem', sm: '2.35rem', md: '2.75rem' }, lineHeight: 1.2, overflowWrap: 'anywhere' }}>{brief?.title}</Typography>
        <Typography sx={{ mt: .8, color: '#64748b', fontSize: { xs: '1rem', md: '1.0625rem' }, lineHeight: 1.7 }}>
          {isRtl ? 'تعليمات وتحديثات مهمة لفريق التجزئة.' : 'Key updates and instructions for Retail staff.'}
        </Typography>
        <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1.15 }}>
          <Typography variant="body2" sx={{ color: '#64748b', fontWeight: 700 }}>{dateOnly(brief?.brief_date)}</Typography>
          <FiberManualRecord aria-hidden="true" sx={{ fontSize: 7, color: '#9aa5b5' }} />
          <Stack direction="row" useFlexGap alignItems="center" sx={{ gap: 1.25 }}>
            <CampaignOutlined sx={{ display: 'block', flexShrink: 0, fontSize: 18, color: '#55657d' }} aria-hidden="true" />
            <Typography variant="body2" sx={{ color: '#55657d', fontWeight: 800, letterSpacing: '.045em' }}>RETAIL COMMUNICATION</Typography>
          </Stack>
          {hasViewCount && <Stack direction="row" alignItems="center" spacing={0.6} aria-label={`${brief.total_view_count} ${t('employees viewed this Daily Brief', 'موظفًا شاهدوا هذا الملخص اليومي')}`}>
            <VisibilityOutlined aria-hidden="true" sx={{ fontSize: 18, color: '#55657d' }} />
            <Typography variant="body2" sx={{ color: '#55657d', fontWeight: 800 }}>{brief.total_view_count}</Typography>
          </Stack>}
        </Stack>
      </Box>
      <Box sx={{ width: 48, height: 4, borderRadius: 1, bgcolor: '#ffd200', mt: 2.25 }} />
    </Box>
    <Box sx={{ pt: { xs: 3, md: 3.5 }, pb: { xs: 1, md: 2 } }}><DailyBriefRenderer brief={brief} apiBase={apiBase} preview={preview} /></Box>
    {canGiveFeedback && <DailyBriefFeedback brief={brief} />}
  </Box>;
}
