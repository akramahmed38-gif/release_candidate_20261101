import React, { useEffect, useState } from 'react';
import { Add, ArrowBack, DeleteOutline, EditOutlined, Search } from '@mui/icons-material';
import { Alert, Box, Button, Card, CardContent, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, InputLabel, MenuItem, Select, Stack, TextField, Typography } from '@mui/material';
import { examService } from '../../services/auth';
import { useLanguage } from '../../context/LanguageContext';

const emptyQuestion = { question_text: '', question_type: 'MCQ', points: 1, choices: [{ choice_text: '', is_correct: true }, { choice_text: '', is_correct: false }] };

export default function QuestionBank() {
  const { t } = useLanguage();
  const tr = (en, ar) => t(en, ar);
  const [groups, setGroups] = useState([]);
  const [items, setItems] = useState([]);
  const [activeGroup, setActiveGroup] = useState(null);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState([]);
  const [destination, setDestination] = useState('');
  const [groupForm, setGroupForm] = useState(null);
  const [questionForm, setQuestionForm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setBusy(true); setError('');
    try {
      const [groupResponse, bankResponse] = await Promise.all([examService.getQuestionBankGroups(), examService.getQuestionBank()]);
      setGroups(groupResponse.data.groups || []);
      setItems(bankResponse.data.items || []);
    } catch (cause) {
      setError(cause.response?.data?.detail || tr('Unable to load Question Bank.', 'تعذر تحميل بنك الأسئلة.'));
    } finally { setBusy(false); }
  };
  useEffect(() => { load(); }, []);

  const saveGroup = async () => {
    if (!groupForm?.name.trim()) return;
    setBusy(true); setError('');
    try {
      const payload = { name: groupForm.name.trim(), description: groupForm.description.trim() };
      if (groupForm.group_id) await examService.updateQuestionBankGroup(groupForm.group_id, payload);
      else await examService.createQuestionBankGroup(payload);
      setGroupForm(null);
      await load();
    } catch (cause) { setError(cause.response?.data?.detail || tr('Unable to save group.', 'تعذر حفظ المجموعة.')); }
    finally { setBusy(false); }
  };
  const deleteGroup = async (group) => {
    if (!window.confirm(tr(`Delete ${group.name}? Its questions will move to General Bank.`, `حذف ${group.name}؟ ستُنقل أسئلتها إلى البنك العام.`))) return;
    setBusy(true); setError('');
    try { await examService.deleteQuestionBankGroup(group.group_id); setActiveGroup(null); setSelected([]); await load(); }
    catch (cause) { setError(cause.response?.data?.detail || tr('Unable to delete group.', 'تعذر حذف المجموعة.')); }
    finally { setBusy(false); }
  };
  const moveQuestions = async (ids) => {
    if (!destination || !ids.length) return;
    setBusy(true); setError('');
    try { await examService.moveQuestionBankItems(ids, destination); setSelected([]); await load(); }
    catch (cause) { setError(cause.response?.data?.detail || tr('Unable to move questions.', 'تعذر نقل الأسئلة.')); }
    finally { setBusy(false); }
  };
  const saveQuestion = async () => {
    if (!questionForm?.question_text.trim() || !activeGroup) return;
    setBusy(true); setError('');
    try {
      const payload = {
        question_text: questionForm.question_text.trim(), question_type: questionForm.question_type,
        points: Number(questionForm.points), question_group: activeGroup.name,
        is_favorite: Boolean(questionForm.is_favorite),
        choices: questionForm.question_type === 'Essay' ? null : questionForm.choices.map((choice) => ({ choice_text: choice.choice_text.trim(), is_correct: choice.is_correct })),
      };
      if (questionForm.bank_question_id) await examService.updateQuestionBankItem(questionForm.bank_question_id, payload);
      else await examService.createQuestionBankItem(payload);
      setQuestionForm(null);
      await load();
    } catch (cause) { setError(cause.response?.data?.signal || tr('Unable to save question.', 'تعذر حفظ السؤال.')); }
    finally { setBusy(false); }
  };
  const deleteQuestion = async (item) => {
    if (!window.confirm(tr('Delete this bank question?', 'حذف هذا السؤال من البنك؟'))) return;
    try { await examService.deleteQuestionBankItem(item.bank_question_id); await load(); }
    catch (cause) { setError(cause.response?.data?.signal || tr('Unable to delete question.', 'تعذر حذف السؤال.')); }
  };
  const activeItems = items.filter((item) => item.group_id === activeGroup?.group_id && (!query || item.question_text.toLowerCase().includes(query.toLowerCase())));
  const visibleGroups = groups.filter((group) => !query || `${group.name} ${group.description}`.toLowerCase().includes(query.toLowerCase()));
  const setChoice = (index, change) => setQuestionForm((form) => ({ ...form, choices: form.choices.map((choice, current) => current === index ? { ...choice, ...change } : change.is_correct ? { ...choice, is_correct: false } : choice) }));

  return <Box sx={{ maxWidth: 1240, mx: 'auto', py: 3 }}>
    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} gap={2}>
      <Box><Typography variant="h4" fontWeight={800}>{activeGroup ? <Button startIcon={<ArrowBack />} onClick={() => { setActiveGroup(null); setSelected([]); setQuery(''); }}>{tr('Question Bank', 'بنك الأسئلة')}</Button> : tr('Question Bank', 'بنك الأسئلة')}{activeGroup && ` / ${activeGroup.name}`}</Typography><Typography color="text.secondary">{activeGroup?.description || tr('Organize and reuse exam questions by group.', 'نظّم أسئلة الاختبارات وأعد استخدامها حسب المجموعة.')}</Typography></Box>
      <Button variant="contained" startIcon={<Add />} onClick={() => activeGroup ? setQuestionForm({ ...emptyQuestion, choices: emptyQuestion.choices.map((choice) => ({ ...choice })) }) : setGroupForm({ name: '', description: '' })}>{activeGroup ? tr('Add Question', 'إضافة سؤال') : tr('New Group', 'مجموعة جديدة')}</Button>
    </Stack>
    {error && <Alert severity="error" sx={{ mt: 2 }} onClose={() => setError('')}>{error}</Alert>}
    <TextField fullWidth size="small" sx={{ my: 2 }} label={activeGroup ? tr('Search questions', 'ابحث عن سؤال') : tr('Search groups', 'ابحث عن مجموعة')} value={query} onChange={(event) => setQuery(event.target.value)} InputProps={{ startAdornment: <Search sx={{ mr: 1, color: 'text.secondary' }} /> }} />
    {busy && <Typography color="text.secondary">{tr('Loading...', 'جارٍ التحميل...')}</Typography>}
    {!activeGroup ? <Stack spacing={1.25}>{visibleGroups.map((group) => <Card key={group.group_id} variant="outlined"><CardContent sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2, flexWrap: 'wrap' }}><Box><Typography fontWeight={800}>{group.name}</Typography><Typography variant="body2" color="text.secondary">{group.question_count} {tr('Questions', 'أسئلة')}{group.description ? ` · ${group.description}` : ''}</Typography></Box><Stack direction="row" spacing={1}><Button onClick={() => { setActiveGroup(group); setQuery(''); }}>{tr('Open', 'فتح')}</Button><Button startIcon={<EditOutlined />} onClick={() => setGroupForm({ ...group })}>{tr('Edit', 'تعديل')}</Button>{!group.is_system && <Button color="error" startIcon={<DeleteOutline />} onClick={() => deleteGroup(group)}>{tr('Delete', 'حذف')}</Button>}</Stack></CardContent></Card>)}{!visibleGroups.length && !busy && <Typography>{tr('No groups found.', 'لا توجد مجموعات.')}</Typography>}</Stack>
      : <Stack spacing={1.25}>
        <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap"><Typography>{activeItems.length} {tr('Questions', 'أسئلة')}</Typography><FormControl size="small" sx={{ minWidth: 180 }}><InputLabel>{tr('Move to Group', 'النقل إلى مجموعة')}</InputLabel><Select label={tr('Move to Group', 'النقل إلى مجموعة')} value={destination} onChange={(event) => setDestination(event.target.value)}>{groups.filter((group) => group.group_id !== activeGroup.group_id).map((group) => <MenuItem key={group.group_id} value={group.group_id}>{group.name}</MenuItem>)}</Select></FormControl><Button disabled={!destination || !selected.length || busy} onClick={() => moveQuestions(selected)}>{tr('Move Selected', 'نقل المحدد')} ({selected.length})</Button></Stack>
        {activeItems.map((item) => <Card key={item.bank_question_id} variant="outlined"><CardContent sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><Checkbox aria-label={tr(`Select ${item.question_text}`, `تحديد ${item.question_text}`)} checked={selected.includes(item.bank_question_id)} onChange={(event) => setSelected((previous) => event.target.checked ? [...previous, item.bank_question_id] : previous.filter((id) => id !== item.bank_question_id))} /><Box sx={{ flex: 1, minWidth: 0 }}><Typography fontWeight={700}>{item.question_text}</Typography><Typography variant="body2" color="text.secondary">{item.question_type} · {item.points} {tr('points', 'نقاط')}</Typography></Box><Button onClick={() => setQuestionForm({ ...item, choices: (item.choices || []).map((choice) => ({ ...choice })) })}>{tr('Edit', 'تعديل')}</Button><Button color="error" onClick={() => deleteQuestion(item)}>{tr('Delete', 'حذف')}</Button></CardContent></Card>)}
        {!activeItems.length && !busy && <Typography>{tr('No questions found in this group.', 'لا توجد أسئلة في هذه المجموعة.')}</Typography>}
      </Stack>}
    <Dialog open={Boolean(groupForm)} onClose={() => setGroupForm(null)} fullWidth maxWidth="sm"><DialogTitle>{groupForm?.group_id ? tr('Edit Group', 'تعديل المجموعة') : tr('New Group', 'مجموعة جديدة')}</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}><TextField autoFocus fullWidth label={tr('Group Name', 'اسم المجموعة')} value={groupForm?.name || ''} onChange={(event) => setGroupForm({ ...groupForm, name: event.target.value })} /><TextField fullWidth multiline rows={2} label={tr('Description', 'الوصف')} value={groupForm?.description || ''} onChange={(event) => setGroupForm({ ...groupForm, description: event.target.value })} /></Stack></DialogContent><DialogActions><Button onClick={() => setGroupForm(null)}>{tr('Cancel', 'إلغاء')}</Button><Button variant="contained" disabled={busy || !groupForm?.name.trim()} onClick={saveGroup}>{tr('Save', 'حفظ')}</Button></DialogActions></Dialog>
    <Dialog open={Boolean(questionForm)} onClose={() => setQuestionForm(null)} fullWidth maxWidth="sm"><DialogTitle>{questionForm?.bank_question_id ? tr('Edit Question', 'تعديل السؤال') : tr('Add Question', 'إضافة سؤال')}</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}><TextField fullWidth multiline label={tr('Question', 'السؤال')} value={questionForm?.question_text || ''} onChange={(event) => setQuestionForm({ ...questionForm, question_text: event.target.value })} /><TextField select fullWidth label={tr('Type', 'النوع')} value={questionForm?.question_type || 'MCQ'} onChange={(event) => setQuestionForm({ ...questionForm, question_type: event.target.value })}>{['MCQ', 'TF', 'Essay'].map((type) => <MenuItem key={type} value={type}>{type}</MenuItem>)}</TextField><TextField type="number" fullWidth label={tr('Points', 'النقاط')} value={questionForm?.points || 1} onChange={(event) => setQuestionForm({ ...questionForm, points: event.target.value })} inputProps={{ min: 1 }} />{questionForm?.question_type !== 'Essay' && questionForm?.choices.map((choice, index) => <Stack key={index} direction="row" alignItems="center" spacing={1}><Checkbox checked={Boolean(choice.is_correct)} onChange={() => setChoice(index, { is_correct: true })} /><TextField fullWidth label={`${tr('Choice', 'اختيار')} ${index + 1}`} value={choice.choice_text} onChange={(event) => setChoice(index, { choice_text: event.target.value })} /></Stack>)}{questionForm?.question_type === 'MCQ' && <Button onClick={() => setQuestionForm({ ...questionForm, choices: [...questionForm.choices, { choice_text: '', is_correct: false }] })}>{tr('Add Choice', 'إضافة اختيار')}</Button>}</Stack></DialogContent><DialogActions><Button onClick={() => setQuestionForm(null)}>{tr('Cancel', 'إلغاء')}</Button><Button variant="contained" disabled={busy || !questionForm?.question_text.trim()} onClick={saveQuestion}>{tr('Save', 'حفظ')}</Button></DialogActions></Dialog>
  </Box>;
}
