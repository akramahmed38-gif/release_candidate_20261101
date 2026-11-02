import React, { useState, useEffect, useCallback } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Typography,
} from '@mui/material';
import { AccessTime, CalendarMonth, Info, Refresh as RefreshIcon } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { examService } from '../../services/auth';
import { useLanguage } from '../../context/LanguageContext';

const statusToColor = (status = '') => {
  const normalized = status.toLowerCase();
  if (normalized === 'open' || normalized === 'مفتوح') return 'success';
  if (normalized === 'on hold' || normalized === 'مؤجل') return 'warning';
  if (normalized === 'closed' || normalized === 'مغلق') return 'default';
  return 'primary';
};

const formatDate = (value, locale) => {
  if (!value) return '-';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString(locale || undefined, {
        timeZone: 'Africa/Cairo',
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
};

const ExamList = () => {
  const navigate = useNavigate();
  const { t, isArabic } = useLanguage();
  const tr = (en, ar) => t(en, ar);
  const locale = isArabic ? 'ar-EG' : 'en-US';
  const [exams, setExams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadExams = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await examService.getStudentExams();
      setExams(response.data.exams || []);
    } catch (err) {
      setError(
        err.response?.data?.message ||
          err.response?.data?.detail ||
          tr('Failed to load your exams. Please try again.', 'تعذر تحميل اختباراتك. يرجى المحاولة مرة أخرى.')
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadExams();
  }, [loadExams]);

  const resolveStatusLabel = (status = '') => {
    const normalized = status.toLowerCase();
    if (normalized === 'open') return tr('Open', 'مفتوح');
    if (normalized === 'on hold') return tr('On hold', 'مؤجل');
    if (normalized === 'closed') return tr('Closed', 'مغلق');
    if (normalized === 'draft') return tr('Draft', 'مسودة');
    return status || tr('Unknown', 'غير معروف');
  };

  return (
    <Box sx={{ direction: isArabic ? 'rtl' : 'ltr', textAlign: isArabic ? 'right' : 'left' }}>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 2,
          mb: 3,
        }}
      >
        <Box>
          <Typography variant="h4" fontWeight="bold">
            {tr('My Exams', 'اختباراتي')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {tr('Only exams assigned to your HR ID are listed here.', 'يتم عرض الاختبارات المخصصة لرقمك الوظيفي فقط هنا.')}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={isArabic ? null : <Info />}
            endIcon={isArabic ? <Info /> : null}
            onClick={() => navigate('/employee/contact')}
          >
            {tr('Contact Us', 'تواصل معنا')}
          </Button>
          <Button
            variant="contained"
            color="primary"
            startIcon={isArabic ? null : <RefreshIcon />}
            endIcon={isArabic ? <RefreshIcon /> : null}
            onClick={loadExams}
          >
            {tr('Refresh', 'تحديث')}
          </Button>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}>
          <CircularProgress />
        </Box>
      ) : exams.length === 0 ? (
        <Card>
          <CardContent>
            <Typography variant="h6" fontWeight="bold" gutterBottom>
              {tr('No exams available', 'لا توجد اختبارات متاحة')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {tr(
                'When an exam is assigned to your HR ID it will appear here automatically.',
                'عند تخصيص اختبار لرقمك الوظيفي سيظهر هنا تلقائياً.'
              )}
            </Typography>
          </CardContent>
        </Card>
      ) : (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 420px))',
            gap: 3,
            justifyContent: isArabic ? 'end' : 'start',
            '@media (max-width: 480px)': {
              gridTemplateColumns: 'minmax(0, 1fr)',
            },
          }}
        >
          {exams.map((exam) => (
            <Box key={exam.exam_id} sx={{ width: '100%', maxWidth: 420 }}>
              <Card
                elevation={2}
                sx={{
                  width: '100%',
                  height: 480,
                  display: 'flex',
                  flexDirection: 'column',
                  overflow: 'hidden',
                  borderRadius: 3,
                  borderTop: '4px solid',
                  borderColor:
                    exam.exam_status?.toLowerCase() === 'open' ? 'success.main' : 'divider',
                  transition: 'transform 180ms ease, box-shadow 180ms ease',
                  '&:hover': {
                    transform: 'translateY(-4px)',
                    boxShadow: 7,
                  },
                }}
              >
                <CardContent sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', p: 2.5 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Chip
                      label={resolveStatusLabel(exam.exam_status)}
                      color={statusToColor(exam.exam_status)}
                      size="small"
                    />
                    <Typography variant="caption" color="text.secondary">
                      {tr('Duration', 'المدة')}: {exam.duration_minutes} {tr('mins', 'دقيقة')}
                    </Typography>
                  </Box>
                  <Typography
                    variant="h6"
                    fontWeight="bold"
                    sx={{
                      minHeight: 58,
                      display: '-webkit-box',
                      WebkitBoxOrient: 'vertical',
                      WebkitLineClamp: 2,
                      overflow: 'hidden',
                    }}
                    title={exam.title}
                  >
                    {exam.title}
                  </Typography>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{
                      minHeight: 60,
                      mb: 1.5,
                      display: '-webkit-box',
                      WebkitBoxOrient: 'vertical',
                      WebkitLineClamp: 3,
                      overflow: 'hidden',
                    }}
                    title={exam.description || ''}
                  >
                    {exam.description}
                  </Typography>

                  <Divider sx={{ my: 2 }} />

                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexDirection: isArabic ? 'row-reverse' : 'row' }}>
                      <CalendarMonth color="primary" fontSize="small" />
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          {tr('Starts', 'يبدأ')}
                        </Typography>
                        <Typography variant="body2" fontWeight={600}>
                          {formatDate(exam.start_date, locale)}
                        </Typography>
                      </Box>
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexDirection: isArabic ? 'row-reverse' : 'row' }}>
                      <CalendarMonth color="primary" fontSize="small" />
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          {tr('Ends', 'ينتهي')}
                        </Typography>
                        <Typography variant="body2" fontWeight={600}>
                          {formatDate(exam.end_date, locale)}
                        </Typography>
                      </Box>
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexDirection: isArabic ? 'row-reverse' : 'row' }}>
                      <AccessTime color="primary" fontSize="small" />
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          {tr('Materials', 'المواد')}
                        </Typography>
                        <Typography variant="body2" fontWeight={600}>
                          {exam.materials?.length || 0} {tr('linked files', 'ملفات مرتبطة')}
                        </Typography>
                      </Box>
                    </Box>
                  </Box>
                </CardContent>
                <Box sx={{ p: 2.5, pt: 0 }}>
                  <Button
                    variant="contained"
                    fullWidth
                    onClick={() => navigate(`/employee/exams/${exam.exam_id}`)}
                  >
                    {tr('View Details', 'عرض التفاصيل')}
                  </Button>
                </Box>
              </Card>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
};

export default ExamList;
