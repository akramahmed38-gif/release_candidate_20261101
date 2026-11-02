import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert, Box, Button, ButtonBase, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControl, IconButton, InputLabel, MenuItem, Paper, Select, Stack, TextField,
  Tooltip, Typography,
} from '@mui/material';
import {
  AccountBalanceWalletOutlined, Add, ArrowBack, BusinessCenterOutlined, CheckCircleOutline,
  CreditCardOutlined, DeleteOutline, EditOutlined, GroupsOutlined, ManageAccountsOutlined,
  MenuBookOutlined, MonitorHeartOutlined, ReceiptLongOutlined, Search, SettingsOutlined,
  TrendingUpOutlined, VolumeUpOutlined,
} from '@mui/icons-material';
import { authService, businessVocabularyService } from '../services/auth';
import { useLanguage } from '../context/LanguageContext';

const CATEGORY_ICONS = {
  'Banking & Products': CreditCardOutlined,
  'Daily Operations': SettingsOutlined,
  'Cards & Banking': CreditCardOutlined,
  'Transactions & Payments': ReceiptLongOutlined,
  'Branch & People': GroupsOutlined,
  Operations: SettingsOutlined,
  Performance: TrendingUpOutlined,
  'System & Issues': MonitorHeartOutlined,
  Business: BusinessCenterOutlined,
};

const CATEGORY_AR = {
  'Banking & Products': 'الخدمات المصرفية والمنتجات',
  'Daily Operations': 'العمليات اليومية',
  'Cards & Banking': 'البطاقات والخدمات المصرفية',
  'Transactions & Payments': 'المعاملات والمدفوعات',
  'Branch & People': 'الفرع والفريق',
  Operations: 'العمليات',
  Performance: 'الأداء',
  'System & Issues': 'النظام والمشكلات',
  Business: 'الأعمال',
};

const emptyForm = { english_text: '', arabic_text: '', speech_text: '', category_id: '' };

function categoryLabel(category, isArabic) {
  return isArabic ? (category.arabic_name || category.name) : category.name;
}

function VocabularyActions({ item, speakingId, onSpeak, t, compact = false }) {
  const speaking = speakingId === item.id;
  return (
    <Stack direction="row" spacing={1} justifyContent={compact ? 'flex-start' : 'flex-end'}>
      <Button
        size="small"
        variant="outlined"
        startIcon={<VolumeUpOutlined fontSize="small" />}
        onClick={() => onSpeak(item, 0.96)}
        aria-label={`Listen to pronunciation of ${item.english_text}`}
        sx={{ borderRadius: 99, textTransform: 'none', minWidth: 96 }}
      >
        {speaking ? t('Speaking...', 'جارٍ النطق...') : t('Listen', 'استمع')}
      </Button>
    </Stack>
  );
}

