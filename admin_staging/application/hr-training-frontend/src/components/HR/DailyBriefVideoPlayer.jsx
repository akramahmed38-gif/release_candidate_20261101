import React, { useMemo, useState } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  Typography,
} from '@mui/material';
import { ArrowBack, PlayCircleOutline } from '@mui/icons-material';
import { normalizedBasePath } from '../../services/sessionAuth';
import { useLanguage } from '../../context/LanguageContext';

const getFileNameFromPath = (materialPath, fallbackName = '') => {
  if (fallbackName) {
    return fallbackName;
  }

  if (!materialPath) {
    return '';
  }

  const segments = String(materialPath)
    .split('/')
    .filter(Boolean);
  return segments.length ? decodeURIComponent(segments[segments.length - 1]) : '';
};

const DailyBriefVideoPlayer = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { isArabic } = useLanguage();
  const [preparing, setPreparing] = useState(true);
  const [errorMessage, setErrorMessage] = useState('');

  const tr = (englishText, arabicText) => (isArabic ? arabicText : englishText);

  const materialPath = searchParams.get('path') || '';
  const videoName = getFileNameFromPath(materialPath, location.state?.fileName || '');
  const streamUrl = useMemo(() => {
    if (!materialPath) {
      return '';
    }
    return `${normalizedBasePath}/api/v1/daily-brief/stream?path=${encodeURIComponent(materialPath)}`;
  }, [materialPath]);

  const handleBack = () => {
    if (window.history.length > 1) {
      navigate(-1);
      return;
    }
    navigate('/script-book');
  };

  return (
    <Box sx={{ direction: isArabic ? 'rtl' : 'ltr' }}>
      <Stack spacing={2}>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          justifyContent="space-between"
          alignItems={{ xs: 'flex-start', sm: 'center' }}
          spacing={1.5}
        >
          <Stack spacing={1}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <PlayCircleOutline color="primary" />
              <Typography
                fontWeight={650}
                sx={{ fontSize: { xs: '1.9rem', md: '2.1rem' }, lineHeight: 1.15 }}
              >
                {tr('Training Video Player', 'Ù…Ø´ØºÙ„ Ø§Ù„ÙÙŠØ¯ÙŠÙˆ Ø§Ù„ØªØ¯Ø±ÙŠØ¨ÙŠ')}
              </Typography>
            </Stack>
            <Typography color="text.secondary" sx={{ lineHeight: 1.5 }}>
              {tr(
                'Play training videos directly from the material library with progressive streaming.',
                'Ø´ØºÙ‘Ù„ ÙÙŠØ¯ÙŠÙˆÙ‡Ø§Øª Ø§Ù„ØªØ¯Ø±ÙŠØ¨ Ù…Ø¨Ø§Ø´Ø±Ø© Ù…Ù† Ù…ÙƒØªØ¨Ø© Ø§Ù„Ù…ÙˆØ§Ø¯ Ù…Ø¹ Ø¨Ø« ØªØ¯Ø±ÙŠØ¬ÙŠ.'
              )}
            </Typography>
          </Stack>

          <Button variant="outlined" startIcon={<ArrowBack />} onClick={handleBack}>
            {tr('Back', 'Ø±Ø¬ÙˆØ¹')}
          </Button>
        </Stack>

        {!materialPath ? (
          <Alert severity="error">
            {tr(
              'No video path was provided. Please return to the material library and try again.',
              'Ù„Ù… ÙŠØªÙ… ØªÙˆÙÙŠØ± Ù…Ø³Ø§Ø± ÙÙŠØ¯ÙŠÙˆ. Ø¨Ø±Ø¬Ø§Ø¡ Ø§Ù„Ø¹ÙˆØ¯Ø© Ø¥Ù„Ù‰ Ù…ÙƒØªØ¨Ø© Ø§Ù„Ù…ÙˆØ§Ø¯ ÙˆØ§Ù„Ù…Ø­Ø§ÙˆÙ„Ø© Ù…Ø±Ø© Ø£Ø®Ø±Ù‰.'
            )}
          </Alert>
        ) : null}

        <Card>
          <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {tr('Video file', 'Ù…Ù„Ù Ø§Ù„ÙÙŠØ¯ÙŠÙˆ')}
              </Typography>
              <Typography
                sx={{
                  mt: 0.5,
                  fontWeight: 700,
                  fontSize: { xs: '1.15rem', md: '1.35rem' },
                  color: '#0b1f4d',
                  wordBreak: 'break-word',
                }}
              >
                {videoName || tr('Unnamed video', 'ÙÙŠØ¯ÙŠÙˆ Ø¨Ø¯ÙˆÙ† Ø§Ø³Ù…')}
              </Typography>
            </Box>

            <Typography
              variant="body2"
              sx={{
                color: 'text.secondary',
                direction: 'ltr',
                unicodeBidi: 'plaintext',
                wordBreak: 'break-all',
              }}
            >
              {materialPath || tr('No relative path available.', 'Ù„Ø§ ÙŠÙˆØ¬Ø¯ Ù…Ø³Ø§Ø± Ù†Ø³Ø¨ÙŠ Ù…ØªØ§Ø­.')}
            </Typography>

            {materialPath ? (
              <Box sx={{ position: 'relative' }}>
                <Box
                  component="video"
                  key={streamUrl}
                  controls
                  preload="metadata"
                  src={streamUrl}
                  onLoadStart={() => {
                    setPreparing(true);
                    setErrorMessage('');
                  }}
                  onLoadedMetadata={() => setPreparing(false)}
                  onCanPlay={() => setPreparing(false)}
                  onError={() => {
                    setPreparing(false);
                    setErrorMessage(
                      tr(
                        'The video could not be loaded. Please refresh the page or try again later.',
                        'ØªØ¹Ø°Ø± ØªØ­Ù…ÙŠÙ„ Ø§Ù„ÙÙŠØ¯ÙŠÙˆ. Ø¨Ø±Ø¬Ø§Ø¡ ØªØ­Ø¯ÙŠØ« Ø§Ù„ØµÙØ­Ø© Ø£Ùˆ Ø§Ù„Ù…Ø­Ø§ÙˆÙ„Ø© Ù„Ø§Ø­Ù‚Ø§Ù‹.'
                      )
                    );
                  }}
                  sx={{
                    width: '100%',
                    minHeight: { xs: 240, md: 420 },
                    maxHeight: '72vh',
                    borderRadius: 3,
                    bgcolor: '#000',
                    display: 'block',
                    overflow: 'hidden',
                  }}
                />

                {preparing ? (
                  <Box
                    sx={{
                      position: 'absolute',
                      inset: 0,
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 1.5,
                      bgcolor: 'rgba(11, 31, 77, 0.28)',
                      color: '#fff',
                      borderRadius: 3,
                      pointerEvents: 'none',
                    }}
                  >
                    <CircularProgress size={32} sx={{ color: '#fff' }} />
                    <Typography sx={{ fontWeight: 600 }}>
                      {tr('Preparing video stream...', 'Ø¬Ø§Ø±Ù ØªØ¬Ù‡ÙŠØ² Ø¨Ø« Ø§Ù„ÙÙŠØ¯ÙŠÙˆ...')}
                    </Typography>
                  </Box>
                ) : null}
              </Box>
            ) : null}

            {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
          </CardContent>
        </Card>
      </Stack>
    </Box>
  );
};

export default DailyBriefVideoPlayer;

