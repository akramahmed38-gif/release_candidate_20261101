import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, Card, CardContent, Stack, TextField, Typography } from '@mui/material';
import { Add, Delete, Save } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '../context/LanguageContext';
import { dailyBriefService } from '../services/auth';

export default function DailyBriefAudience() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [recipients, setRecipients] = useState([]);
  const [revision, setRevision] = useState(null);
  const [busy, setBusy] = useState(true);
  const [notice, setNotice] = useState(null);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    let active = true;
    dailyBriefService.getAudience().then(({ data }) => {
      if (active) { setRecipients(data.recipients); setRevision(data.revision); }
    }).catch(() => { if (active) setNotice('load'); }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    const warn = (event) => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  const change = (next) => { setRecipients(next); setDirty(true); setNotice(null); };
  const save = async (event) => {
    event.preventDefault();
    const normalized = recipients.map(row => ({ name: row.name.trim(), email: row.email.trim().toLowerCase() }));
    if (new Set(normalized.map(row => row.email)).size !== normalized.length) { setNotice('duplicate'); return; }
    setBusy(true); setNotice(null);
    try {
      const { data } = await dailyBriefService.saveAudience({ recipients: normalized, revision });
      setRecipients(data.recipients); setRevision(data.revision); setDirty(false); setNotice('saved');
    } catch (error) { setNotice(error.response?.status === 409 ? 'conflict' : 'save'); }
    finally { setBusy(false); }
  };
  const messages = {
    load: t('Unable to load the audience. Refresh to retry.', 'تعذر تحميل المستلمين. حدّث الصفحة للمحاولة مجددًا.'),
    save: t('Save was not confirmed. Your edits remain here. Check the saved list before retrying.', 'لم يتم تأكيد الحفظ. تعديلاتك ما زالت هنا. تحقق من القائمة المحفوظة قبل إعادة المحاولة.'),
    conflict: t('Another administrator changed this list. Copy your edits, then refresh before saving again.', 'عدّل مسؤول آخر هذه القائمة. انسخ تعديلاتك ثم حدّث الصفحة قبل الحفظ مجددًا.'),
    duplicate: t('Remove duplicate email addresses before saving.', 'احذف عناوين البريد المكررة قبل الحفظ.'),
    saved: t('Audience saved. No email was sent.', 'تم حفظ المستلمين. لم يتم إرسال أي بريد.'),
  };
  return <Box sx={{ maxWidth: 960, mx: 'auto', py: 2 }}>
    <Typography variant="h4" fontWeight={800}>{t('Daily Brief email audience', 'مستلمو بريد الملخص اليومي')}</Typography>
    <Typography color="text.secondary" sx={{ my: 2 }}>{t('Manage email addresses and distribution groups for Send Brief Email. This does not change who can view the brief.', 'إدارة عناوين البريد ومجموعات التوزيع لإرسال الملخص بالبريد. لا يغيّر ذلك صلاحية مشاهدة الملخص.')}</Typography>
    {notice && <Alert severity={notice === 'saved' ? 'success' : 'error'} sx={{ mb: 2 }}>{messages[notice]}</Alert>}
    <Card><CardContent><Box component="form" onSubmit={save}>
      <Stack spacing={2}>
        {busy && revision === null ? <Typography>{t('Loading...', 'جارٍ التحميل...')}</Typography> : revision !== null && !recipients.length && <Alert severity="info">{t('No recipients. Email sending is disabled until you add and save an audience.', 'لا يوجد مستلمون. إرسال البريد متوقف حتى إضافة مستلمين وحفظهم.')}</Alert>}
        {recipients.map((row, index) => <Stack key={index} direction={{ xs: 'column', sm: 'row' }} sx={{ gap: 2, alignItems: { sm: 'center' } }}>
          <TextField label={t('User / group name', 'اسم المستخدم أو المجموعة')} value={row.name} disabled={busy} inputProps={{ maxLength: 200 }} onChange={e => change(recipients.map((r, i) => i === index ? { ...r, name: e.target.value } : r))} fullWidth />
          <TextField label={t('Email', 'البريد الإلكتروني')} type="email" required value={row.email} disabled={busy} inputProps={{ maxLength: 254, dir: 'ltr' }} onChange={e => change(recipients.map((r, i) => i === index ? { ...r, email: e.target.value } : r))} fullWidth />
          <Button color="error" startIcon={<Delete />} disabled={busy} onClick={() => change(recipients.filter((_, i) => i !== index))}>{t('Remove', 'إزالة')}</Button>
        </Stack>)}
        <Stack direction="row" sx={{ gap: 2, flexWrap: 'wrap' }}>
          <Button startIcon={<Add />} disabled={busy || revision === null || recipients.length >= 500} onClick={() => change([...recipients, { name: '', email: '' }])}>{t('Add recipient', 'إضافة مستلم')}</Button>
          <Button type="submit" variant="contained" startIcon={<Save />} disabled={busy || revision === null || !dirty}>{busy ? t('Saving...', 'جارٍ الحفظ...') : t('Save audience', 'حفظ المستلمين')}</Button>
          <Button disabled={busy} onClick={() => { if (!dirty || window.confirm(t('Discard unsaved changes?', 'تجاهل التعديلات غير المحفوظة؟'))) navigate('/daily-brief'); }}>{t('Back', 'رجوع')}</Button>
        </Stack>
      </Stack>
    </Box></CardContent></Card>
  </Box>;
}
