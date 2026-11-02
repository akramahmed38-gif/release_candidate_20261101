import React from 'react';
import { CampaignOutlined, CheckCircleOutline, ErrorOutline, InfoOutlined, LightbulbOutlined, NotificationsNone, StarOutlined, WarningAmberOutlined } from '@mui/icons-material';
import { Box, Stack, Typography } from '@mui/material';

const styles = {
  standard: { label: 'NOTE', Icon: LightbulbOutlined, background: '#EEF2FF', border: '#C7D2FE', accent: '#6366F1', title: '#312E81', text: '#4338CA' },
  important: { label: 'IMPORTANT', Icon: StarOutlined, background: '#FFFBEB', border: '#FDE68A', accent: '#D97706', title: '#92400E', text: '#92400E' },
  information: { label: 'INFORMATION', Icon: InfoOutlined, background: '#EFF6FF', border: '#BFDBFE', accent: '#2563EB', title: '#1E3A8A', text: '#1E40AF' },
  success: { label: 'SUCCESS', Icon: CheckCircleOutline, background: '#F0FDF4', border: '#BBF7D0', accent: '#16A34A', title: '#166534', text: '#166534' },
  warning: { label: 'CAUTION', Icon: WarningAmberOutlined, background: '#FFF7ED', border: '#FED7AA', accent: '#EA580C', title: '#9A3412', text: '#9A3412' },
  critical: { label: 'CRITICAL', Icon: ErrorOutline, background: '#FEF2F2', border: '#FECACA', accent: '#DC2626', title: '#991B1B', text: '#991B1B' },
};
const alertLabels = { standard: 'NOTICE', important: 'IMPORTANT NOTICE', information: 'INFO NOTICE', success: 'RESOLVED', warning: 'WARNING', critical: 'CRITICAL ALERT' };
const alertIcons = { standard: NotificationsNone, important: CampaignOutlined, information: InfoOutlined, success: CheckCircleOutline, warning: WarningAmberOutlined, critical: ErrorOutline };

export const semanticStyleKeys = Object.keys(styles);
export const getSemanticStyle = (type, style = 'standard') => {
  const base = styles[style] || styles.standard;
  const accentWidth = style === 'critical' ? 7 : type === 'alert' || style === 'warning' ? 6 : style === 'important' ? 5 : 4;
  return type === 'alert'
    ? { ...base, label: alertLabels[style] || alertLabels.standard, Icon: alertIcons[style] || NotificationsNone, accentWidth }
    : { ...base, accentWidth };
};

export function SemanticBlock({ type = 'highlight', style = 'standard', heading, text, compact = false }) {
  const semantic = getSemanticStyle(type, style);
  const { Icon } = semantic;
  const isRtl = /[\u0600-\u06FF]/.test(`${heading || ''} ${text || ''}`);
  return (
    <Box
      dir={isRtl ? 'rtl' : 'auto'}
      sx={{
        width: '100%',
        height: 'auto',
        p: compact ? 1.5 : { xs: 2.5, md: 3.25 },
        borderRadius: compact ? 1.5 : 2,
        bgcolor: semantic.background,
        border: `${style === 'warning' ? 1.5 : 1}px solid ${semantic.border}`,
        borderInlineStart: `${semantic.accentWidth}px solid ${semantic.accent}`,
      }}
    >
      <Stack
        direction="row"
        useFlexGap
        alignItems="flex-start"
        sx={{ gap: compact ? 1.5 : { xs: 3, md: 4.5 } }}
      >
        <Box
          sx={{
            display: 'grid',
            placeItems: 'center',
            flexShrink: 0,
            width: compact ? 38 : { xs: 52, md: 60 },
            height: compact ? 38 : { xs: 52, md: 60 },
            borderRadius: '50%',
            bgcolor: `${semantic.accent}12`,
            color: semantic.accent,
            border: `1.5px solid ${semantic.border}`,
            boxShadow: `0 6px 16px ${semantic.accent}14`,
          }}
        >
          <Icon aria-hidden="true" sx={{ fontSize: compact ? 21 : { xs: 28, md: 32 } }} />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0, textAlign: isRtl ? 'right' : 'left' }}>
          <Typography
            sx={{
              color: semantic.accent,
              fontSize: compact ? '.6875rem' : { xs: '.75rem', md: '.8125rem' },
              lineHeight: 1.25,
              letterSpacing: '.06em',
              fontWeight: 700,
            }}
          >
            {semantic.label}
          </Typography>
          {heading ? (
            <Typography
              sx={{
                mt: .5,
                color: semantic.title,
                fontSize: compact ? '.95rem' : { xs: '1.1875rem', md: '1.3125rem' },
                fontWeight: 700,
                lineHeight: 1.4,
              }}
            >
              {heading}
            </Typography>
          ) : null}
          {text ? (
            <Typography
              sx={{
                mt: heading ? .75 : .5,
                color: semantic.text,
                fontSize: compact ? '.8125rem' : { xs: '1rem', md: '1.0625rem' },
                fontWeight: 400,
                lineHeight: 1.7,
                whiteSpace: 'pre-line',
              }}
            >
              {text}
            </Typography>
          ) : null}
        </Box>
      </Stack>
    </Box>
  );
}
