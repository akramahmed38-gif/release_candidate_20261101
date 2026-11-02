import React, { useEffect, useState } from 'react';
import { ThumbDownAltOutlined, ThumbUpAltOutlined } from '@mui/icons-material';
import { Alert, Box, Button, Snackbar, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { useLanguage } from '../context/LanguageContext';
import { dailyBriefService } from '../services/auth';

const initialFeedback = (brief) => ({ reaction: brief.current_user_reaction || null, comment: brief.current_user_comment || '' });

export default function DailyBriefFeedback({ brief }) {
  const { t } = useLanguage();
  const [reaction, setReaction] = useState(brief.current_user_reaction || null);
  const [comment, setComment] = useState(brief.current_user_comment || '');
  const [saved, setSaved] = useState(() => initialFeedback(brief));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [showSuccess, setShowSuccess] = useState(false);

  useEffect(() => {
    const value = initialFeedback(brief);
    setReaction(value.reaction);
    setComment(value.comment);
    setSaved(value);
  }, [brief.id, brief.current_user_reaction, brief.current_user_comment]);

  const normalizedComment = comment.trim();
  const hasChanges = reaction !== saved.reaction || normalizedComment !== saved.comment.trim();

  const submitFeedback = async (event) => {
    event.preventDefault();
    if (!hasChanges || saving) return;
    setSaving(true);
    setError('');
    try {
      const response = await dailyBriefService.saveFeedback(brief.id, { reaction, comment: normalizedComment || null });
      const value = { reaction: response.data.reaction || null, comment: response.data.comment || '' };
      setReaction(value.reaction);
      setComment(value.comment);
      setSaved(value);
      setShowSuccess(true);
    } catch (saveError) {
      setError(saveError.response?.data?.detail || saveError.response?.data?.message || t('Unable to save your feedback. Please try again.', 'تعذر حفظ ملاحظاتك. يرجى المحاولة مرة أخرى.'));
    } finally {
      setSaving(false);
    }
  };

  return <Box component="form" onSubmit={submitFeedback} sx={{ mt: { xs: 2, md: 3 }, p: { xs: 2, sm: 2.5 }, maxWidth: 960, border: '1px solid #dfe4ea', borderRadius: 2.5, bgcolor: '#fff' }}>
    <Typography variant="h6" sx={{ color: '#102a56', fontWeight: 800, mb: 1.5 }}>{t('Was this Daily Brief helpful?', 'هل كان هذا الملخص اليومي مفيدًا؟')}</Typography>
    <Stack spacing={2} alignItems="flex-start">
      <ToggleButtonGroup exclusive size="small" value={reaction} onChange={(_, value) => setReaction(value)} aria-label={t('Daily Brief reaction', 'التفاعل مع الملخص اليومي')} sx={{ '& .MuiToggleButton-root': { px: 1.75, py: 0.9, textTransform: 'none', fontWeight: 700, color: '#40536e', borderColor: '#cbd5e1' }, '& .Mui-selected': { color: '#0b4fa8 !important', bgcolor: '#eaf3ff !important' } }}>
        <ToggleButton value="LIKE" aria-label={t('Like', 'أعجبني')}><ThumbUpAltOutlined fontSize="small" sx={{ mr: 0.75 }} />{t('Like', 'أعجبني')}</ToggleButton>
        <ToggleButton value="UNLIKE" aria-label={t('Unlike', 'لم يعجبني')}><ThumbDownAltOutlined fontSize="small" sx={{ mr: 0.75 }} />{t('Unlike', 'لم يعجبني')}</ToggleButton>
      </ToggleButtonGroup>
      <TextField fullWidth size="small" multiline minRows={2} maxRows={4} label={t('Comment (optional)', 'تعليق (اختياري)')} value={comment} onChange={(event) => setComment(event.target.value)} inputProps={{ maxLength: 4000 }} />
      {error && <Alert severity="error" sx={{ width: '100%' }}>{error}</Alert>}
      <Button type="submit" variant="contained" disabled={!hasChanges || saving} sx={{ borderRadius: 2, px: 2.25, bgcolor: '#0b4fa8', fontWeight: 800, '&:hover': { bgcolor: '#083a7a' } }}>
        {saving ? t('Saving...', 'جارٍ الحفظ...') : t('Submit Feedback', 'إرسال الملاحظات')}
      </Button>
    </Stack>
    <Snackbar open={showSuccess} autoHideDuration={3500} onClose={() => setShowSuccess(false)} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
      <Alert severity="success" variant="filled" onClose={() => setShowSuccess(false)}>{t('Your feedback has been saved.', 'تم حفظ ملاحظاتك.')}</Alert>
    </Snackbar>
  </Box>;
}