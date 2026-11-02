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

const VideoPlayer = () => {
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
    return `${normalizedBasePath}/api/v1/materials/stream?path=${encodeURIComponent(materialPath)}`;
  }, [materialPath]);

  const handleBack = () => {
    if (window.history.length > 1) {
      navigate(-1);
      return;
    }
    navigate('/materials');
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
                {tr('Training Video Player', 'مشغل الفيديو التدريبي')}
              </Typography>
            </Stack>
            <Typography color="text.secondary" sx={{ lineHeight: 1.5 }}>
              {tr(
                'Play training videos directly from the material library with progressive streaming.',
                'شغّل فيديوهات التدريب مباشرة من مكتبة المواد مع بث تدريجي.'
              )}
            </Typography>
          </Stack>

          <Button variant="outlined" startIcon={<ArrowBack />} onClick={handleBack}>
            {tr('Back', 'رجوع')}
          </Button>
        </Stack>

        {!materialPath ? (
          <Alert severity="error">
            {tr(
              'No video path was provided. Please return to the material library and try again.',
              'لم يتم توفير مسار فيديو. برجاء العودة إلى مكتبة المواد والمحاولة مرة أخرى.'
            )}
          </Alert>
        ) : null}

        <Card>
          <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {tr('Video file', 'ملف الفيديو')}
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
                {videoName || tr('Unnamed video', 'فيديو بدون اسم')}
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
              {materialPath || tr('No relative path available.', 'لا يوجد مسار نسبي متاح.')}
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
                        'تعذر تحميل الفيديو. برجاء تحديث الصفحة أو المحاولة لاحقاً.'
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
                      {tr('Preparing video stream...', 'جارٍ تجهيز بث الفيديو...')}
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

export default VideoPlayer;
