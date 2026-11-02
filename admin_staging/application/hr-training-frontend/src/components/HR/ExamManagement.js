import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { alpha, useTheme } from '@mui/material/styles';
import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { Add } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { examService } from '../../services/auth';
import { useLanguage } from '../../context/LanguageContext';
import ExamLevelBoard from './exams/ExamLevelBoard';

const formatDateTime = (value, locale) => {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '-';
  return parsed.toLocaleString(locale, {
    timeZone: 'Africa/Cairo',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const ExamManagement = () => {
  const navigate = useNavigate();
  const theme = useTheme();
  const { t, isArabic } = useLanguage();
  const tr = useCallback((en, ar) => t(en, ar), [t]);

  const [exams, setExams] = useState([]);
  const [alert, setAlert] = useState({ show: false, message: '', severity: 'success' });
  const [sortConfig, setSortConfig] = useState({ key: 'created_on', direction: 'desc' });
  const [sendingMailExamId, setSendingMailExamId] = useState(null);
  const [regeneratingExamId, setRegeneratingExamId] = useState(null);
  const [movingExamId, setMovingExamId] = useState(null);

  useEffect(() => {
    loadExams();
  }, []);

  const loadExams = async () => {
    try {
      const response = await examService.getAllExams();
      setExams(response.data.exams || []);
    } catch (error) {
      console.error('Error loading exams:', error);
      setAlert({
        show: true,
        message: tr('Failed to load exams', 'فشل تحميل الاختبارات'),
        severity: 'error',
      });
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'Open':
        return 'success';
      case 'Closed':
        return 'error';
      default:
        return 'warning';
    }
  };

  const statusLabel = (status) => {
    if (status === 'Open') return tr('Open', 'مفتوح');
    if (status === 'Closed') return tr('Closed', 'مغلق');
    return tr('On Hold', 'معلق');
  };

  const getSortableValue = (exam, key) => {
    switch (key) {
      case 'title':
        return exam.title || '';
      case 'exam_status':
        return exam.exam_status || '';
      case 'duration_minutes':
        return Number(exam.duration_minutes || 0);
      case 'start_date': {
        const ts = Date.parse(exam.start_date || '');
        return Number.isNaN(ts) ? null : ts;
      }
      case 'end_date': {
        const ts = Date.parse(exam.end_date || '');
        return Number.isNaN(ts) ? null : ts;
      }
      case 'created_on': {
        const ts = Date.parse(exam.created_on || exam.created_at || '');
        return Number.isNaN(ts) ? null : ts;
      }
      default:
        return '';
    }
  };

  const sortedExams = useMemo(() => {
    const locale = isArabic ? 'ar' : 'en';
    const rows = [...exams];
    const { key, direction } = sortConfig;

    rows.sort((a, b) => {
      const left = getSortableValue(a, key);
      const right = getSortableValue(b, key);

      const leftMissing = left === null || left === undefined || left === '';
      const rightMissing = right === null || right === undefined || right === '';
      if (leftMissing && rightMissing) return 0;
      if (leftMissing) return 1;
      if (rightMissing) return -1;

      let comparison;
      if (typeof left === 'number' && typeof right === 'number') {
        comparison = left - right;
      } else {
        comparison = String(left).localeCompare(String(right), locale, {
          sensitivity: 'base',
          numeric: true,
        });
      }
      return direction === 'asc' ? comparison : -comparison;
    });

    return rows;
  }, [exams, isArabic, sortConfig]);

  const sortableColumns = useMemo(
    () => [
      { key: 'title', label: tr('Title', 'العنوان') },
      { key: 'exam_status', label: tr('Status', 'الحالة') },
      { key: 'duration_minutes', label: tr('Duration', 'المدة') },
      { key: 'start_date', label: tr('Start Date', 'تاريخ البداية') },
      { key: 'end_date', label: tr('End Date', 'تاريخ النهاية') },
      { key: 'created_on', label: tr('Created On', 'تاريخ الإنشاء') },
    ],
    [tr]
  );

  const handleSort = (key) => {
    setSortConfig((prev) => {
      if (prev.key === key) {
        return { key, direction: prev.direction === 'asc' ? 'desc' : 'asc' };
      }
      return { key, direction: 'asc' };
    });
  };

  const handleDelete = async (examId) => {
    if (!window.confirm(tr('Are you sure you want to delete this exam?', 'هل أنت متأكد من حذف هذا الاختبار؟'))) {
      return;
    }

    try {
      await examService.deleteExam(examId, false);
      setAlert({
        show: true,
        message: tr('Exam deleted successfully!', 'تم حذف الاختبار بنجاح!'),
        severity: 'success',
      });
      await loadExams();
    } catch (error) {
      setAlert({
        show: true,
        message: tr('Delete failed', 'فشل الحذف'),
        severity: 'error',
      });
    }
  };

  const handleSendMail = async (examId) => {
    try {
      setSendingMailExamId(examId);
      const response = await examService.sendExamMail(examId);
      const queuedCount = Number(response.data?.notification_recipients_queued || 0);
      setAlert({
        show: true,
        message:
          response.data?.signal ||
          (queuedCount > 0
            ? tr('Exam mail queued successfully.', 'تم تجهيز رسائل الاختبار بنجاح.')
            : tr('No audience members with valid email addresses were found.', 'لم يتم العثور على مستلمين صالحين للبريد.')),
        severity: queuedCount > 0 ? 'success' : 'warning',
      });
    } catch (error) {
      setAlert({
        show: true,
        message: error.response?.data?.signal || tr('Failed to send mail', 'فشل إرسال البريد'),
        severity: 'error',
      });
    } finally {
      setSendingMailExamId(null);
    }
  };

  const handleRegenerateExam = async (exam) => {
    const confirmed = window.confirm(
      tr(
        `Create a regenerated copy of "${exam.title}" with the same questions, materials, and audience, but without previous attempts or submitted answers?`,
        `هل تريد إنشاء نسخة مُعاد توليدها من "${exam.title}" بنفس الأسئلة والمواد والجمهور، ولكن بدون أي محاولات سابقة أو إجابات مُرسلة؟`
      )
    );
    if (!confirmed) {
      return;
    }

    try {
      setRegeneratingExamId(exam.exam_id);
      const response = await examService.regenerateExam(exam.exam_id);
      const skippedMaterialCount = Number(response.data?.skipped_material_count || 0);
      setAlert({
        show: true,
        message:
          skippedMaterialCount > 0
            ? tr(
                `Exam regenerated successfully. ${skippedMaterialCount} deleted materials were skipped from the new copy. Review the new exam dates before sending mail.`,
                `تمت إعادة توليد الاختبار بنجاح. تم تخطي ${skippedMaterialCount} من المواد المحذوفة من النسخة الجديدة. راجع مواعيد الاختبار الجديد قبل إرسال البريد.`
              )
            : tr(
                'Exam regenerated successfully. The new copy keeps the same setup without previous attempts or submitted answers. Review the new exam dates before sending mail.',
                'تمت إعادة توليد الاختبار بنجاح. النسخة الجديدة تحتفظ بنفس الإعدادات بدون المحاولات السابقة أو الإجابات المرسلة. راجع مواعيد الاختبار الجديد قبل إرسال البريد.'
              ),
        severity: 'success',
      });
      await loadExams();
    } catch (error) {
      setAlert({
        show: true,
        message:
          error.response?.data?.signal ||
          tr('Failed to regenerate exam', 'فشل في إعادة توليد الاختبار'),
        severity: 'error',
      });
    } finally {
      setRegeneratingExamId(null);
    }
  };

  const handleMoveExamLevel = async (examId, nextLevel) => {
    const currentExam = exams.find((exam) => exam.exam_id === examId);
    if (!nextLevel || currentExam?.exam_level === nextLevel) {
      return;
    }

    try {
      setMovingExamId(examId);
      await examService.updateExamLevel(examId, { exam_level: nextLevel });
      setExams((previous) =>
        previous.map((exam) =>
          exam.exam_id === examId ? { ...exam, exam_level: nextLevel } : exam
        )
      );
      setAlert({
        show: true,
        message: tr('Exam level updated successfully.', 'تم تحديث مستوى الاختبار بنجاح.'),
        severity: 'success',
      });
    } catch (error) {
      setAlert({
        show: true,
        message:
          error.response?.data?.signal ||
          tr('Failed to move exam level', 'فشل نقل مستوى الاختبار'),
        severity: 'error',
      });
    } finally {
      setMovingExamId(null);
    }
  };

  const handleOpenExam = (exam) => {
    navigate(`/hr/exams/${exam.exam_id}`);
  };

  const handleOpenEdit = (exam) => {
    navigate(`/hr/exams/edit/${exam.exam_id}`);
  };

  return (
    <Box sx={{ direction: isArabic ? 'rtl' : 'ltr' }}>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        justifyContent="space-between"
        alignItems={{ xs: 'flex-start', md: 'center' }}
        spacing={2}
        sx={{ mb: 3 }}
      >
        <Box>
          <Typography variant="h4" fontWeight={800} sx={{ color: 'text.primary', mb: 0.5 }}>
            {tr('Exam Management', 'إدارة الاختبارات')}
          </Typography>
          <Typography variant="body1" color="text.secondary">
            {tr(
              'Browse exams by level in collapsible sections, then open the full filtered table when you need all actions.',
              'استعرض الاختبارات حسب المستوى داخل أقسام قابلة للطي، ثم افتح الجدول المفلتر الكامل عند الحاجة إلى كل الإجراءات.'
            )}
          </Typography>
        </Box>

        <Button
          variant="contained"
          startIcon={<Add />}
          onClick={() => navigate('/hr/exams/create')}
          sx={{ alignSelf: { xs: 'stretch', md: 'auto' } }}
        >
          {tr('Create Exam', 'إنشاء اختبار')}
        </Button>
      </Stack>

      {alert.show && (
        <Alert
          severity={alert.severity}
          sx={{
            mb: 3,
            borderRadius: 2,
            boxShadow: 'none',
            border: `1px solid ${alpha(theme.palette.secondary.main, 0.12)}`,
          }}
          onClose={() => setAlert((previous) => ({ ...previous, show: false }))}
        >
          {alert.message}
        </Alert>
      )}

      <ExamLevelBoard
        exams={sortedExams}
        tr={tr}
        isArabic={isArabic}
        sortableColumns={sortableColumns}
        sortConfig={sortConfig}
        onSort={handleSort}
        formatDateTime={formatDateTime}
        statusLabel={statusLabel}
        getStatusColor={getStatusColor}
        onMoveLevel={handleMoveExamLevel}
        onSendMail={handleSendMail}
        onRegenerate={handleRegenerateExam}
        onOpenExam={handleOpenExam}
        onOpenEdit={handleOpenEdit}
        onDelete={handleDelete}
        sendingMailExamId={sendingMailExamId}
        regeneratingExamId={regeneratingExamId}
        movingExamId={movingExamId}
      />
    </Box>
  );
};

export default ExamManagement;