export default function BusinessVocabulary() {
  const { t, isArabic } = useLanguage();
  const formLayoutSx = {
    direction: isArabic ? 'rtl' : 'ltr',
    '& .MuiInputLabel-root': { position: 'static', transform: 'none', maxWidth: '100%', mb: 1, fontSize: 14, lineHeight: 1.5, textAlign: 'start', whiteSpace: 'normal' },
    '& .MuiOutlinedInput-notchedOutline legend': { display: 'none' },
    '& .MuiOutlinedInput-notchedOutline': { top: 0 },
    '& .MuiFormHelperText-root': { textAlign: 'start', mx: 0 },
    '& .MuiSelect-select': { paddingInlineStart: '14px !important', paddingInlineEnd: '36px !important' },
    '& .MuiSelect-icon': { right: isArabic ? 'auto' : 7, left: isArabic ? 7 : 'auto' },
    '& .MuiButton-root': { columnGap: 1, whiteSpace: 'nowrap' },
    '& .MuiButton-startIcon, & .MuiButton-endIcon': { margin: '0 !important', flexShrink: 0 },
  };
  const currentUser = authService.getCurrentUser();
  const canManage = ['admin', 'auditor', 'hr'].includes(String(currentUser?.role || currentUser?.department || '').toLowerCase());
  const [categories, setCategories] = useState([]);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState(null);
  const [globalSearch, setGlobalSearch] = useState('');
  const [selectedCategoryId, setSelectedCategoryId] = useState(null);
  const [speakingId, setSpeakingId] = useState(null);
  const [voices, setVoices] = useState([]);
  const speechRequestRef = useRef(0);
  const speechTimerRef = useRef(null);
  const [manageMode, setManageMode] = useState(false);
  const [manageSearch, setManageSearch] = useState('');
  const [manageCategoryId, setManageCategoryId] = useState('all');
  const [formOpen, setFormOpen] = useState(false);
  const [categoryOpen, setCategoryOpen] = useState(false);
  const [categoryForm, setCategoryForm] = useState({ name: '', arabic_name: '', display_order: 0, is_active: true });
  const [categoryError, setCategoryError] = useState('');
  const [editingItem, setEditingItem] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);
  const [deleteItem, setDeleteItem] = useState(null);

  const loadVocabulary = async () => {
    setLoading(true);
    setError('');
    try {
      const [categoriesResponse, itemsResponse] = await Promise.all([
        businessVocabularyService.getCategories(),
        businessVocabularyService.getItems(),
      ]);
      setCategories(categoriesResponse.data.items || []);
      setItems(itemsResponse.data.items || []);
    } catch (requestError) {
      setError((typeof requestError.response?.data?.detail === 'string' ? requestError.response.data.detail : '') || t('Unable to load Business Vocabulary.', 'تعذر تحميل مفردات الأعمال.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadVocabulary(); }, []);

  useEffect(() => {
    if (!window.speechSynthesis) return undefined;
    const loadVoices = () => setVoices(window.speechSynthesis.getVoices());
    loadVoices();
    window.speechSynthesis.addEventListener('voiceschanged', loadVoices);
    return () => {
      window.speechSynthesis.removeEventListener('voiceschanged', loadVoices);
      window.clearTimeout(speechTimerRef.current);
      window.speechSynthesis.cancel();
    };
  }, []);

  const selectedCategory = categories.find((category) => category.id === selectedCategoryId) || null;
  const normalizedSearch = globalSearch.trim().toLocaleLowerCase();
  const globalResults = useMemo(() => items.filter((item) => (
    item.english_text.toLocaleLowerCase().includes(normalizedSearch)
    || item.arabic_text.includes(globalSearch.trim())
  )), [globalSearch, items, normalizedSearch]);
  const categoryItems = useMemo(() => items.filter((item) => (
    item.category_id === selectedCategoryId
    && (!normalizedSearch || item.english_text.toLocaleLowerCase().includes(normalizedSearch) || item.arabic_text.includes(globalSearch.trim()))
  )), [globalSearch, items, normalizedSearch, selectedCategoryId]);
  const manageItems = useMemo(() => items.filter((item) => {
    const matchesCategory = manageCategoryId === 'all' || item.category_id === manageCategoryId;
    const search = manageSearch.trim().toLocaleLowerCase();
    return matchesCategory && (!search || item.english_text.toLocaleLowerCase().includes(search) || item.arabic_text.includes(manageSearch.trim()));
  }), [items, manageCategoryId, manageSearch]);

  const speak = (item, rate) => {
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) {
      setNotice({ severity: 'warning', text: t('Pronunciation is not supported by this browser.', 'هذا المتصفح لا يدعم النطق الصوتي.') });
      return;
    }
    const requestId = speechRequestRef.current + 1;
    speechRequestRef.current = requestId;
    window.clearTimeout(speechTimerRef.current);
    window.speechSynthesis.cancel();
    setSpeakingId(item.id);

    // Some Chromium builds drop speech queued immediately after cancel(); this brief handoff is intentional.
    speechTimerRef.current = window.setTimeout(() => {
      if (speechRequestRef.current !== requestId) return;
      const utterance = new window.SpeechSynthesisUtterance(item.speech_text || item.english_text);
      utterance.lang = 'en-US';
      utterance.rate = rate;
      const preferredVoice = voices.find((voice) => voice.lang.toLowerCase() === 'en-us')
        || voices.find((voice) => voice.lang.toLowerCase().startsWith('en'));
      if (preferredVoice) utterance.voice = preferredVoice;
      const clearSpeaking = () => {
        if (speechRequestRef.current === requestId) setSpeakingId(null);
      };
      utterance.onend = clearSpeaking;
      utterance.onerror = clearSpeaking;
      window.speechSynthesis.speak(utterance);
    }, 80);
  };

  const openAdd = () => {
    setEditingItem(null);
    setForm({ ...emptyForm, category_id: selectedCategoryId || categories[0]?.id || '' });
    setFormError('');
    setFormOpen(true);
  };
  const openEdit = (item) => {
    setEditingItem(item);
    setForm({ english_text: item.english_text, arabic_text: item.arabic_text, speech_text: item.speech_text || '', category_id: item.category_id });
    setFormError('');
    setFormOpen(true);
  };
  const saveItem = async () => {
    if (!form.english_text.trim() || !form.arabic_text.trim() || !form.category_id) {
      setFormError(t('English, Arabic, and category are required.', 'الإنجليزية والعربية والفئة حقول مطلوبة.'));
      return;
    }
    setSaving(true);
    setFormError('');
    try {
      if (editingItem) await businessVocabularyService.updateItem(editingItem.id, form);
      else await businessVocabularyService.createItem(form);
      setFormOpen(false);
      setNotice({ severity: 'success', text: t(editingItem ? 'Vocabulary updated successfully.' : 'Vocabulary added successfully.', editingItem ? 'تم تحديث المفردة بنجاح.' : 'تمت إضافة المفردة بنجاح.') });
      await loadVocabulary();
    } catch (requestError) {
      setFormError((typeof requestError.response?.data?.detail === 'string' ? requestError.response.data.detail : '') || t('Unable to save vocabulary.', 'تعذر حفظ المفردة.'));
    } finally { setSaving(false); }
  };
  const saveCategory = async () => {
    if (!categoryForm.name.trim() || !categoryForm.arabic_name.trim()) {
      setCategoryError(t('English and Arabic category names are required.', 'اسم الفئة بالإنجليزية والعربية مطلوب.'));
      return;
    }
    setSaving(true); setCategoryError('');
    try {
      await businessVocabularyService.createCategory(categoryForm);
      setCategoryOpen(false);
      setCategoryForm({ name: '', arabic_name: '', display_order: 0, is_active: true });
      setNotice({ severity: 'success', text: t('Category created successfully.', 'تم إنشاء الفئة بنجاح.') });
      await loadVocabulary();
    } catch (requestError) {
      setCategoryError((typeof requestError.response?.data?.detail === 'string' ? requestError.response.data.detail : '') || t('Unable to create category.', 'تعذر إنشاء الفئة.'));
    } finally { setSaving(false); }
  };
  const confirmDelete = async () => {
    if (!deleteItem) return;
    try {
      await businessVocabularyService.deleteItem(deleteItem.id);
      setDeleteItem(null);
      setNotice({ severity: 'success', text: t('Vocabulary deleted successfully.', 'تم حذف المفردة بنجاح.') });
      await loadVocabulary();
    } catch (requestError) {
      setDeleteItem(null);
      setNotice({ severity: 'error', text: (typeof requestError.response?.data?.detail === 'string' ? requestError.response.data.detail : '') || t('Unable to delete vocabulary.', 'تعذر حذف المفردة.') });
    }
  };

  const renderRows = (displayItems, includeCategory = false, management = false) => (
    <Paper variant="outlined" sx={{ overflow: 'hidden', borderColor: 'rgba(31,53,88,0.14)', borderRadius: 3 }}>
      <Box sx={{ display: { xs: 'none', md: 'grid' }, gridTemplateColumns: management ? '1.2fr 1.15fr 0.9fr 1.15fr' : includeCategory ? '1fr 1fr 0.8fr 1fr' : '1.2fr 1.1fr 1fr', gap: 2, px: 2.5, py: 1.25, bgcolor: 'rgba(31,53,88,0.045)' }}>
        <Typography fontWeight={800}>{t('English', 'الإنجليزية')}</Typography>
        <Typography fontWeight={800}>{t('Arabic', 'العربية')}</Typography>
        {includeCategory && <Typography fontWeight={800}>{t('Category', 'الفئة')}</Typography>}
        <Typography fontWeight={800} textAlign={isArabic ? 'left' : 'right'}>{management ? t('Actions', 'الإجراءات') : t('Pronunciation', 'النطق')}</Typography>
      </Box>
      {displayItems.map((item, index) => (
        <Box key={item.id} sx={{ px: { xs: 2, md: 2.5 }, py: { xs: 1.75, md: 1.5 }, display: { md: 'grid' }, gridTemplateColumns: management ? '1.2fr 1.15fr 0.9fr 1.15fr' : includeCategory ? '1fr 1fr 0.8fr 1fr' : '1.2fr 1.1fr 1fr', gap: 2, alignItems: 'center', borderTop: index ? '1px solid rgba(31,53,88,0.10)' : 'none', '&:hover': { bgcolor: 'rgba(255,210,0,0.055)' } }}>
          <Typography dir="ltr" sx={{ fontWeight: 750, fontSize: { xs: 16, md: 17 }, color: 'secondary.main' }}>{item.english_text}</Typography>
          <Typography dir="rtl" sx={{ textAlign: isArabic ? 'right' : 'left', color: 'text.secondary', fontSize: 16 }}>{item.arabic_text}</Typography>
          {includeCategory && <Typography sx={{ mt: { xs: 1, md: 0 }, color: 'text.secondary' }}>{item.category_name}</Typography>}
          {management ? (
            <Stack direction="row" spacing={0.25} justifyContent={{ md: isArabic ? 'flex-start' : 'flex-end' }} sx={{ mt: { xs: 1, md: 0 } }}>
              <Tooltip title={t('Listen', 'استمع')}><IconButton onClick={() => speak(item, 0.96)} aria-label={`Listen to pronunciation of ${item.english_text}`} color="primary"><VolumeUpOutlined /></IconButton></Tooltip>
              <Tooltip title={t('Edit', 'تعديل')}><IconButton onClick={() => openEdit(item)} aria-label={`Edit ${item.english_text}`} color="primary"><EditOutlined /></IconButton></Tooltip>
              <Tooltip title={t('Delete', 'حذف')}><IconButton onClick={() => setDeleteItem(item)} aria-label={`Delete ${item.english_text}`} color="error"><DeleteOutline /></IconButton></Tooltip>
            </Stack>
          ) : <Box sx={{ mt: { xs: 1.25, md: 0 } }}><VocabularyActions item={item} speakingId={speakingId} onSpeak={speak} t={t} compact /></Box>}
        </Box>
      ))}
    </Paper>
  );

  if (loading) return <Box sx={{ minHeight: 420, display: 'grid', placeItems: 'center' }}><CircularProgress color="primary" /></Box>;

  return (
    <Box sx={{ ...formLayoutSx, maxWidth: 1240, mx: 'auto', px: { xs: 2, md: 3 }, py: { xs: 3, md: 5 }, direction: isArabic ? 'rtl' : 'ltr' }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'flex-start' }} spacing={2.25} sx={{ mb: 3.25 }}>
        <Box>
          <Stack direction="row" spacing={1.1} alignItems="center"><MenuBookOutlined color="primary" sx={{ fontSize: 31 }} /><Typography variant="h3" component="h1" sx={{ fontSize: { xs: 30, md: 38 }, fontWeight: 850 }}>{t('Business Vocabulary', 'مفردات الأعمال')}</Typography></Stack>
          <Typography sx={{ mt: 0.8, color: 'text.secondary', fontSize: { xs: 15, md: 17 } }}>{t('Common Business Language at Fawry Plus Branches', 'لغة الأعمال الشائعة في فروع فوري بلس')}</Typography>
        </Box>
        {canManage && <Button variant="outlined" startIcon={<ManageAccountsOutlined />} onClick={() => { setManageMode((value) => !value); setSelectedCategoryId(null); }} sx={{ borderRadius: 99, textTransform: 'none', fontWeight: 800, px: 2.15 }}>{manageMode ? t('Browse Vocabulary', 'استعراض المفردات') : t('Manage Vocabulary', 'إدارة المفردات')}</Button>}
      </Stack>

      {notice && <Alert severity={notice.severity} onClose={() => setNotice(null)} sx={{ mb: 2.25 }}>{notice.text}</Alert>}
      {error && <Alert severity="error" sx={{ mb: 2.25 }} action={<Button color="inherit" size="small" onClick={loadVocabulary}>{t('Retry', 'إعادة المحاولة')}</Button>}>{error}</Alert>}

      {manageMode ? <>
        <Paper sx={{ p: { xs: 2, md: 2.5 }, borderRadius: 3, mb: 2.25 }}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} justifyContent="space-between">
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} flex={1}>
              <TextField size="small" fullWidth placeholder={t('Search vocabulary...', 'ابحث في المفردات...')} value={manageSearch} onChange={(event) => setManageSearch(event.target.value)} InputProps={{ startAdornment: <Search sx={{ color: 'text.secondary', marginInlineEnd: 1 }} /> }} />
              <FormControl size="small" sx={{ minWidth: 220 }}><InputLabel>{t('Category', 'الفئة')}</InputLabel><Select value={manageCategoryId} label={t('Category', 'الفئة')} onChange={(event) => setManageCategoryId(event.target.value)}><MenuItem value="all">{t('All categories', 'كل الفئات')}</MenuItem>{categories.map((category) => <MenuItem key={category.id} value={category.id}>{categoryLabel(category, isArabic)}</MenuItem>)}</Select></FormControl>
            </Stack>
            <Stack direction="row" spacing={1}><Button variant="outlined" startIcon={<Add />} onClick={() => { setCategoryError(''); setCategoryOpen(true); }} sx={{ borderRadius: 99, textTransform: 'none', fontWeight: 800 }}>{t('Add Category', 'إضافة فئة')}</Button><Button variant="contained" startIcon={<Add />} onClick={openAdd} sx={{ borderRadius: 99, minWidth: 170, textTransform: 'none', fontWeight: 800 }}>{t('Add Vocabulary', 'إضافة مفردة')}</Button></Stack>
          </Stack>
        </Paper>
        {manageItems.length ? renderRows(manageItems, true, true) : <Paper sx={{ p: 5, textAlign: 'center', borderRadius: 3 }}><Typography color="text.secondary">{t('No matching vocabulary found.', 'لم يتم العثور على مفردات مطابقة.')}</Typography></Paper>}
      </> : selectedCategory ? <>
        <Button startIcon={<ArrowBack />} onClick={() => { setSelectedCategoryId(null); setGlobalSearch(''); }} sx={{ mb: 2, textTransform: 'none', fontWeight: 800 }}>{t('All categories', 'كل الفئات')}</Button>
        <Paper sx={{ p: { xs: 2.25, md: 3 }, borderRadius: 3, mb: 2.25, borderTop: '4px solid', borderColor: 'primary.main' }}>
          <Typography variant="h5" fontWeight={850}>{categoryLabel(selectedCategory, isArabic)}</Typography>
          <Typography color="text.secondary" sx={{ mt: 0.35 }}>{selectedCategory.item_count} {t('Words', 'كلمة')}</Typography>
          <TextField fullWidth size="small" placeholder={t('Search in this category...', 'ابحث داخل هذه الفئة...')} value={globalSearch} onChange={(event) => setGlobalSearch(event.target.value)} sx={{ mt: 2.25 }} InputProps={{ startAdornment: <Search sx={{ color: 'text.secondary', marginInlineEnd: 1 }} /> }} />
        </Paper>
        {categoryItems.length ? renderRows(categoryItems) : <Paper sx={{ p: 5, textAlign: 'center', borderRadius: 3 }}><Typography color="text.secondary">{t('No vocabulary has been added to this category yet.', 'لم تتم إضافة مفردات لهذه الفئة بعد.')}</Typography></Paper>}
      </> : <>
        <TextField fullWidth placeholder={t('Search vocabulary...', 'ابحث في المفردات...')} value={globalSearch} onChange={(event) => setGlobalSearch(event.target.value)} sx={{ mb: 3 }} InputProps={{ startAdornment: <Search sx={{ color: 'text.secondary', marginInlineEnd: 1 }} /> }} />
        {globalSearch.trim() ? <>
          <Typography variant="h6" fontWeight={850} sx={{ mb: 1.4 }}>{t('Search results', 'نتائج البحث')}</Typography>
          {globalResults.length ? renderRows(globalResults, true) : <Paper sx={{ p: 5, textAlign: 'center', borderRadius: 3 }}><Typography color="text.secondary">{t('No matching vocabulary found.', 'لم يتم العثور على مفردات مطابقة.')}</Typography></Paper>}
        </> : <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(3, 1fr)' }, gap: 1.75 }}>
          {categories.map((category) => {
            const Icon = CATEGORY_ICONS[category.name] || AccountBalanceWalletOutlined;
            return <Paper component={ButtonBase} key={category.id} elevation={0} onClick={() => setSelectedCategoryId(category.id)} aria-label={`${t('Open', 'فتح')} ${categoryLabel(category, isArabic)}`} sx={{ display: 'block', width: '100%', p: 2.25, textAlign: isArabic ? 'right' : 'left', border: '1px solid rgba(31,53,88,0.13)', borderRadius: 3, transition: 'transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease', '&:hover': { transform: 'translateY(-3px)', boxShadow: '0 15px 28px rgba(31,53,88,0.11)', borderColor: 'primary.main' }, '&.Mui-focusVisible': { outline: '3px solid rgba(255,210,0,0.55)', outlineOffset: 3 } }}>
              <Box sx={{ width: 43, height: 43, display: 'grid', placeItems: 'center', bgcolor: 'rgba(255,210,0,0.22)', borderRadius: 2, color: 'secondary.main', mb: 2 }}><Icon /></Box>
              <Typography fontWeight={850} fontSize={17}>{categoryLabel(category, isArabic)}</Typography>
              <Typography color="text.secondary" sx={{ mt: 0.5 }}>{category.item_count} {t('Words', 'كلمة')}</Typography>
              <Box sx={{ mt: 1.35, display: 'flex', alignItems: 'center', gap: 0.65, color: 'primary.main', fontWeight: 800, fontSize: 14 }}><span>{t('Open', 'فتح')}</span></Box>
            </Paper>;
          })}
        </Box>}
      </>}

      <Dialog sx={formLayoutSx} dir={isArabic ? 'rtl' : 'ltr'} open={categoryOpen} onClose={() => !saving && setCategoryOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('Add Category', 'إضافة فئة')}</DialogTitle>
        <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
          {categoryError && <Alert severity="error">{categoryError}</Alert>}
          <TextField label={t('Category Name (English)', 'اسم الفئة بالإنجليزية')} value={categoryForm.name} onChange={(event) => setCategoryForm((value) => ({ ...value, name: event.target.value }))} inputProps={{ dir: 'ltr' }} autoFocus />
          <TextField label={t('Category Name (Arabic)', 'اسم الفئة بالعربية')} value={categoryForm.arabic_name} onChange={(event) => setCategoryForm((value) => ({ ...value, arabic_name: event.target.value }))} inputProps={{ dir: 'rtl' }} />
          <TextField type="number" label={t('Display Order', 'ترتيب العرض')} value={categoryForm.display_order} onChange={(event) => setCategoryForm((value) => ({ ...value, display_order: Number(event.target.value) || 0 }))} />
          <FormControl><InputLabel>{t('Status', 'الحالة')}</InputLabel><Select label={t('Status', 'الحالة')} value={categoryForm.is_active ? 'active' : 'inactive'} onChange={(event) => setCategoryForm((value) => ({ ...value, is_active: event.target.value === 'active' }))}><MenuItem value="active">{t('Active', 'نشط')}</MenuItem><MenuItem value="inactive">{t('Inactive', 'غير نشط')}</MenuItem></Select></FormControl>
          <Typography variant="caption" color="text.secondary">{t('The category ID is generated once from the English name and remains stable.', 'يتم إنشاء معرف الفئة مرة واحدة من الاسم الإنجليزي ويبقى ثابتاً.')}</Typography>
        </Stack></DialogContent>
        <DialogActions sx={{ p: 2.5 }}><Button onClick={() => setCategoryOpen(false)} disabled={saving}>{t('Cancel', 'إلغاء')}</Button><Button variant="contained" onClick={saveCategory} disabled={saving} startIcon={<Add />}>{t('Create Category', 'إنشاء فئة')}</Button></DialogActions>
      </Dialog>
      <Dialog sx={formLayoutSx} dir={isArabic ? 'rtl' : 'ltr'} open={formOpen} onClose={() => !saving && setFormOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editingItem ? t('Edit Vocabulary', 'تعديل المفردة') : t('Add Vocabulary', 'إضافة مفردة')}</DialogTitle>
        <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
          {formError && <Alert severity="error">{formError}</Alert>}
          <TextField label={t('English Word / Phrase', 'الكلمة أو العبارة الإنجليزية')} value={form.english_text} onChange={(event) => setForm((value) => ({ ...value, english_text: event.target.value }))} inputProps={{ dir: 'ltr' }} autoFocus />
          <TextField label={t('Arabic Meaning', 'المعنى العربي')} value={form.arabic_text} onChange={(event) => setForm((value) => ({ ...value, arabic_text: event.target.value }))} inputProps={{ dir: 'rtl' }} />
          <TextField label={t('Pronunciation Text (optional)', 'نص النطق (اختياري)')} helperText={t('Use this only when an acronym needs a clearer English pronunciation.', 'استخدمه فقط إذا كان الاختصار يحتاج نطقاً إنجليزياً أوضح.')} value={form.speech_text} onChange={(event) => setForm((value) => ({ ...value, speech_text: event.target.value }))} inputProps={{ dir: 'ltr' }} />
          <FormControl><InputLabel>{t('Category', 'الفئة')}</InputLabel><Select label={t('Category', 'الفئة')} value={form.category_id} onChange={(event) => setForm((value) => ({ ...value, category_id: event.target.value }))}>{categories.map((category) => <MenuItem key={category.id} value={category.id}>{categoryLabel(category, isArabic)}</MenuItem>)}</Select></FormControl>
        </Stack></DialogContent>
        <DialogActions sx={{ p: 2.5 }}><Button onClick={() => setFormOpen(false)} disabled={saving}>{t('Cancel', 'إلغاء')}</Button><Button variant="contained" onClick={saveItem} disabled={saving} startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <CheckCircleOutline />}>{t('Save', 'حفظ')}</Button></DialogActions>
      </Dialog>
      <Dialog sx={formLayoutSx} dir={isArabic ? 'rtl' : 'ltr'} open={Boolean(deleteItem)} onClose={() => setDeleteItem(null)} maxWidth="xs" fullWidth><DialogTitle>{t('Delete Vocabulary?', 'حذف المفردة؟')}</DialogTitle><DialogContent><Typography>{deleteItem?.english_text}</Typography><Typography color="text.secondary" sx={{ mt: 1 }}>{t('This vocabulary item will be removed from Business Vocabulary.', 'سيتم حذف هذه المفردة من مفردات الأعمال.')}</Typography></DialogContent><DialogActions sx={{ p: 2.5 }}><Button onClick={() => setDeleteItem(null)}>{t('Cancel', 'إلغاء')}</Button><Button variant="contained" color="error" onClick={confirmDelete} startIcon={<DeleteOutline />}>{t('Delete', 'حذف')}</Button></DialogActions></Dialog>
    </Box>
  );
}
