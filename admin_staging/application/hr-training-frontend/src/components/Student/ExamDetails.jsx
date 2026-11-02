import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  FormControlLabel,
  Checkbox,
  Grid,
  IconButton,
  LinearProgress,
  Paper,
  Radio,
  RadioGroup,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { ArrowBack, AccessTime, CalendarToday, Download, ExpandMore, Repeat } from '@mui/icons-material';
import { useNavigate, useParams } from 'react-router-dom';
import { examService, authService } from '../../services/auth';
import { broadcastExamChatLockState } from '../../utils/examChatLock';
import { useLanguage } from '../../context/LanguageContext';

const parseDateSafe = (value) => {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const formatRemainingTime = (totalSeconds) => {
  if (typeof totalSeconds !== 'number' || totalSeconds < 0) return '00:00';
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
};

const formatFullDateTime = (value, locale) => {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(locale || undefined, {
    timeZone: 'Africa/Cairo',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const formatNumber = (value, options = {}, locale) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '-';
  }
  return Number(value).toLocaleString(locale || undefined, options);
};

const formatPercentageValue = (value, locale) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '-';
  }
  const formatted = Number(value).toLocaleString(locale || undefined, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  return `${formatted}%`;
};

const formatDurationFromSeconds = (seconds) => {
  if (seconds === null || seconds === undefined) return '-';
  const totalSeconds = Number(seconds);
  if (Number.isNaN(totalSeconds)) return '-';
  if (totalSeconds < 60) {
    return `${totalSeconds}s`;
  }
  const minutes = Math.floor(totalSeconds / 60);
  const remaining = totalSeconds % 60;
  return remaining ? `${minutes}m ${remaining}s` : `${minutes}m`;
};

const formatScoreDisplay = (score, maxScore, locale) => {
  if (score === null || score === undefined) return '-';
  if (maxScore === null || maxScore === undefined) {
    return formatNumber(score, { maximumFractionDigits: 2, minimumFractionDigits: 0 }, locale);
  }
  return `${formatNumber(score, { maximumFractionDigits: 2, minimumFractionDigits: 0 }, locale)} / ${formatNumber(
    maxScore,
    { maximumFractionDigits: 2, minimumFractionDigits: 0 },
    locale
  )}`;
};

const DEFAULT_RETAIL_GROUP_NAME = 'General';

const ExamDetails = () => {
  const navigate = useNavigate();
  const { examId } = useParams();
  const { t, isArabic } = useLanguage();
  const tr = (en, ar) => t(en, ar);
  const locale = isArabic ? 'ar-EG' : 'en-US';
  const basePath = import.meta.env.VITE_BASENAME || '/training';
  const normalizedBasePath = basePath.startsWith('/') ? basePath : `/${basePath}`;
  const [exam, setExam] = useState(null);
  const [loading, setLoading] = useState(true);
  const [currentTime, setCurrentTime] = useState(() => new Date());
  const [isExamActive, setIsExamActive] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(null);
  const [attemptLocked, setAttemptLocked] = useState(false);
  const [examNotification, setExamNotification] = useState('');
  const [showQuestionFlow, setShowQuestionFlow] = useState(false);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [responses, setResponses] = useState({});
  const [submitStatus, setSubmitStatus] = useState({ show: false, severity: 'success', message: '' });
  const [justSubmitted, setJustSubmitted] = useState(false);
  const [startingExam, setStartingExam] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [resultsSummary, setResultsSummary] = useState(null);
  const [resultsDetails, setResultsDetails] = useState([]);
  const [participantsOverview, setParticipantsOverview] = useState([]);
  const [participantsPage, setParticipantsPage] = useState(0);
  const [participantsRowsPerPage, setParticipantsRowsPerPage] = useState(25);
  const [attemptSearchTerm, setAttemptSearchTerm] = useState('');
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resultsError, setResultsError] = useState('');
  const [downloadingExcel, setDownloadingExcel] = useState(false);
  const user = authService.getCurrentUser();
  const rawRole = (user?.role || user?.department || '').toLowerCase();
  const normalizedRole = rawRole === 'employee' ? 'retail' : rawRole;
  const isRetailView = normalizedRole === 'retail';
  const timerRef = useRef(null);
  const participantStatusColorMap = {
    passed: 'success',
    attempted: 'warning',
    pending: 'default',
  };
  const participantStatusLabelMap = {
    passed: tr('Passed', 'ناجح'),
    attempted: tr('Attempted', 'تمت المحاولة'),
    pending: tr('Not Attempted', 'لم تتم المحاولة'),
  };
  const canonicalParticipantStatusColorMap = {
    not_attempted: 'default',
    in_progress: 'info',
    submitted: 'secondary',
    passed: 'success',
    failed: 'warning',
  };
  const canonicalParticipantStatusLabelMap = {
    not_attempted: tr('Not Attempted', 'لم تتم المحاولة'),
    in_progress: tr('In Progress', 'جارٍ التنفيذ'),
    submitted: tr('Submitted', 'تم الإرسال'),
    passed: tr('Passed', 'ناجح'),
    failed: tr('Failed', 'راسب'),
  };
  const baseQuestions = Array.isArray(exam?.questions) ? exam.questions : [];
  const questionOrder = isRetailView ? exam?.session_state?.question_order : null;
  const questions = Array.isArray(questionOrder) && questionOrder.length === baseQuestions.length
    ? [...baseQuestions].sort((left, right) => questionOrder.indexOf(left.question_id) - questionOrder.indexOf(right.question_id))
    : baseQuestions;
  const resolveQuestionGroupName = (question) =>
    (question?.question_group || '').trim() || tr(DEFAULT_RETAIL_GROUP_NAME, 'عام');
  const sessionIdentity =
    user?.hrid || user?.hr_id || user?.employee_id || user?.email || 'employee';
  const examSessionStorageKey = examId ? `exam_session_${examId}_${sessionIdentity}` : null;
  const [storedSession, setStoredSession] = useState(null);
  useEffect(() => {
    if (participantsRowsPerPage === -1) {
      setParticipantsPage(0);
      return;
    }
    const maxPage = Math.max(Math.ceil(participantsOverview.length / participantsRowsPerPage) - 1, 0);
    if (participantsPage > maxPage) {
      setParticipantsPage(maxPage);
    }
  }, [participantsOverview.length, participantsRowsPerPage, participantsPage]);

  const persistSessionToStorage = useCallback(
    (session) => {
      if (typeof window === 'undefined' || !examSessionStorageKey) {
        return;
      }
      try {
        if (!session) {
          window.localStorage.removeItem(examSessionStorageKey);
        } else {
          window.localStorage.setItem(examSessionStorageKey, JSON.stringify(session));
        }
        broadcastExamChatLockState();
      } catch (error) {
        console.error('Failed to persist exam session state', error);
      }
    },
    [examSessionStorageKey]
  );

  const readSessionFromStorage = useCallback(() => {
    if (typeof window === 'undefined' || !examSessionStorageKey) {
      return null;
    }
    try {
      const raw = window.localStorage.getItem(examSessionStorageKey);
      return raw ? JSON.parse(raw) : null;
    } catch (error) {
      console.error('Failed to parse stored exam session', error);
      return null;
    }
  }, [examSessionStorageKey]);

  const updateStoredSession = useCallback(
    (updater) => {
      setStoredSession((prev) => {
        const computed = typeof updater === 'function' ? updater(prev) : updater;
        const next = computed ?? null;
        persistSessionToStorage(next);
        return next;
      });
    },
    [persistSessionToStorage]
  );

  const syncSessionProgress = useCallback(
    (partial) => {
      if (!isRetailView || !partial) {
        return;
      }
      updateStoredSession((prev) => {
        if (!prev || prev.status !== 'in-progress') {
          return prev;
        }
        return { ...prev, ...partial };
      });
    },
    [isRetailView, updateStoredSession]
  );

  const markSessionCompleted = useCallback(
    (message, incrementAttempts = true) => {
      if (!isRetailView) {
        return;
      }
      updateStoredSession((prev) => ({
        ...(prev || {}),
        status: 'completed',
        completedAt: new Date().toISOString(),
        completedMessage: message || tr('Exam submitted successfully.', 'تم إرسال الاختبار بنجاح.'),
        attempts_used: incrementAttempts ? (prev?.attempts_used || 0) + 1 : (prev?.attempts_used || 0),
      }));
    },
    [isRetailView, tr, updateStoredSession]
  );

  const markSessionExpired = useCallback(
    (message) => {
      if (!isRetailView) {
        return;
      }
      updateStoredSession((prev) => ({
        ...(prev || {}),
        status: 'expired',
        completedAt: new Date().toISOString(),
        completedMessage: message || tr('Your exam session has ended.', 'انتهت جلسة الاختبار الخاصة بك.'),
      }));
    },
    [isRetailView, tr, updateStoredSession]
  );

  const backPath = isRetailView ? '/employee/exams' : '/hr/exams';
  const handleBack = () => {
    if (isRetailView) {
      window.location.assign(`${normalizedBasePath}${backPath}`);
      return;
    }
    navigate(backPath);
  };
  const formatAudienceMode = (mode) => {
    switch (mode) {
      case 'filters':
        return 'Filtered Audience';
      case 'manual':
        return 'Manual HR IDs';
      case 'all':
        return 'All Employees';
      default:
        return 'Not Configured';
    }
  };

  const loadExam = useCallback(async () => {
    try {
      const response = await examService.getExamById(examId);
      setExam(response.data.exam);
    } catch (error) {
      console.error('Error loading exam:', error);
    } finally {
      setLoading(false);
    }
  }, [examId]);

  const loadExamResults = useCallback(async () => {
    if (isRetailView) {
      return;
    }
    setResultsLoading(true);
    setResultsError('');
    try {
      const response = await examService.getExamResultsDetails(examId);
      const payload = response.data || {};
      setResultsSummary(payload.results_summary || null);
      setResultsDetails(Array.isArray(payload.results_details) ? payload.results_details : []);
      setParticipantsOverview(Array.isArray(payload.participants_overview) ? payload.participants_overview : []);
    } catch (error) {
      console.error('Error loading exam results:', error);
      setResultsError(error.response?.data?.message || 'Unable to load exam performance insights.');
    } finally {
      setResultsLoading(false);
    }
  }, [examId, isRetailView]);

  const handleDownloadExamResults = async () => {
    if (downloadingExcel) return;
    setDownloadingExcel(true);
    try {
      const response = await examService.downloadExamResultsExcel(examId);
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const timestamp = new Date().toISOString().split('T')[0];
      link.download = `${exam?.title || 'exam'}_${timestamp}_analytics.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to download analytics workbook', error);
      setResultsError('Unable to download the analytics workbook. Please try again.');
    } finally {
      setDownloadingExcel(false);
    }
  };

  useEffect(() => {
    loadExam();
  }, [loadExam]);

  useEffect(() => {
    if (!isRetailView) {
      setStoredSession(null);
      return;
    }
    if (!exam) {
      return;
    }
    const restored = readSessionFromStorage();
    const serverSession = exam.session_state || null;

    if (serverSession?.status === 'in_progress') {
      const previousAttemptId = restored?.attemptId || restored?.attempt_id || null;
      const sameAttempt = previousAttemptId && previousAttemptId === serverSession.attempt_id;
      const nextSession = {
        status: 'in-progress',
        attemptId: serverSession.attempt_id,
        startedAt: serverSession.started_at,
        expiresAt: serverSession.expires_at,
        attempts_used: serverSession.attempts_used,
        responses: sameAttempt ? restored?.responses || {} : {},
        currentQuestionIndex: sameAttempt ? restored?.currentQuestionIndex || 0 : 0,
      };
      persistSessionToStorage(nextSession);
      setStoredSession(nextSession);
      return;
    }

    if (serverSession?.status === 'expired') {
      const expiredSession = {
        ...(restored || {}),
        status: 'expired',
        attemptId: serverSession.attempt_id,
        startedAt: serverSession.started_at,
        expiresAt: serverSession.expires_at,
        attempts_used: serverSession.attempts_used,
        completedAt: serverSession.expires_at || new Date().toISOString(),
        completedMessage:
          serverSession.message ||
          tr('Your exam session has expired.', 'انتهت جلسة الاختبار الخاصة بك.'),
        responses: {},
        currentQuestionIndex: 0,
      };
      persistSessionToStorage(expiredSession);
      setStoredSession(expiredSession);
      return;
    }

    if (restored?.status === 'in-progress') {
      persistSessionToStorage(null);
      setStoredSession(null);
      return;
    }

    setStoredSession(restored);
  }, [exam, isRetailView, persistSessionToStorage, readSessionFromStorage, tr]);

  useEffect(() => {
    if (isRetailView) {
      setResultsSummary(null);
      setResultsDetails([]);
      setParticipantsOverview([]);
      setResultsError('');
      setResultsLoading(false);
      return;
    }
    loadExamResults();
  }, [isRetailView, loadExamResults]);

  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setResultsSummary(null);
    setResultsDetails([]);
    setParticipantsOverview([]);
    setResultsError('');
    setResultsLoading(false);
    setIsExamActive(false);
    setAttemptLocked(false);
    setExamNotification('');
    setRemainingSeconds(null);
    setShowQuestionFlow(false);
    setCurrentQuestionIndex(0);
    setResponses({});
    setStartingExam(false);
    setJustSubmitted(false);
    setSubmitStatus({ show: false, severity: 'success', message: '' });
    setStoredSession(null);
  }, [examId]);

  useEffect(() => {
    const tick = setInterval(() => setCurrentTime(new Date()), 30000);
    return () => clearInterval(tick);
  }, []);

  useEffect(() => {
    if (!isRetailView) {
      return;
    }
    const successMessage = String(submitStatus.message || '');
    const submittedNow =
      submitStatus.show &&
      submitStatus.severity === 'success' &&
      !showQuestionFlow &&
      !isExamActive &&
      remainingSeconds === 0 &&
      (successMessage.includes('close this page') || successMessage.includes('إغلاق هذه الصفحة'));
    if (submittedNow) {
      setJustSubmitted(true);
    }
  }, [isRetailView, submitStatus, showQuestionFlow, isExamActive, remainingSeconds]);

  const handleExamTimeout = useCallback(
    (message) => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setIsExamActive(false);
      setAttemptLocked(true);
      setRemainingSeconds(0);
      setExamNotification(message);
      setShowQuestionFlow(false);
      setJustSubmitted(false);
      markSessionExpired(message);
    },
    [markSessionExpired]
  );

  useEffect(() => {
    if (!isExamActive) {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return undefined;
    }
    const scheduleEndMs = exam?.end_date ? new Date(exam.end_date).getTime() : null;
    timerRef.current = setInterval(() => {
      setRemainingSeconds((prev) => {
        if (prev === null) return prev;
        if (scheduleEndMs && Date.now() >= scheduleEndMs) {
          handleExamTimeout(
            tr('Exam window closed because the end date was reached.', 'تم إغلاق نافذة الاختبار بسبب انتهاء التاريخ.')
          );
          return 0;
        }
        if (prev <= 1) {
          handleExamTimeout(tr('Time is up! The exam has been closed automatically.', 'انتهى الوقت! تم إغلاق الاختبار تلقائياً.'));
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isExamActive, exam?.end_date, handleExamTimeout]);

  useEffect(() => {
    if (!isRetailView || !exam || !storedSession) {
      return;
    }
    if (storedSession.status === 'completed' || storedSession.status === 'expired') {
      const maxAttempts = Math.max(1, Number(exam?.number_of_attempts_allowed || 1));
      const attemptsUsed = Number.isFinite(Number(exam?.attempts_used))
        ? Number(exam.attempts_used)
        : Math.max(0, Number(storedSession?.attempts_used || 0));
      const attemptsLeftFromApi = Number.isFinite(Number(exam?.attempts_left))
        ? Math.max(0, Number(exam.attempts_left))
        : null;
      const attemptsRemaining =
        attemptsLeftFromApi !== null ? attemptsLeftFromApi : Math.max(0, maxAttempts - attemptsUsed);
      const shouldLock = attemptsRemaining <= 0;
      setIsExamActive(false);
      setShowQuestionFlow(false);
      setRemainingSeconds(null);
      setAttemptLocked(shouldLock);
      const defaultMessage =
        storedSession.status === 'completed'
          ? tr('You have already submitted this exam.', 'لقد قمت بإرسال هذا الاختبار بالفعل.')
          : tr('Your previous exam session has expired.', 'انتهت جلسة الاختبار السابقة.');
      setExamNotification(storedSession.completedMessage || defaultMessage);
      setSubmitStatus({
        show: true,
        severity: storedSession.status === 'completed' ? 'success' : 'warning',
        message: storedSession.completedMessage || defaultMessage,
      });
      return;
    }
    if (storedSession.status === 'in-progress') {
      if (isExamActive) {
        return;
      }
      const expiresMs = Date.parse(storedSession.expiresAt || '');
      if (!Number.isFinite(expiresMs)) {
        updateStoredSession(null);
        return;
      }
      const remaining = Math.floor((expiresMs - Date.now()) / 1000);
      if (remaining <= 0) {
        markSessionExpired(tr('Your exam session has expired.', 'انتهت جلسة الاختبار الخاصة بك.'));
        handleExamTimeout(tr('Your exam session has expired.', 'انتهت جلسة الاختبار الخاصة بك.'));
        return;
      }
      setResponses(storedSession.responses || {});
      const restoredIndex = Math.min(
        storedSession.currentQuestionIndex || 0,
        Math.max(questions.length - 1, 0)
      );
      setCurrentQuestionIndex(restoredIndex);
      setShowQuestionFlow(questions.length > 0);
      setIsExamActive(true);
      setAttemptLocked(false);
      setRemainingSeconds(remaining);
      setExamNotification(tr('Exam session restored. Continue where you left off.', 'تم استعادة جلسة الاختبار. أكمل من حيث توقفت.'));
    }
  }, [
    storedSession,
    exam,
    isRetailView,
    isExamActive,
    questions.length,
    handleExamTimeout,
    markSessionExpired,
    updateStoredSession,
  ]);

  if (loading) return <Typography>{tr('Loading...', 'جارٍ التحميل...')}</Typography>;
  if (!exam) return <Typography>{tr('Exam not found', 'لم يتم العثور على الاختبار')}</Typography>;

  const startDateMs = parseDateSafe(exam.start_date)?.getTime() ?? null;
  const endDateMs = parseDateSafe(exam.end_date)?.getTime() ?? null;
  const nowMs = currentTime.getTime();
  const hasStarted = startDateMs ? nowMs >= startDateMs : false;
  const hasEnded = endDateMs ? nowMs >= endDateMs : false;
  const examStatusLower = (exam.exam_status || '').toLowerCase();
  const isExamMarkedOpen = examStatusLower === 'open';
  const scheduleAllowsStart = Boolean(startDateMs && hasStarted && !hasEnded);
  const sessionStatus = storedSession?.status;
  const sessionCompleted = sessionStatus === 'completed';
  const sessionExpired = sessionStatus === 'expired';
  const sessionInProgress = sessionStatus === 'in-progress';
  const maxAttempts = Math.max(1, Number(exam.number_of_attempts_allowed || 1));
  const attemptsUsed = Number.isFinite(Number(exam.attempts_used))
    ? Number(exam.attempts_used)
    : Math.max(0, Number(storedSession?.attempts_used || 0));
  const attemptsLeftFromApi = Number.isFinite(Number(exam.attempts_left))
    ? Math.max(0, Number(exam.attempts_left))
    : null;
  const attemptsRemaining = Math.max(0, maxAttempts - attemptsUsed);
  const attemptsRemainingDisplay =
    attemptsLeftFromApi !== null ? attemptsLeftFromApi : attemptsRemaining;
  const attemptsExhausted = attemptsRemaining <= 0;
  const canStartAnotherAttempt = (sessionCompleted || sessionExpired) && !attemptsExhausted;
  const formatExamStatusLabel = (statusValue) => {
    const normalized = (statusValue || '').toLowerCase();
    if (normalized === 'open') return tr('Open', 'مفتوح');
    if (normalized === 'closed') return tr('Closed', 'مغلق');
    if (normalized === 'on hold') return tr('On hold', 'مؤجل');
    if (normalized === 'draft') return tr('Draft', 'مسودة');
    if (normalized === 'archived') return tr('Archived', 'مؤرشف');
    return statusValue || tr('Unknown', 'غير معروف');
  };
  const examStatusLabel = formatExamStatusLabel(exam.exam_status);
  const startButtonDisabled =
    !isRetailView ||
    !isExamMarkedOpen ||
    !scheduleAllowsStart ||
    isExamActive ||
    startingExam ||
    attemptLocked ||
    (!sessionInProgress && attemptsExhausted) ||
    sessionInProgress;
  const startButtonLabel = sessionCompleted
    ? tr('Exam Submitted', 'تم إرسال الاختبار')
    : sessionExpired
    ? tr('Session Locked', 'الجلسة مقفلة')
    : isExamActive
    ? tr('Exam In Progress', 'الاختبار جارٍ')
    : attemptLocked
    ? tr('Exam Closed', 'تم إغلاق الاختبار')
    : sessionInProgress
    ? tr('Resuming...', 'جارٍ الاستئناف...')
    : tr('Start Exam', 'بدء الاختبار');

  const resolvedStartButtonDisabled =
    !isRetailView ||
    !isExamMarkedOpen ||
    !scheduleAllowsStart ||
    isExamActive ||
    startingExam ||
    attemptLocked ||
    (!sessionInProgress && attemptsExhausted) ||
    sessionInProgress;
  const resolvedStartButtonLabel = startingExam
    ? tr('Starting...', 'جارٍ البدء...')
    : canStartAnotherAttempt
    ? tr('Start New Attempt', 'ابدأ محاولة جديدة')
    : startButtonLabel;

  let availabilityMessage = '';
  if (!isRetailView) {
    availabilityMessage = tr('Only employee accounts can take exams.', 'حسابات الموظفين فقط يمكنها أداء الاختبارات.');
  } else if (attemptsExhausted && (sessionCompleted || sessionExpired)) {
    availabilityMessage = tr('You have used all attempts for this exam.', 'لقد استخدمت جميع المحاولات لهذا الاختبار.');
  } else if (sessionCompleted) {
    availabilityMessage = tr('You can start another attempt.', 'يمكنك بدء محاولة أخرى.');
  } else if (sessionExpired) {
    availabilityMessage = tr(
      'Your previous exam session expired. You can start another attempt.',
      'انتهت جلسة الاختبار السابقة. يمكنك بدء محاولة أخرى.'
    );
  } else if (sessionInProgress) {
    availabilityMessage = tr(
      'Restoring your previous attempt. Please continue where you left off.',
      'جارٍ استعادة محاولتك السابقة. أكمل من حيث توقفت.'
    );
  } else if (!startDateMs) {
    availabilityMessage = tr('Exam start date is not scheduled yet.', 'لم يتم تحديد تاريخ بدء الاختبار بعد.');
  } else if (!hasStarted) {
    availabilityMessage =
      tr('Exam opens on', 'يفتح الاختبار في') + ` ${formatFullDateTime(exam.start_date, locale)}.`;
  } else if (hasEnded) {
    availabilityMessage = tr('Exam window has closed.', 'انتهت نافذة الاختبار.');
  } else if (!isExamMarkedOpen) {
    availabilityMessage =
      tr('This exam is currently', 'هذا الاختبار حالياً') + ` ${examStatusLabel}.`;
  } else if (attemptLocked) {
    availabilityMessage = tr('Your exam attempt has ended.', 'انتهت محاولتك للاختبار.');
  } else if (isExamActive) {
    availabilityMessage = tr('Exam session in progress.', 'جلسة الاختبار جارية.');
  } else {
    availabilityMessage = tr('You can start the exam now.', 'يمكنك بدء الاختبار الآن.');
  }

  if (attemptsExhausted && !sessionInProgress) {
    availabilityMessage = tr('You have used all attempts for this exam.', 'لقد استخدمت جميع المحاولات لهذا الاختبار.');
  }

  const summaryCards = [
    {
      label: 'Assigned Employees',
      value: formatNumber(resultsSummary?.employees_assigned),
      helper: 'Eligible audience',
    },
    {
      label: 'Attempted',
      value: formatNumber(resultsSummary?.employees_attempted),
      helper: `${formatPercentageValue(resultsSummary?.attempt_rate_percentage)} attempt rate`,
    },
    {
      label: 'Pass Rate',
      value: formatPercentageValue(resultsSummary?.pass_rate_percentage),
      helper: `${formatNumber(resultsSummary?.total_passed)} passed`,
    },
    {
      label: 'Average Score',
      value: formatPercentageValue(resultsSummary?.average_score_percentage),
      helper: `${formatNumber(resultsSummary?.total_attempts)} attempts`,
    },
    {
      label: 'Average Duration',
      value: resultsSummary?.average_duration_seconds
        ? formatDurationFromSeconds(resultsSummary?.average_duration_seconds)
        : '-',
      helper: 'Per attempt',
    },
    {
      label: 'Max Possible Score',
      value: formatNumber(resultsSummary?.max_possible_score, {
        maximumFractionDigits: 2,
        minimumFractionDigits: 0,
      }),
      helper: `${resultsSummary?.questions_count || 0} questions`,
    },
  ];

  const normalizedAttemptSearchTerm = attemptSearchTerm.trim().toLocaleLowerCase(locale);
  const filteredResultsDetails = normalizedAttemptSearchTerm
    ? resultsDetails.filter((attempt) => {
        const employeeName = String(attempt.employee_name || '').toLocaleLowerCase(locale);
        const employeeHrId = String(attempt.employee_hr_id || '').toLocaleLowerCase(locale);
        return (
          employeeName.includes(normalizedAttemptSearchTerm) ||
          employeeHrId.includes(normalizedAttemptSearchTerm)
        );
      })
    : resultsDetails;
  const attemptsToDisplay = filteredResultsDetails.slice(0, 8);
  const hasMoreAttempts = filteredResultsDetails.length > attemptsToDisplay.length;
  const topPerformer = resultsSummary?.top_performer;
  const hasResultsData =
    Boolean(resultsSummary && (resultsSummary.total_attempts || resultsSummary.employees_assigned)) ||
    participantsOverview.length > 0 ||
    resultsDetails.length > 0;
  const participantsToDisplay =
    participantsRowsPerPage === -1
      ? participantsOverview
      : participantsOverview.slice(
          participantsPage * participantsRowsPerPage,
          participantsPage * participantsRowsPerPage + participantsRowsPerPage
        );

  const isQuestionAnswered = (question) => {
    if (!question) return false;
    const answer = responses[question.question_id];
    if (question.question_type === 'Essay') {
      return typeof answer === 'string' && answer.trim().length > 0;
    }
    if (question.question_type === 'MCQ') {
      return Array.isArray(answer) ? answer.length > 0 : Boolean(answer);
    }
    return Boolean(answer);
  };

  const handleStartExam = () => {
    if (startButtonDisabled) return;
    const durationSeconds = Math.max(1, Number(exam.duration_minutes || 0) * 60 * 2);
    const now = new Date();
    const newSession = {
      status: 'in-progress',
      startedAt: now.toISOString(),
      expiresAt: new Date(now.getTime() + durationSeconds * 1000).toISOString(),
      attempts_used: attemptsUsed,
      responses: {},
      currentQuestionIndex: 0,
    };
    updateStoredSession(newSession);
    setAttemptLocked(false);
    setJustSubmitted(false);
    setExamNotification('');
    setResponses({});
    setCurrentQuestionIndex(0);
    setShowQuestionFlow(questions.length > 0);
    setSubmitStatus({ show: false, severity: 'success', message: '' });
    setRemainingSeconds(durationSeconds);
    setIsExamActive(true);
  };

  const handleStartExamRequest = async () => {
    if (resolvedStartButtonDisabled) return;

    setStartingExam(true);
    setJustSubmitted(false);
    setSubmitStatus({ show: false, severity: 'success', message: '' });

    try {
      const response = await examService.startExam(exam.exam_id);
      const session = response?.data?.session;
      if (!session?.attempt_id || !session?.expires_at) {
        throw new Error('Exam start response is missing session details.');
      }

      const previousAttemptId = storedSession?.attemptId || storedSession?.attempt_id || null;
      const sameAttempt = previousAttemptId && previousAttemptId === session.attempt_id;
      const nextSession = {
        status: 'in-progress',
        attemptId: session.attempt_id,
        startedAt: session.started_at,
        expiresAt: session.expires_at,
        attempts_used: session.attempts_used,
        responses: sameAttempt ? storedSession?.responses || {} : {},
        currentQuestionIndex: sameAttempt ? storedSession?.currentQuestionIndex || 0 : 0,
      };

      updateStoredSession(nextSession);
      setExam((prev) =>
        prev
          ? {
              ...prev,
              attempts_used: session.attempts_used,
              attempts_left: session.attempts_left,
              session_state: session,
            }
          : prev
      );
      setAttemptLocked(false);
      setExamNotification('');
      setResponses(nextSession.responses);
      setCurrentQuestionIndex(nextSession.currentQuestionIndex);
      setShowQuestionFlow(questions.length > 0);
      setRemainingSeconds(
        Number.isFinite(Number(session.remaining_seconds)) ? Math.max(0, Number(session.remaining_seconds)) : 0
      );
      setIsExamActive(true);
    } catch (error) {
      console.error('Failed to start exam', error);
      const serverMessage =
        error.response?.data?.message ||
        tr('Failed to start exam. Please try again.', 'فشل بدء الاختبار. يرجى المحاولة مرة أخرى.');
      if (error.response?.data?.attempts_used !== undefined || error.response?.data?.attempts_left !== undefined) {
        setExam((prev) =>
          prev
            ? {
                ...prev,
                attempts_used:
                  error.response?.data?.attempts_used !== undefined
                    ? error.response.data.attempts_used
                    : prev.attempts_used,
                attempts_left:
                  error.response?.data?.attempts_left !== undefined
                    ? error.response.data.attempts_left
                    : prev.attempts_left,
              }
            : prev
        );
      }
      setSubmitStatus({
        show: true,
        severity: 'error',
        message: serverMessage,
      });
      setExamNotification(serverMessage);
    } finally {
      setStartingExam(false);
    }
  };

  const handleParticipantsPageChange = (_event, newPage) => {
    if (participantsRowsPerPage === -1) {
      return;
    }
    setParticipantsPage(newPage);
  };

  const handleParticipantsRowsPerPageChange = (event) => {
    const nextValue = parseInt(event.target.value, 10);
    setParticipantsRowsPerPage(nextValue);
    setParticipantsPage(0);
  };

  const handleSelectChoice = (questionId, choiceId, checked, questionType) => {
    setResponses((prev) => {
      let nextAnswer;
      if (questionType === 'MCQ') {
        const current = prev[questionId];
        const list = Array.isArray(current) ? current : current ? [current] : [];
        nextAnswer = checked
          ? Array.from(new Set([...list, choiceId]))
          : list.filter((id) => id !== choiceId);
      } else {
        nextAnswer = choiceId;
      }
      const updated = {
        ...prev,
        [questionId]: nextAnswer,
      };
      syncSessionProgress({ responses: updated });
      return updated;
    });
  };

  const handleEssayChange = (questionId, value) => {
    setResponses((prev) => {
      const updated = {
        ...prev,
        [questionId]: value,
      };
      syncSessionProgress({ responses: updated });
      return updated;
    });
  };

  const goToQuestion = (direction) => {
    if (!questions.length) return;
    setCurrentQuestionIndex((prev) => {
      let nextIndex = prev;
      if (direction === 'next') {
        nextIndex = Math.min(prev + 1, questions.length - 1);
      } else if (direction === 'prev') {
        nextIndex = Math.max(prev - 1, 0);
      }
      if (nextIndex !== prev) {
        syncSessionProgress({ currentQuestionIndex: nextIndex });
      }
      return nextIndex;
    });
  };

  const handleSubmitExam = async () => {
    if (answeredCount < questions.length) {
      setSubmitStatus({
        show: true,
        severity: 'error',
        message: tr('Please answer all questions before submitting.', 'يرجى الإجابة على جميع الأسئلة قبل الإرسال.'),
      });
      return;
    }
    setSubmitting(true);
    setJustSubmitted(false);
    setSubmitStatus({ show: false, severity: 'success', message: '' });
    try {
      const answersPayload = questions.map((question) => {
        if (question.question_type === 'MCQ') {
          const selected = responses[question.question_id];
          const choiceIds = Array.isArray(selected)
            ? selected
            : selected
            ? [selected]
            : [];
          return {
            question_id: question.question_id,
            choice_ids: choiceIds,
          };
        }
        return {
          question_id: question.question_id,
          choice_id: responses[question.question_id] || null,
        };
      });
        const submitResponse = await examService.submitExam(exam.exam_id, answersPayload);
        const updatedAttempts = submitResponse?.data?.result || {};
        setExam((prev) =>
          prev
            ? {
                ...prev,
                attempts_used:
                  updatedAttempts.attempts_used !== undefined
                    ? updatedAttempts.attempts_used
                    : prev.attempts_used,
                attempts_left:
                  updatedAttempts.attempts_left !== undefined
                    ? updatedAttempts.attempts_left
                    : prev.attempts_left,
                session_state: null,
              }
            : prev
        );
      setSubmitStatus({
        show: true,
        severity: 'success',
        message: tr('Exam submitted successfully. You may close this page.', 'تم إرسال الاختبار بنجاح. يمكنك إغلاق هذه الصفحة.'),
      });
      setShowQuestionFlow(false);
      setIsExamActive(false);
      setAttemptLocked(true);
      setExamNotification(tr('Exam submitted successfully.', 'تم إرسال الاختبار بنجاح.'));
      setRemainingSeconds(0);
      markSessionCompleted(tr('Exam submitted successfully.', 'تم إرسال الاختبار بنجاح.'));
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    } catch (error) {
      console.error('Failed to submit exam', error);
      let serverMessage =
        error.response?.data?.message ||
        tr('Failed to submit exam. Please try again.', 'فشل إرسال الاختبار. يرجى المحاولة مرة أخرى.');
      if (serverMessage.toLowerCase().includes('already submitted')) {
        const localizedMessage = tr('You have already submitted this exam.', 'لقد قمت بإرسال هذا الاختبار بالفعل.');
        serverMessage = localizedMessage;
        markSessionCompleted(localizedMessage, false);
        setAttemptLocked(true);
        setExamNotification(localizedMessage);
        setShowQuestionFlow(false);
        setIsExamActive(false);
      }
      setSubmitStatus({
        show: true,
        severity: 'error',
        message: serverMessage,
      });
    } finally {
      setSubmitting(false);
    }
  };

  const audienceConfig = exam?.audience || exam?.audience_config || {};
  const audienceSummary = exam?.audience_summary || {};
  const audienceFilters = audienceConfig.filters || {};
  const manualHrIdsCount = Array.isArray(audienceConfig.manual_hr_ids)
    ? audienceConfig.manual_hr_ids.filter((hr) => !!hr).length
    : 0;
  const previewHrIds = (audienceSummary.hr_ids || []).slice(0, 6);
  const extraHrIds = Math.max((audienceSummary.hr_ids || []).length - previewHrIds.length, 0);
  const filterLabelMap = {
    regions: 'Regions',
    areas: 'Areas',
    branches: 'Branches',
    branch_codes: 'Branch Codes',
    departments: 'Departments',
    divisions: 'Divisions',
    sub_departments: 'Sub Departments',
    titles: 'Titles',
    hr_ids: 'Specific HR IDs',
  };
  const activeFilters = Object.entries(filterLabelMap)
    .map(([key, label]) => {
      const value = audienceFilters[key];
      const list = Array.isArray(value) ? value.filter(Boolean) : value ? [value] : [];
      return list.length ? { label, values: list } : null;
    })
    .filter(Boolean);
  const currentQuestion = showQuestionFlow ? questions[currentQuestionIndex] : null;
  const answeredCount = questions.filter((question) => {
    const answer = responses[question.question_id];
    if (question.question_type === 'Essay') {
      return typeof answer === 'string' && answer.trim().length > 0;
    }
    if (question.question_type === 'MCQ') {
      return Array.isArray(answer) ? answer.length > 0 : Boolean(answer);
    }
    return Boolean(answer);
  }).length;
  const progressPercent = questions.length ? (answeredCount / questions.length) * 100 : 0;
  const questionProgress = questions.length ? ((currentQuestionIndex + 1) / questions.length) * 100 : 0;
  const showSubmitSuccessOnly =
    isRetailView && justSubmitted && submitStatus.show && submitStatus.severity === 'success';

  const currentAnswerValue = currentQuestion
    ? responses[currentQuestion.question_id] ?? (currentQuestion.question_type === 'Essay' ? '' : '')
    : '';
  const disableNextButton = !isQuestionAnswered(currentQuestion) || submitting;
  const disablePrevButton = currentQuestionIndex === 0 || submitting;
  const isLastQuestion = currentQuestionIndex === questions.length - 1;
  const canSubmitExam = answeredCount === questions.length && !submitting;

  const renderQuestionBody = () => {
    if (!currentQuestion) return null;
    if (currentQuestion.question_type === 'Essay') {
      return (
        <TextField
          fullWidth
          multiline
          minRows={4}
          variant="outlined"
          placeholder={tr('Type your answer here...', 'اكتب إجابتك هنا...')}
          value={currentAnswerValue}
          onChange={(e) => handleEssayChange(currentQuestion.question_id, e.target.value)}
          inputProps={{ dir: isArabic ? 'rtl' : 'ltr' }}
        />
      );
    }
    if (currentQuestion.question_type === 'MCQ') {
      const selected = Array.isArray(currentAnswerValue)
        ? currentAnswerValue
        : currentAnswerValue
        ? [currentAnswerValue]
        : [];
      return (
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: isArabic ? 'flex-end' : 'flex-start',
            textAlign: isArabic ? 'right' : 'left',
            gap: 1,
          }}
        >
          {currentQuestion.choices?.map((choice) => (
            <FormControlLabel
              key={choice.choice_id}
              sx={{ margin: 0, flexDirection: isArabic ? 'row-reverse' : 'row' }}
              control={
                <Checkbox
                  checked={selected.includes(choice.choice_id)}
                  onChange={(event) =>
                    handleSelectChoice(
                      currentQuestion.question_id,
                      choice.choice_id,
                      event.target.checked,
                      currentQuestion.question_type
                    )
                  }
                />
              }
              label={choice.choice_text}
            />
          ))}
        </Box>
      );
    }
    return (
      <RadioGroup
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: isArabic ? 'flex-end' : 'flex-start',
          textAlign: isArabic ? 'right' : 'left',
          gap: 1,
        }}
        value={currentAnswerValue}
        onChange={(event) =>
          handleSelectChoice(
            currentQuestion.question_id,
            event.target.value,
            true,
            currentQuestion.question_type
          )
        }
      >
        {currentQuestion.choices?.map((choice) => (
          <FormControlLabel
            key={choice.choice_id}
            sx={{ margin: 0, flexDirection: isArabic ? 'row-reverse' : 'row' }}
            value={choice.choice_id}
            control={<Radio />}
            label={choice.choice_text}
          />
        ))}
      </RadioGroup>
    );
  };

  return (
    <Box sx={{ direction: isArabic ? 'rtl' : 'ltr', textAlign: isArabic ? 'right' : 'left' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <IconButton onClick={handleBack} sx={{ mr: isArabic ? 0 : 2, ml: isArabic ? 2 : 0 }}>
          <ArrowBack sx={{ transform: isArabic ? 'rotate(180deg)' : 'none' }} />
        </IconButton>
        <Typography variant="h4" fontWeight="bold">
          {tr('Exam Details', 'تفاصيل الاختبار')}
        </Typography>
      </Box>

      {/* Exam Info */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
            <Typography variant="h5" fontWeight="bold">
              {exam.title}
            </Typography>
            <Chip label={examStatusLabel} color="success" />
          </Box>
          <Typography variant="body1" color="text.secondary" paragraph>
            {exam.description}
          </Typography>

          <Divider sx={{ my: 2 }} />

          <Grid container spacing={2}>
              <Grid item xs={12} sm={4}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexDirection: isArabic ? 'row-reverse' : 'row' }}>
                  <AccessTime color="primary" />
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      {tr('Duration', 'المدة')}
                    </Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {exam.duration_minutes} {tr('minutes', 'دقيقة')}
                    </Typography>
                  </Box>
                </Box>
              </Grid>
              <Grid item xs={12} sm={4}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexDirection: isArabic ? 'row-reverse' : 'row' }}>
                  <Repeat color="primary" />
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      {tr('Attempts Allowed', 'المحاولات المسموح بها')}
                    </Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {exam.number_of_attempts_allowed ?? 1}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {tr('Attempts left', 'المحاولات المتبقية')}: {attemptsRemainingDisplay}
                    </Typography>
                  </Box>
                </Box>
              </Grid>
            <Grid item xs={12} sm={4}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexDirection: isArabic ? 'row-reverse' : 'row' }}>
                <CalendarToday color="primary" />
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {tr('Start Date', 'تاريخ البدء')}
                  </Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {formatFullDateTime(exam.start_date, locale)}
                  </Typography>
                </Box>
              </Box>
            </Grid>
            <Grid item xs={12} sm={4}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexDirection: isArabic ? 'row-reverse' : 'row' }}>
                <CalendarToday color="primary" />
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {tr('End Date', 'تاريخ الانتهاء')}
                  </Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {formatFullDateTime(exam.end_date, locale)}
                  </Typography>
                </Box>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {!isRetailView && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6" fontWeight="bold">
                Target Audience
              </Typography>
              <Chip label={formatAudienceMode(audienceConfig.mode)} color="warning" variant="outlined" />
            </Box>

            <Grid container spacing={2}>
              <Grid item xs={12} sm={4}>
                <Typography variant="caption" color="text.secondary">
                  Audience Size
                </Typography>
                <Typography variant="body2" fontWeight={600}>
                  {audienceSummary.count ?? 0} employees
                </Typography>
              </Grid>
              <Grid item xs={12} sm={4}>
                <Typography variant="caption" color="text.secondary">
                  Manual HR IDs
                </Typography>
                <Typography variant="body2" fontWeight={600}>
                  {manualHrIdsCount}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={4}>
                <Typography variant="caption" color="text.secondary">
                  Last Snapshot
                </Typography>
                <Typography variant="body2" fontWeight={600}>
                  {audienceSummary.hr_ids ? `${audienceSummary.hr_ids.length} resolved IDs` : 'Not available'}
                </Typography>
              </Grid>
            </Grid>

            {audienceConfig.mode === 'filters' && (
              <Box sx={{ mt: 3 }}>
                <Typography variant="subtitle2" fontWeight={600} gutterBottom>
                  Applied Filters
                </Typography>
                {activeFilters.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No filters selected. All employees will be targeted unless additional filters are applied.
                  </Typography>
                ) : (
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    {activeFilters.map(({ label, values }) => (
                      <Box key={label}>
                        <Typography variant="caption" color="text.secondary">
                          {label}
                        </Typography>
                        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 0.5 }}>
                          {values.slice(0, 8).map((value) => (
                            <Chip key={`${label}-${value}`} label={value} size="small" variant="outlined" />
                          ))}
                          {values.length > 8 && (
                            <Chip
                              label={`+${values.length - 8} more`}
                              size="small"
                              variant="outlined"
                            />
                          )}
                        </Box>
                      </Box>
                    ))}
                  </Box>
                )}
              </Box>
            )}

            {previewHrIds.length > 0 && (
              <Box sx={{ mt: 3 }}>
                <Typography variant="subtitle2" fontWeight={600} gutterBottom>
                  HR IDs Preview
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                  {previewHrIds.map((hrId) => (
                    <Chip key={hrId} label={hrId} size="small" />
                  ))}
                  {extraHrIds > 0 && (
                    <Chip label={`+${extraHrIds} more`} size="small" variant="outlined" />
                  )}
                </Box>
              </Box>
            )}

            {audienceConfig.mode === 'all' && (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                This exam is available to every employee.
              </Typography>
            )}
            {audienceConfig.mode === 'manual' && manualHrIdsCount === 0 && (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                Manual mode selected, but no HR IDs have been provided.
              </Typography>
            )}
          </CardContent>
        </Card>
      )}
      {/* Questions Preview */}
      {isRetailView ? (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" fontWeight="bold" gutterBottom>
              {tr('Questions Overview', 'نظرة عامة على الأسئلة')}
            </Typography>
            <Divider sx={{ mb: 2 }} />
            <Typography variant="h2" fontWeight="bold">
              {exam.questions?.length || 0}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {tr(
                'Total questions assigned for this exam. Detailed content will be available when you start the exam.',
                'إجمالي الأسئلة المخصصة لهذا الاختبار. ستتوفر التفاصيل عند بدء الاختبار.'
              )}
            </Typography>
          </CardContent>
        </Card>
      ) : (
        <Card sx={{ mb: 3 }}>
          <CardContent sx={{ p: 0, '&:last-child': { pb: 0 } }}>
            <Accordion
              disableGutters
              sx={{
                boxShadow: 'none',
                '&:before': { display: 'none' },
              }}
            >
              <AccordionSummary
                expandIcon={<ExpandMore />}
                sx={{
                  px: 3,
                  py: 2,
                  '& .MuiAccordionSummary-content': {
                    my: 0,
                  },
                }}
              >
                <Box>
                  <Typography variant="h6" fontWeight="bold">
                    Questions ({exam.questions?.length || 0})
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {tr('Click to show the exam questions.', 'اضغط لعرض أسئلة الاختبار.')}
                  </Typography>
                </Box>
              </AccordionSummary>
              <AccordionDetails sx={{ px: 3, pb: 3 }}>
                <Divider sx={{ mb: 2 }} />
                {exam.questions && exam.questions.length > 0 ? (
                  exam.questions.map((question, index) => (
                    <Accordion
                      key={question.question_id}
                      disableGutters
                      sx={{
                        mb: 2,
                        border: '1px solid',
                        borderColor: 'divider',
                        borderRadius: 3,
                        bgcolor: 'grey.50',
                        overflow: 'hidden',
                        '&:before': { display: 'none' },
                      }}
                    >
                      <AccordionSummary
                        expandIcon={<ExpandMore />}
                        sx={{
                          px: 2,
                          py: 1,
                          '& .MuiAccordionSummary-content': {
                            my: 0.5,
                          },
                        }}
                      >
                        <Box sx={{ minWidth: 0, width: '100%' }}>
                          <Stack
                            direction={{ xs: 'column', sm: 'row' }}
                            spacing={1}
                            alignItems={{ xs: 'flex-start', sm: 'center' }}
                            justifyContent="space-between"
                            sx={{ mb: 0.5 }}
                          >
                            <Typography variant="subtitle2" fontWeight={700}>
                              {tr('Question', 'السؤال')} {index + 1}
                            </Typography>
                            <Stack direction="row" spacing={1} flexWrap="wrap">
                              <Chip
                                size="small"
                                label={tr(`${question.points} points`, `${question.points} نقاط`)}
                                color="primary"
                                variant="outlined"
                              />
                              <Chip size="small" label={question.question_type} variant="outlined" />
                            </Stack>
                          </Stack>
                          <Typography
                            variant="body2"
                            color="text.secondary"
                            sx={{
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              display: '-webkit-box',
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: 'vertical',
                            }}
                          >
                            {question.question_text}
                          </Typography>
                        </Box>
                      </AccordionSummary>
                      <AccordionDetails sx={{ px: 2, pt: 0, pb: 2 }}>
                        <Typography variant="body2" paragraph sx={{ whiteSpace: 'pre-wrap' }}>
                          {question.question_text}
                        </Typography>
                        {question.choices && question.choices.length > 0 && (
                          <Box sx={{ pl: { xs: 0, sm: 2 } }}>
                            {question.choices.map((choice, cIndex) => {
                              const isCorrect = Boolean(choice.is_correct);
                              return (
                                <Typography
                                  key={choice.choice_id}
                                  variant="body2"
                                  sx={{
                                    mb: 0.75,
                                    color: isCorrect ? 'success.main' : 'text.secondary',
                                    fontWeight: isCorrect ? 600 : 400,
                                  }}
                                >
                                  {String.fromCharCode(65 + cIndex)}. {choice.choice_text}{' '}
                                  {isCorrect && (
                                    <Chip
                                      size="small"
                                      color="success"
                                      label={tr('Correct', 'صحيح')}
                                      sx={{ ml: 1 }}
                                    />
                                  )}
                                </Typography>
                              );
                            })}
                          </Box>
                        )}
                      </AccordionDetails>
                    </Accordion>
                  ))
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    {tr('No questions available yet.', 'لا توجد أسئلة متاحة بعد.')}
                  </Typography>
                )}
              </AccordionDetails>
            </Accordion>
          </CardContent>
        </Card>
      )}

      {!isRetailView && (
        <Box sx={{ mb: 3 }}>
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Box
                sx={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: { xs: 'flex-start', sm: 'center' },
                  flexDirection: { xs: 'column', sm: 'row' },
                  gap: 1,
                  mb: 1,
                }}
              >
                <Typography variant="h6" fontWeight="bold">
                  Exam Performance Overview
                </Typography>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                  <Button
                    variant="outlined"
                    startIcon={<Download />}
                    size="small"
                    onClick={handleDownloadExamResults}
                    disabled={downloadingExcel || resultsLoading || !hasResultsData}
                  >
                    {downloadingExcel ? 'Preparing...' : 'Download Excel'}
                  </Button>
                  <Chip
                    label={
                      resultsSummary?.last_submission_at
                        ? `Last submission: ${formatFullDateTime(resultsSummary.last_submission_at)}`
                        : 'No submissions yet'
                    }
                    color="primary"
                    variant="outlined"
                  />
                </Stack>
              </Box>
              {resultsLoading ? (
                <Box sx={{ py: 4 }}>
                  <LinearProgress />
                </Box>
              ) : resultsError ? (
                <Alert severity="error">{resultsError}</Alert>
              ) : !hasResultsData ? (
                <Alert severity="info">No attempts have been submitted for this exam yet.</Alert>
              ) : (
                <>
                  <Grid container spacing={2} sx={{ mb: 2 }}>
                    {summaryCards.map((card) => (
                      <Grid item xs={12} sm={6} md={4} key={card.label}>
                        <Card variant="outlined" sx={{ height: '100%' }}>
                          <CardContent>
                            <Typography variant="caption" color="text.secondary">
                              {card.label}
                            </Typography>
                            <Typography variant="h5" fontWeight="bold">
                              {card.value}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              {card.helper}
                            </Typography>
                          </CardContent>
                        </Card>
                      </Grid>
                    ))}
                  </Grid>
                  {topPerformer && (
                    <Card variant="outlined" sx={{ mb: 2 }}>
                      <CardContent>
                        <Stack
                          direction={{ xs: 'column', sm: 'row' }}
                          alignItems={{ xs: 'flex-start', sm: 'center' }}
                          justifyContent="space-between"
                          spacing={2}
                        >
                          <Stack direction="row" spacing={2} alignItems="center">
                            <Avatar sx={{ bgcolor: 'success.main' }}>
                              {(topPerformer.employee_name || '?')
                                .split(' ')
                                .map((part) => part[0])
                                .join('')
                                .slice(0, 2)
                                .toUpperCase()}
                            </Avatar>
                            <Box>
                              <Typography variant="subtitle1" fontWeight={600}>
                                {topPerformer.employee_name || 'Top Performer'}
                              </Typography>
                              <Typography variant="body2" color="text.secondary">
                                HR ID: {topPerformer.employee_hr_id || '-'}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                Submitted at {formatFullDateTime(topPerformer.submitted_at)}
                              </Typography>
                            </Box>
                          </Stack>
                          <Chip
                            label={`${formatPercentageValue(topPerformer.score_percentage)} • ${formatNumber(
                              topPerformer.total_score,
                              { maximumFractionDigits: 2, minimumFractionDigits: 0 }
                            )} pts`}
                            color="success"
                          />
                        </Stack>
                      </CardContent>
                    </Card>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          {hasResultsData && !resultsLoading && !resultsError && (
            <>
              <Card sx={{ mb: 3 }}>
                <CardContent>
                  <Box
                    sx={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: { xs: 'flex-start', sm: 'center' },
                      flexDirection: { xs: 'column', sm: 'row' },
                      gap: 1,
                      mb: 2,
                    }}
                  >
                    <Box>
                      <Typography variant="h6" fontWeight="bold">
                        Participants Overview
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Track who attempted the exam, pass outcomes, and follow-up needs.
                      </Typography>
                    </Box>
                    <Chip
                      label={`${participantsOverview.length} employees`}
                      color="default"
                      variant="outlined"
                    />
                  </Box>
                  <TableContainer component={Paper} variant="outlined">
                    <Table size="small">
                      <TableHead sx={{ bgcolor: 'grey.100' }}>
                        <TableRow>
                          <TableCell>Employee</TableCell>
                          <TableCell>HR ID</TableCell>
                          <TableCell>Branch</TableCell>
                          <TableCell>Status</TableCell>
                          <TableCell align="right">Attempts</TableCell>
                          <TableCell align="right">Last Score</TableCell>
                          <TableCell align="right">Last Activity</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {participantsOverview.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={7} align="center">
                              <Typography variant="body2" color="text.secondary">
                                No assigned participants were found for this exam.
                              </Typography>
                            </TableCell>
                          </TableRow>
                        ) : (
                          participantsToDisplay.map((participant) => (
                            <TableRow key={participant.employee_id}>
                              <TableCell>
                                <Typography variant="body2" fontWeight={600}>
                                  {participant.employee_name || '-'}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  {participant.employee_title || participant.department || ''}
                                </Typography>
                              </TableCell>
                              <TableCell>{participant.employee_hr_id || '-'}</TableCell>
                              <TableCell>
                                {participant.branch_name ? (
                                  <Tooltip
                                    title={[
                                      participant.branch_area,
                                      participant.branch_region,
                                      participant.branch_division,
                                    ]
                                      .filter(Boolean)
                                      .join(' • ')}
                                  >
                                    <span>{participant.branch_name}</span>
                                  </Tooltip>
                                ) : (
                                  '-'
                                )}
                              </TableCell>
                              <TableCell>
                                <Chip
                                  label={canonicalParticipantStatusLabelMap[participant.status] || participant.status}
                                  color={canonicalParticipantStatusColorMap[participant.status] || 'default'}
                                  size="small"
                                />
                              </TableCell>
                              <TableCell align="right">{formatNumber(participant.attempts_count)}</TableCell>
                              <TableCell align="right">
                                {participant.last_score_percentage !== undefined &&
                                participant.last_score_percentage !== null
                                  ? formatPercentageValue(participant.last_score_percentage)
                                  : '-'}
                              </TableCell>
                              <TableCell align="right">
                                {participant.last_activity_at
                                  ? formatFullDateTime(participant.last_activity_at, locale)
                                  : '-'}
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </TableContainer>
                  {participantsOverview.length > 0 && (
                    <TablePagination
                      component="div"
                      count={participantsOverview.length}
                      page={participantsRowsPerPage === -1 ? 0 : participantsPage}
                      onPageChange={handleParticipantsPageChange}
                      rowsPerPage={participantsRowsPerPage}
                      onRowsPerPageChange={handleParticipantsRowsPerPageChange}
                      rowsPerPageOptions={[10, 25, 50, 100, { label: 'All', value: -1 }]}
                      labelRowsPerPage="Rows per page"
                      sx={{ borderTop: 1, borderColor: 'divider' }}
                    />
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardContent>
                    <Typography variant="h6" fontWeight="bold" gutterBottom>
                      Attempt Insights
                    </Typography>
                    {resultsDetails.length === 0 ? (
                      <Typography variant="body2" color="text.secondary">
                        Attempts will appear here once participants submit the exam.
                      </Typography>
                    ) : (
                      <>
                        <TextField
                          fullWidth
                          size="small"
                          value={attemptSearchTerm}
                          onChange={(event) => setAttemptSearchTerm(event.target.value)}
                          placeholder={tr(
                            'Search attempted employees by name or HR ID',
                            'ابحث عن الموظفين الذين حاولوا الاختبار بالاسم أو الرقم الوظيفي'
                          )}
                          sx={{ mb: 2 }}
                        />
                        {filteredResultsDetails.length === 0 ? (
                          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                            {tr(
                              'No attempted employees match this search.',
                              'لا يوجد موظفون مطابقون لهذا البحث.'
                            )}
                          </Typography>
                        ) : (
                          <>
                      {attemptsToDisplay.map((attempt) => (
                        <Accordion key={attempt.attempt_id} disableGutters sx={{ mb: 1 }}>
                          <AccordionSummary expandIcon={<ExpandMore />}>
                            <Stack
                              direction={{ xs: 'column', sm: 'row' }}
                              spacing={2}
                              sx={{ width: '100%', alignItems: { sm: 'center' } }}
                              justifyContent="space-between"
                            >
                              <Stack direction="row" spacing={2} alignItems="center">
                                <Avatar sx={{ bgcolor: attempt.passed ? 'success.main' : 'warning.main' }}>
                                  {(attempt.employee_name || '?')
                                    .split(' ')
                                    .map((part) => part[0])
                                    .join('')
                                    .slice(0, 2)
                                    .toUpperCase()}
                                </Avatar>
                                <Box>
                                  <Typography variant="subtitle2" fontWeight={600}>
                                    {attempt.employee_name || 'Employee'}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    HR ID: {attempt.employee_hr_id || '-'}
                                  </Typography>
                                </Box>
                              </Stack>
                              <Stack
                                direction={{ xs: 'column', sm: 'row' }}
                                spacing={1}
                                alignItems={{ xs: 'flex-start', sm: 'center' }}
                              >
                                <Chip
                                  label={attempt.passed ? 'Passed' : 'Attempted'}
                                  color={attempt.passed ? 'success' : 'warning'}
                                  size="small"
                                />
                                <Chip
                                  label={formatPercentageValue(attempt.score_percentage)}
                                  color={attempt.passed ? 'success' : 'warning'}
                                  variant="outlined"
                                  size="small"
                                />
                                <Typography variant="caption" color="text.secondary">
                                  {formatFullDateTime(attempt.submitted_at)}
                                </Typography>
                              </Stack>
                            </Stack>
                          </AccordionSummary>
                          <AccordionDetails>
                            <Grid container spacing={2} sx={{ mb: 2 }}>
                              <Grid item xs={6} sm={3}>
                                <Typography variant="caption" color="text.secondary">
                                  Score
                                </Typography>
                                <Typography variant="body2" fontWeight={600}>
                                  {formatScoreDisplay(attempt.total_score, attempt.max_score, locale)}
                                </Typography>
                              </Grid>
                              <Grid item xs={6} sm={3}>
                                <Typography variant="caption" color="text.secondary">
                                  Percentage
                                </Typography>
                                <Typography variant="body2" fontWeight={600}>
                                  {formatPercentageValue(attempt.score_percentage)}
                                </Typography>
                              </Grid>
                              <Grid item xs={6} sm={3}>
                                <Typography variant="caption" color="text.secondary">
                                  Duration
                                </Typography>
                                <Typography variant="body2" fontWeight={600}>
                                  {formatDurationFromSeconds(attempt.duration_seconds)}
                                </Typography>
                              </Grid>
                              <Grid item xs={6} sm={3}>
                                <Typography variant="caption" color="text.secondary">
                                  Started
                                </Typography>
                                <Typography variant="body2" fontWeight={600}>
                                  {formatFullDateTime(attempt.started_at)}
                                </Typography>
                              </Grid>
                            </Grid>
                            <TableContainer component={Paper} variant="outlined">
                              <Table size="small">
                                <TableHead>
                                  <TableRow>
                                    <TableCell>Question</TableCell>
                                    <TableCell>Selected Answer</TableCell>
                                    <TableCell>Correct Answer</TableCell>
                                    <TableCell>Result</TableCell>
                                  </TableRow>
                                </TableHead>
                                <TableBody>
                                  {(attempt.answers || []).map((answer) => (
                                    <TableRow key={answer.answer_id || `${attempt.attempt_id}-${answer.question_id}`}>
                                      <TableCell>
                                        <Typography variant="body2" fontWeight={600}>
                                          {answer.question_text || 'Question'}
                                        </Typography>
                                        <Typography variant="caption" color="text.secondary" display="block">
                                          {answer.question_type || ''}{' '}
                                          {answer.question_points
                                            ? `• ${formatNumber(answer.question_points)} pts`
                                            : ''}
                                        </Typography>
                                      </TableCell>
                                      <TableCell>
                                        <Typography variant="body2">
                                          {answer.selected_choice_text || 'No answer'}
                                        </Typography>
                                        {answer.selected_choice_id && (
                                          <Typography variant="caption" color="text.secondary">
                                            {answer.selected_choice_id}
                                          </Typography>
                                        )}
                                      </TableCell>
                                      <TableCell>
                                        <Typography variant="body2">
                                          {answer.correct_choice_text || '-'}
                                        </Typography>
                                      </TableCell>
                                      <TableCell>
                                        <Chip
                                          label={answer.is_correct ? 'Correct' : 'Incorrect'}
                                          color={answer.is_correct ? 'success' : 'error'}
                                          size="small"
                                          sx={{ mb: 0.5 }}
                                        />
                                        <Typography variant="caption" color="text.secondary" display="block">
                                          +{formatNumber(answer.points_awarded, { maximumFractionDigits: 2 })}
                                        </Typography>
                                      </TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            </TableContainer>
                          </AccordionDetails>
                        </Accordion>
                      ))}
                      {hasMoreAttempts && (
                        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                          {tr(
                            `Showing ${attemptsToDisplay.length} of ${filteredResultsDetails.length} matching attempts.`,
                            `يتم عرض ${attemptsToDisplay.length} من أصل ${filteredResultsDetails.length} محاولة مطابقة.`
                          )}
                        </Typography>
                      )}
                          </>
                        )}
                    </>
                  )}
                </CardContent>
              </Card>
            </>
          )}
        </Box>
      )}

      {isRetailView && showQuestionFlow && currentQuestion && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6" fontWeight="bold">
                {tr('Question', 'السؤال')} {currentQuestionIndex + 1} {tr('of', 'من')} {questions.length}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {tr('Answered', 'تمت الإجابة')} {answeredCount}/{questions.length}
              </Typography>
            </Box>
            <LinearProgress variant="determinate" value={questionProgress} sx={{ mb: 3 }} />
            <Typography variant="subtitle1" fontWeight={600} gutterBottom>
              {currentQuestion.question_text}
            </Typography>
            <Typography variant="caption" color="text.secondary" gutterBottom display="block">
              {tr('Type', 'النوع')}: {currentQuestion.question_type}
            </Typography>
            <Typography variant="caption" color="text.secondary" gutterBottom display="block">
              {tr('Group', 'المجموعة')}: {resolveQuestionGroupName(currentQuestion)}
            </Typography>
            <Box sx={{ mt: 2 }}>{renderQuestionBody()}</Box>

            <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 3, gap: 1, flexWrap: 'wrap' }}>
              <Button variant="outlined" onClick={() => goToQuestion('prev')} disabled={disablePrevButton}>
                {tr('Previous', 'السابق')}
              </Button>
              {!isLastQuestion && (
                <Button variant="contained" onClick={() => goToQuestion('next')} disabled={disableNextButton}>
                  {tr('Next Question', 'السؤال التالي')}
                </Button>
              )}
              {isLastQuestion && (
                <Button variant="contained" color="success" onClick={handleSubmitExam} disabled={!canSubmitExam}>
                  {submitting ? tr('Submitting...', 'جارٍ الإرسال...') : tr('Submit Exam', 'إرسال الاختبار')}
                </Button>
              )}
            </Box>
            {!isQuestionAnswered(currentQuestion) && (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                {tr('Please answer this question to continue.', 'يرجى الإجابة على هذا السؤال للمتابعة.')}
              </Typography>
            )}
          </CardContent>
        </Card>
      )}

      {isRetailView && (
        <Box sx={{ mt: 3 }}>
          {showSubmitSuccessOnly ? (
            <Alert severity={submitStatus.severity} sx={{ mt: 1 }}>
              {submitStatus.message}
            </Alert>
          ) : (
            <>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 2 }}>
            <Button
              variant="contained"
              size="large"
              onClick={handleStartExamRequest}
              disabled={resolvedStartButtonDisabled}
            >
              {resolvedStartButtonLabel}
            </Button>
            {isExamActive && remainingSeconds !== null && (
              <Chip
                color={remainingSeconds <= 60 ? 'error' : 'primary'}
                label={`${tr('Time left', 'الوقت المتبقي')}: ${formatRemainingTime(remainingSeconds)}`}
              />
            )}
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {availabilityMessage}
          </Typography>
          {examNotification && (
            <Typography variant="body2" color="error" sx={{ mt: 1 }}>
              {examNotification}
            </Typography>
          )}
          {submitStatus.show && (
            <Alert severity={submitStatus.severity} sx={{ mt: 1 }}>
              {submitStatus.message}
            </Alert>
          )}
            </>
          )}
        </Box>
      )}
    </Box>
  );
};

export default ExamDetails;
