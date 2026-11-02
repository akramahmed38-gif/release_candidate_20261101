import React, { useState } from 'react';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from '@mui/material';
import { History } from '@mui/icons-material';
import { useLanguage } from '../context/LanguageContext';
import { dailyBriefService } from '../services/auth';

export default function DailyBriefActions({ brief }) {
  const { t, isArabic } = useLanguage();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState(null);
  const [deliveries, setDeliveries] = useState(null);
  const [deliveryError, setDeliveryError] = useState(false);
  const [error, setError] = useState(false);
  const labels = {
    CREATED: t('Created', 'تم الإنشاء'), EDITED: t('Edited', 'تم التعديل'),
    PUBLISHED: t('Published', 'تم النشر'), ARCHIVED: t('Archived', 'تمت الأرشفة'),
    AUTO_ARCHIVED: t('Automatically archived when another brief went live', 'تمت الأرشفة تلقائيًا عند نشر ملخص آخر'),
    RESTORED: t('Restored to Live', 'أُعيد نشره'), DELETED: t('Deleted', 'تم الحذف'),
    DUPLICATED: t('Created as a copy', 'تم الإنشاء كنسخة'),
  };
  const load = async () => {
    setOpen(true); setItems(null); setDeliveries(null); setDeliveryError(false); setError(false);
    try {
      const [actionResult, deliveryResult] = await Promise.allSettled([
        dailyBriefService.getActions(brief.id),
        dailyBriefService.getEmailDeliveryHistory(brief.id),
      ]);
      if (actionResult.status !== 'fulfilled') throw actionResult.reason;
      const response = actionResult.value;
      if (!Array.isArray(response.data?.items)) throw new Error('Invalid response');
      setItems(response.data.items);
      if (deliveryResult.status === 'fulfilled' && Array.isArray(deliveryResult.value.data?.items)) {
        setDeliveries(deliveryResult.value.data.items);
      } else {
        setDeliveryError(true);
        console.warn('Unable to load Daily Brief email delivery history.', deliveryResult.status === 'rejected' ? deliveryResult.reason : deliveryResult.value?.data);
      }
    } catch { setError(true); }
  };
  return <>
    <Button startIcon={<History />} onClick={load}>{t('Action history', 'سجل الإجراءات')}</Button>
    <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
      <DialogTitle>{t('Action history', 'سجل الإجراءات')} — {brief.title}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={1.5} sx={{ mb: 3 }}>
          <Typography fontWeight={700}>{t('Email delivery results', 'نتائج إرسال البريد')}</Typography>
          {deliveryError ? <Alert severity="warning">{t('Unable to load email delivery results. Please try again.', 'تعذر تحميل نتائج إرسال البريد. يرجى المحاولة مرة أخرى.')}</Alert>
            : deliveries === null ? <Typography>{t('Loading...', 'جارٍ التحميل...')}</Typography>
              : deliveries.length === 0 ? <Typography>{t('No email delivery results recorded for this brief.', 'لا توجد نتائج إرسال بريد مسجلة لهذا الملخص.')}</Typography>
                : deliveries.map((batch) => <Stack key={batch.id} spacing={0.75} sx={{ pb: 1, borderBottom: '1px solid', borderColor: 'divider' }}>
                  <Typography color="text.secondary">{new Intl.DateTimeFormat(isArabic ? 'ar-EG' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(batch.triggered_at))} - {batch.accepted_count} {t('accepted', 'مقبول')}, {batch.rejected_count} {t('rejected', 'مرفوض')}, {batch.failed_count} {t('failed', 'فشل')}</Typography>
                  {batch.recipients.map((recipient) => <Typography key={recipient.email} variant="body2" sx={{ overflowWrap: 'anywhere' }}>{recipient.email}: <strong>{recipient.status}</strong>{recipient.smtp_code ? ` (${recipient.smtp_code})` : ''}{recipient.smtp_message ? ` - ${recipient.smtp_message}` : ''}</Typography>)}
                </Stack>)}
        </Stack>
        {error ? <Alert severity="error" action={<Button onClick={load}>{t('Retry', 'إعادة المحاولة')}</Button>}>{t('Unable to load action history.', 'تعذر تحميل سجل الإجراءات.')}</Alert> : items === null ? <Typography>{t('Loading...', 'جارٍ التحميل...')}</Typography> : !items.length ? <Typography>{t('No recorded actions. History is captured for actions performed after this feature is activated.', 'لا توجد إجراءات مسجلة. يُسجّل التاريخ للإجراءات المنفذة بعد تفعيل هذه الميزة.')}</Typography> : <Stack spacing={2}>{items.map(item => <Stack key={item.id} spacing={0.5}>
          <Typography fontWeight={700}>{labels[item.action] || item.action}</Typography>
          <Typography dir="auto" sx={{ overflowWrap: 'anywhere' }}>{item.actor}</Typography>
          <Typography color="text.secondary">{new Intl.DateTimeFormat(isArabic ? 'ar-EG' : 'en-GB', { dateStyle: 'medium', timeStyle: 'long' }).format(new Date(item.occurred_at))}</Typography>
        </Stack>)}</Stack>}
      </DialogContent>
      <DialogActions><Button onClick={() => setOpen(false)}>{t('Close', 'إغلاق')}</Button></DialogActions>
    </Dialog>
  </>;
}
