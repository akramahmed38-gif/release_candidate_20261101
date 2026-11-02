import React, { useEffect, useRef, useState } from 'react';
import { Add, Archive, Delete, Edit, Email, FileDownload, Insights, Preview, Restore } from '@mui/icons-material';
import { Alert, Box, Button, Card, CardContent, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, Stack, Skeleton, Tab, Tabs, TextField, Typography } from '@mui/material';
import { useLocation, useNavigate } from 'react-router-dom';
import { dailyBriefService } from '../services/auth';
import { useLanguage } from '../context/LanguageContext';
import { adminArabic } from './adminTranslations';
import DailyBriefActions from './DailyBriefActions';
import DailyBriefAnalyticsDialog from './DailyBriefAnalyticsDialog';
import DailyBriefEmailProgress from './DailyBriefEmailProgress';


export default function DailyBriefAdmin() {
  const { t, isArabic } = useLanguage();
  const tr = (text) => t(text, adminArabic[text] || text);
  const formatViewedAt = (value) => value ? new Intl.DateTimeFormat(isArabic ? 'ar-EG' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : tr('Unknown');
  const navigate = useNavigate();
  const location = useLocation();
  const [tab, setTab] = useState(['DRAFT', 'LIVE', 'ARCHIVED'].includes(location.state?.tab) ? location.state.tab : 'LIVE'); const [items, setItems] = useState([]); const [summary, setSummary] = useState(() => dailyBriefService.peekSummary()); const [search, setSearch] = useState('');
  const [analytics, setAnalytics] = useState(null); const [analyticsTitle, setAnalyticsTitle] = useState(''); const [analyticsBriefId, setAnalyticsBriefId] = useState(''); const [analyticsError, setAnalyticsError] = useState(''); const [analyticsLoading, setAnalyticsLoading] = useState(false); const [analyticsExportLoading, setAnalyticsExportLoading] = useState(false);
  const [analyticsDisplay, setAnalyticsDisplay] = useState(null); const [analyticsDisplayError, setAnalyticsDisplayError] = useState(''); const [analyticsDisplayLoading, setAnalyticsDisplayLoading] = useState(false);
  const [notification, setNotification] = useState(location.state?.message ? { severity: 'success', message: location.state.message } : null);
  const [emailProgress, setEmailProgress] = useState(null);
  const [emailSending, setEmailSending] = useState(false);
  const listSequence = useRef(0);
  const countSequence = useRef(0);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [countError, setCountError] = useState('');
  const loadCounts = async () => {
    const sequence = ++countSequence.current;
    setCountError('');
    try {
      const counts = await dailyBriefService.getSummary();
      if (sequence === countSequence.current) setSummary(counts.data);
    } catch {
      if (sequence === countSequence.current) setCountError('Counts could not be refreshed.');
    }
  };
  const loadList = async () => {
    const sequence = ++listSequence.current;
    setListLoading(true);
    setListError('');
    try {
      const list = await dailyBriefService.listBriefs({ status: tab, search });
      if (sequence === listSequence.current) setItems(list.data.items || []);
    } catch {
      if (sequence === listSequence.current) setListError('Daily Briefs could not be loaded.');
    } finally {
      if (sequence === listSequence.current) setListLoading(false);
    }
  };
  const load = () => Promise.all([loadList(), loadCounts()]);
  useEffect(() => {
    loadList();
    return () => { listSequence.current += 1; };
  }, [tab]);
  useEffect(() => {
    loadCounts();
    const refreshCounts = () => { if (document.visibilityState !== 'hidden') loadCounts(); };
    window.addEventListener('focus', refreshCounts);
    const timer = window.setInterval(refreshCounts, 15000);
    return () => {
      countSequence.current += 1;
      window.removeEventListener('focus', refreshCounts);
      window.clearInterval(timer);
    };
  }, []);
  const restore = async (id) => { if (window.confirm(tr('Make this archived Daily Brief live? The current Live Brief will be archived.'))) { try { await dailyBriefService.restoreLiveBrief(id); loadCounts(); setTab('LIVE'); setNotification({ severity: 'success', message: 'Daily Brief is now Live. No email has been sent.' }); } catch (error) { setNotification({ severity: 'error', message: error.response?.data?.detail || error.message || 'Unable to make this brief Live.' }); } } };
  const deleteBrief = async (item) => { const message = item.status === 'LIVE' ? 'Delete this Live Daily Brief? Retail users will no longer see it.' : 'Delete this Daily Brief?'; if (window.confirm(tr(message))) { try { await dailyBriefService.deleteBrief(item.id); await load(); } catch (error) { window.alert(tr(error.response?.data?.detail || 'Unable to delete Daily Brief.')); } } };
  const viewAnalytics = async (item) => { setAnalyticsTitle(item.title); setAnalyticsBriefId(item.id); setAnalyticsDisplay(null); setAnalyticsDisplayError(''); setAnalyticsDisplayLoading(true); try { const response = await dailyBriefService.getAnalytics(item.id); setAnalyticsDisplay(response.data); } catch (error) { setAnalyticsDisplayError(error.response?.data?.detail || 'Unable to load viewer statistics.'); } finally { setAnalyticsDisplayLoading(false); } };
  const closeAnalytics = () => { if (!analyticsDisplayLoading && !analyticsExportLoading) { setAnalyticsDisplay(null); setAnalyticsBriefId(''); setAnalyticsDisplayError(''); } };
  const exportAnalytics = async () => {
    if (!analyticsBriefId || analyticsExportLoading) return;
    setAnalyticsExportLoading(true);
    try {
      const response = await dailyBriefService.exportAnalytics(analyticsBriefId);
      const downloadUrl = window.URL.createObjectURL(new Blob([response.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
      const link = document.createElement('a');
      const timestamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
      link.href = downloadUrl;
      link.download = `daily-brief-viewers-${timestamp}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
    } catch (error) {
      setNotification({ severity: 'error', message: error.response?.data?.detail || 'Unable to export the viewer report.' });
    } finally {
      setAnalyticsExportLoading(false);
    }
  };
  const notifyRetail = async (item) => {
    if (emailSending || (emailProgress?.brief.id === item.id && !['COMPLETED', 'COMPLETED_WITH_ERRORS'].includes(emailProgress.status))) return;
    if (!window.confirm(t(`Send the Daily Brief email for "${item.title}" to the approved recipients?`, `هل تريد إرسال بريد الملخص اليومي «${item.title}» إلى المستلمين المعتمدين؟`))) return;
    setEmailSending(true);
    setEmailProgress({ brief: item, id: null, status: 'STARTING', open: true, error: '' });
    try {
      const response = await dailyBriefService.notifyRetail(item.id);
      if (!response.data?.batch_id) throw new Error('Email status unavailable: no batch ID returned. Check Action history before sending again.');
      setEmailProgress({ brief: item, id: response.data.batch_id, status: 'PENDING', open: true, error: '' });
    } catch (error) {
      setEmailProgress((previous) => ({ ...previous, status: 'UNKNOWN', error: error.response?.data?.detail || error.message || 'Unable to confirm whether email sending started. Check Action history before sending again.' }));
    } finally {
      setEmailSending(false);
    }
  };
  return <><DailyBriefEmailProgress open={Boolean(emailProgress?.open)} brief={emailProgress?.brief} batchId={emailProgress?.id} startError={emailProgress?.error} onClose={() => setEmailProgress((previous) => previous && { ...previous, open: false })} onStatus={(status) => setEmailProgress((previous) => previous && { ...previous, status })} /><DailyBriefAnalyticsDialog key={analyticsBriefId || 'daily-brief-analytics'} open={analyticsDisplayLoading || Boolean(analyticsDisplay) || Boolean(analyticsDisplayError)} title={analyticsTitle} analytics={analyticsDisplay} loading={analyticsDisplayLoading} error={analyticsDisplayError} exportLoading={analyticsExportLoading} onExport={exportAnalytics} onClose={closeAnalytics} translate={tr} isArabic={isArabic} /><Box sx={{ maxWidth: 1240, mx: 'auto', py: 2 }}>
    <Stack direction="row" justifyContent="space-between"><Box><Typography variant="h4" fontWeight={800}>{tr('Daily Brief')}</Typography><Typography color="text.secondary">{tr('Create, manage and publish Retail communications.')}</Typography></Box><Stack direction="row" sx={{ gap: 2, flexWrap: 'wrap' }}><Button onClick={() => navigate('/daily-brief/audience')}>{t('Manage audience', 'إدارة المستلمين')}</Button><Button variant="contained" startIcon={<Add />} onClick={() => navigate('/daily-brief/new')}>{tr('Create Daily Brief')}</Button></Stack></Stack>
    {notification && <Alert severity={notification.severity} onClose={() => setNotification(null)} sx={{ mt: 2 }}>{isArabic && notification.arabicMessage ? notification.arabicMessage : tr(notification.message)}</Alert>}
    <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: { xs: 1, sm: 2 }, width: '100%', maxWidth: 528, my: 2 }}>
      {[['Live', summary?.live], ['Draft', summary?.drafts], ['Archived', summary?.archived]].map(([name, value]) => <Card key={name} sx={{ minWidth: 0 }}>
        <CardContent sx={{ boxSizing: 'border-box', minHeight: { xs: 112, sm: 128 }, p: { xs: 1.5, sm: 2.5 }, '&:last-child': { pb: { xs: 1.5, sm: 2.5 } } }}>
          <Typography color="text.secondary" sx={{ fontSize: { xs: 14, sm: 16 }, mb: 1 }}>{tr(name)}</Typography>
          <Typography variant="h4" fontWeight={800} aria-label={t(`${name} count`, `عدد ${tr(name)}`)} sx={{ fontSize: value == null && countError ? 14 : { xs: 24, sm: 34 }, lineHeight: 1.2, fontVariantNumeric: 'tabular-nums', overflowWrap: 'anywhere' }}>{value ?? (countError ? tr('Unavailable') : <Skeleton width="4ch" />)}</Typography>
        </CardContent>
      </Card>)}
    </Box>
    {countError && <Alert severity="warning" action={<Button onClick={loadCounts}>{tr('Retry')}</Button>} sx={{ mb: 2 }}>{tr(countError)}{summary ? tr(' Showing the last loaded counts.') : ''}</Alert>}
    {listError && <Alert severity="error" action={<Button onClick={loadList}>{tr('Retry')}</Button>} sx={{ mb: 2 }}>{tr(listError)}</Alert>}
    <Card><CardContent><Stack direction="row" justifyContent="space-between"><Tabs value={tab} onChange={(_, value) => setTab(value)}><Tab value="LIVE" label={tr('Live')} /><Tab value="DRAFT" label={tr('Draft')} /><Tab value="ARCHIVED" label={tr('Archived')} /></Tabs><TextField size="small" label={tr('Search by title')} value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && load()} /></Stack><Stack spacing={1} sx={{ mt: 2 }}>{!listLoading && !listError && items.length === 0 && <Typography role="status" color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>{tr('No records found in this section.')}</Typography>}{listLoading ? <Skeleton variant="rounded" height={90} aria-label={tr('Loading Daily Briefs')} /> : items.map((item) => <Card key={item.id} variant="outlined"><CardContent><Stack direction={{ xs: 'column', md: 'row' }} sx={{ gap: 2 }} justifyContent="space-between" alignItems="center"><Box sx={{ minWidth: 0, overflowWrap: 'anywhere' }}><Typography component="div" fontWeight={800}>{item.title} <Chip size="small" label={tr(item.status)} /></Typography><Typography variant="body2" color="text.secondary">{tr('Brief date:')} {item.brief_date}</Typography></Box><Stack direction="row" sx={{ gap: 1, flexWrap: 'wrap', justifyContent: 'flex-end', '& .MuiButton-root': { whiteSpace: 'nowrap' } }}>{item.status === 'LIVE' && <Button startIcon={<Email />} disabled={emailSending || (emailProgress?.brief.id === item.id && !['COMPLETED', 'COMPLETED_WITH_ERRORS'].includes(emailProgress.status))} onClick={() => notifyRetail(item)}>{tr('Send Brief Email')}</Button>}{emailProgress?.brief.id === item.id && <Button onClick={() => setEmailProgress((previous) => ({ ...previous, open: true }))}>{t('View email status', 'عرض حالة البريد')}</Button>}<Button startIcon={<Preview />} onClick={() => navigate(`/daily-brief/${item.id}/preview`)}>{tr('Preview')}</Button>{['DRAFT', 'LIVE', 'ARCHIVED'].includes(item.status) && <Button startIcon={<Edit />} onClick={() => navigate(`/daily-brief/${item.id}/edit`)}>{tr('Edit')}</Button>}<Button startIcon={<Insights />} onClick={() => viewAnalytics(item)}>{tr('Viewed by')}</Button><DailyBriefActions brief={item} />{item.status === 'LIVE' && <Button startIcon={<Archive />} onClick={() => dailyBriefService.archiveBrief(item.id).then(load)}>{tr('Archive')}</Button>}{item.status === 'ARCHIVED' && <Button color="success" startIcon={<Restore />} onClick={() => restore(item.id)}>{tr('Make Live')}</Button>}<Button color="error" startIcon={<Delete />} onClick={() => deleteBrief(item)}>{tr('Delete')}</Button></Stack></Stack></CardContent></Card>)}</Stack></CardContent></Card>
    <Dialog open={analyticsLoading || Boolean(analytics) || Boolean(analyticsError)} onClose={closeAnalytics} maxWidth="sm" fullWidth><DialogTitle>{tr('Viewed by')}{analyticsTitle ? `: ${analyticsTitle}` : ''}</DialogTitle><DialogContent dividers>{analyticsLoading ? <Typography>{tr('Loading viewer statistics...')}</Typography> : analyticsError ? <Alert severity="error">{tr(analyticsError)}</Alert> : analytics && <><Stack direction="row" spacing={1.5} sx={{ mb: 2 }}><Box sx={{ minWidth: 110, p: 1.5, borderRadius: 2, bgcolor: '#f5f7fa' }}><Typography variant="caption" color="text.secondary">{tr('Viewed')}</Typography><Typography variant="h5" fontWeight={800}>{analytics.viewed}</Typography></Box><Box sx={{ minWidth: 110, p: 1.5, borderRadius: 2, bgcolor: '#f5f7fa' }}><Typography variant="caption" color="text.secondary">{tr('Eligible Retail')}</Typography><Typography variant="h5" fontWeight={800}>{analytics.eligible_retail_users}</Typography></Box></Stack><Divider sx={{ mb: 1 }} />{analytics.viewed_users?.length ? analytics.viewed_users.map((viewer) => <Box key={`${viewer.hr_id}-${viewer.first_viewed_at}`} sx={{ py: 1.25 }}><Typography fontWeight={800}>{viewer.name || tr('Unknown user')}</Typography><Typography variant="body2" color="text.secondary">{tr('HR ID:')} {viewer.hr_id || tr('Not available')} · {tr('Viewed')} {formatViewedAt(viewer.first_viewed_at)}</Typography></Box>) : <Typography color="text.secondary">{tr('No Retail users have viewed this Brief yet.')}</Typography>}</>}</DialogContent><DialogActions><Button startIcon={<FileDownload />} onClick={exportAnalytics} disabled={analyticsLoading || analyticsExportLoading || !analyticsBriefId}>{analyticsExportLoading ? tr('Exporting...') : tr('Export Excel')}</Button><Button onClick={closeAnalytics} disabled={analyticsLoading || analyticsExportLoading}>{tr('Close')}</Button></DialogActions></Dialog>
  </Box></>;
}
