import React from 'react';
import { Box, Button } from '@mui/material';
import { useLanguage } from '../../context/LanguageContext';

const LanguageToggle = ({ compact = false, abbreviated = false }) => {
  const { lang, setLanguage } = useLanguage();
  const useShortLabels = compact && abbreviated;
  const arLabel = useShortLabels ? 'AR' : 'العربية';
  const enLabel = useShortLabels ? 'EN' : 'English';
  const compactMinWidth = useShortLabels ? { xs: 42, sm: 46 } : { xs: 58, sm: 68 };
  const compactPaddingX = useShortLabels ? 0.95 : 1.5;
  const compactFontSize = useShortLabels ? 11.5 : 12;

  return (
    <Box
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 0.35,
        p: useShortLabels ? 0.28 : 0.45,
        borderRadius: 999,
        border: '1px solid rgba(31,53,88,0.12)',
        background: 'linear-gradient(180deg, rgba(255,255,255,0.92), rgba(255,249,231,0.86))',
        boxShadow: '0 10px 20px rgba(31,53,88,0.06), inset 0 1px 0 rgba(255,255,255,0.9)',
      }}
    >
      <Button
        size={compact ? 'small' : 'medium'}
        onClick={() => setLanguage('ar')}
        sx={{
          minWidth: compact ? compactMinWidth : { xs: 68, sm: 80 },
          px: compact ? compactPaddingX : 2,
          py: compact ? 0.4 : 0.6,
          borderRadius: 999,
          fontSize: compact ? compactFontSize : 13,
          fontWeight: 700,
          color: lang === 'ar' ? '#17263D' : '#667085',
          background:
            lang === 'ar'
              ? 'linear-gradient(135deg, rgba(255,241,168,0.96), rgba(255,210,0,0.92))'
              : 'transparent',
          boxShadow: lang === 'ar' ? '0 10px 18px rgba(176,138,0,0.16)' : 'none',
          transition:
            'transform 220ms cubic-bezier(0.22, 1, 0.36, 1), background-color 220ms cubic-bezier(0.22, 1, 0.36, 1), box-shadow 220ms cubic-bezier(0.22, 1, 0.36, 1)',
          '&:hover': {
            transform: 'translateY(-1px)',
            background:
              lang === 'ar'
                ? 'linear-gradient(135deg, rgba(255,241,168,1), rgba(255,210,0,1))'
                : 'rgba(255,210,0,0.10)',
          },
        }}
      >
        {arLabel}
      </Button>

      <Button
        size={compact ? 'small' : 'medium'}
        onClick={() => setLanguage('en')}
        sx={{
          minWidth: compact ? compactMinWidth : { xs: 68, sm: 80 },
          px: compact ? compactPaddingX : 2,
          py: compact ? 0.4 : 0.6,
          borderRadius: 999,
          fontSize: compact ? compactFontSize : 13,
          fontWeight: 700,
          color: lang === 'en' ? '#17263D' : '#667085',
          background:
            lang === 'en'
              ? 'linear-gradient(135deg, rgba(255,241,168,0.96), rgba(255,210,0,0.92))'
              : 'transparent',
          boxShadow: lang === 'en' ? '0 10px 18px rgba(176,138,0,0.16)' : 'none',
          transition:
            'transform 220ms cubic-bezier(0.22, 1, 0.36, 1), background-color 220ms cubic-bezier(0.22, 1, 0.36, 1), box-shadow 220ms cubic-bezier(0.22, 1, 0.36, 1)',
          '&:hover': {
            transform: 'translateY(-1px)',
            background:
              lang === 'en'
                ? 'linear-gradient(135deg, rgba(255,241,168,1), rgba(255,210,0,1))'
                : 'rgba(255,210,0,0.10)',
          },
        }}
      >
        {enLabel}
      </Button>
    </Box>
  );
};

export default LanguageToggle;
