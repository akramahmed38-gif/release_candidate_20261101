import React, { useEffect, useRef, useState } from 'react';
import { CheckCircle, ErrorOutline, HourglassEmpty, Refresh } from '@mui/icons-material';
import { Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from '@mui/material';
import { dailyBriefService } from '../services/auth';
import { useLanguage } from '../context/LanguageContext';

const terminal = new Set(['ACCEPTED', 'REJECTED', 'FAILED']);

export default function DailyBriefEmailProgress({ open, brief, batchId, startError, onClose, onStatus }) {
  const { t, isArabic } = useLanguage();
  const [batch, setBatch] = useState(null);
  const [fetchError, setFetchError] = useState(false);
  const busy = useRef(false);
  const timer = useRef(null);
  const active = useRef(false);

  const refresh = async () => {
    if (!batchId || busy.current) return;
    busy.current = true;
    try {
      const response = await dailyBriefService.getEmailDeliveryHistory(brief.id);
      const found = response.data?.items?.find((item) => item.id === batchId);
      if (!found) throw new Error('Email batch not found in delivery history');
      if (active.current) {
        setBatch(found);
        setFetchError(false);
        onStatus(found.status);
      }
      return found;
    } catch (error) {
      if (active.current) setFetchError(true);
      console.warn('Unable to refresh Daily Brief email status.', error);
      return null;
    } finally {
      busy.current = false;
    }
  };

  useEffect(() => {
    active.current = open;
    if (!open || !batchId || !brief) return () => { active.current = false; };
    setBatch(null);
    setFetchError(false);
    let cancelled = false;
    const poll = async () => {
      const result = await refresh();
      if (!cancelled && result && !['COMPLETED', 'COMPLETED_WITH_ERRORS'].includes(result.status)) {
        timer.current = window.setTimeout(poll, 2000);
      }
    };
    poll();
    return () => {
      cancelled = true;
      active.current = false;
      window.clearTimeout(timer.current);
    };
  }, [open, batchId, brief?.id]);

  const recipients = batch?.recipients || [];
  const processed = recipients.filter((item) => terminal.has(item.status)).length;
  const total = batch?.recipient_count ?? 0;
  const unknown = Math.max(0, total - processed);
  const completed = ['COMPLETED', 'COMPLETED_WITH_ERRORS'].includes(batch?.status);
  const formatTime = (value) => value ? new Intl.DateTimeFormat(isArabic ? 'ar-EG' : 'en-GB', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Cairo',
  }).format(new Date(value)) : '';
  const result = (recipient) => {
    switch (recipient.status) {
      case 'ACCEPTED': return { color: 'success.main', icon: <CheckCircle fontSize="small" />, label: t('Sent - server accepted', 'تم الإرسال - قبله الخادم') };
      case 'REJECTED': return { color: 'error.main', icon: <ErrorOutline fontSize="small" />, label: t('Rejected', 'مرفوض') };
      case 'FAILED': return { color: 'error.main', icon: <ErrorOutline fontSize="small" />, label: t('Failed', 'فشل') };
      case 'PENDING': return { color: 'text.secondary', icon: <HourglassEmpty fontSize="small" />, label: t('Pending', 'قيد الانتظار') };
      default: return { color: 'warning.main', icon: <ErrorOutline fontSize="small" />, label: t('Outcome unknown', 'النتيجة غير معروفة') };
    }
  };

  return <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" aria-labelledby="brief-email-title" dir={isArabic ? 'rtl' : 'ltr'}>
    <DialogTitle id="brief-email-title" sx={{ color: '#102a56', fontWeight: 800 }}>{t('Daily Brief Email', 'البريد الإلكتروني للملخص اليومي')}</DialogTitle>
    <DialogContent dividers>
      <Stack spacing={2}>
        <Box><Typography fontWeight={700}>{brief?.title}</Typography><Typography color="text.secondary">{brief?.brief_date}</Typography></Box>
        {startError && <Alert severity="warning">{startError}</Alert>}
        {fetchError && <Alert severity="warning" action={<Button onClick={refresh} disabled={busy.current}>{t('Refresh status', 'تحديث الحالة')}</Button>}>{t('Unable to refresh sending status. Outcome unknown until records can be retrieved.', 'تعذر تحديث حالة الإرسال. النتيجة غير معروفة حتى يمكن تحميل السجلات.')}</Alert>}
        {batch ? <>
          <Typography color="text.secondary">{t('Started (Cairo time):', 'بدأ (بتوقيت القاهرة):')} {formatTime(batch.triggered_at)}</Typography>
          <Typography fontWeight={700}>{processed} {t('of', 'من')} {total} {t('processed', 'تمت معالجتهم')}</Typography>
          <Typography color="text.secondary">{batch.accepted_count} {t('accepted', 'مقبول')}, {batch.rejected_count} {t('rejected', 'مرفوض')}, {batch.failed_count} {t('failed', 'فشل')}{completed && unknown ? `, ${unknown} ${t('unknown', 'غير معروف')}` : ''}</Typography>
          {batch.status === 'PROCESSING' && <Stack direction="row" alignItems="center" spacing={1}><CircularProgress size={16} /><Typography>{t('Sending...', 'جارٍ الإرسال...')}</Typography></Stack>}
          {recipients.map((recipient) => {
            const state = result(recipient);
            return <Box key={recipient.email} sx={{ p: 1.5, border: '1px solid #e1e6ee', borderRadius: 2 }}>
              <Typography sx={{ overflowWrap: 'anywhere' }}>{recipient.email}</Typography>
              <Stack direction="row" alignItems="center" spacing={0.5} sx={{ color: state.color }}>{state.icon}<Typography variant="body2" fontWeight={700}>{state.label}</Typography></Stack>
              {recipient.smtp_message && recipient.status !== 'ACCEPTED' && <Typography variant="caption" color="text.secondary">{recipient.smtp_code ? `${recipient.smtp_code}: ` : ''}{recipient.smtp_message}</Typography>}
            </Box>;
          })}
          {completed && unknown > 0 && <Alert severity="warning">{t('Some recipient outcomes remain unknown.', 'لا تزال بعض نتائج المستلمين غير معروفة.')}</Alert>}
        </> : !startError && !fetchError && <Stack direction="row" spacing={1} alignItems="center"><CircularProgress size={18} /><Typography>{t('Loading sending status...', 'جارٍ تحميل حالة الإرسال...')}</Typography></Stack>}
        <Alert severity="info">{t('Server acceptance does not confirm inbox delivery or delivery to every distribution-group member.', 'قبول الخادم لا يؤكد وصول الرسالة إلى صندوق الوارد أو إلى كل عضو في مجموعة التوزيع.')}</Alert>
      </Stack>
    </DialogContent>
    <DialogActions><Button startIcon={<Refresh />} onClick={refresh} disabled={!batchId}>{t('Refresh status', 'تحديث الحالة')}</Button><Button onClick={onClose}>{t('Close', 'إغلاق')}</Button></DialogActions>
  </Dialog>;
}
