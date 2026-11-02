import React, { useEffect, useRef, useState } from 'react';
import { Add, ArrowDownward, ArrowUpward, Check, ContentCopy, Delete, Image as ImageIcon, Preview, Publish, Save } from '@mui/icons-material';
import { Alert, Box, Button, Card, CardContent, Dialog, DialogActions, DialogContent, DialogTitle, Divider, IconButton, Menu, MenuItem, Paper, Stack, TextField, Tooltip, Typography } from '@mui/material';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { dailyBriefService } from '../services/auth';
import { getSemanticStyle, semanticStyleKeys, SemanticBlock } from './DailyBriefSemanticBlock';
import RichTextEditor from './RichTextEditor';
import { publishValidationError } from './publishValidation';

const blockTypes = [
  ['text', 'Text'], ['highlight', 'Highlight'], ['alert', 'Alert'], ['image', 'Image'],
];

function SemanticStyleSelector({ type, selectedStyle, onSelect }) {
  return (
    <Box>
      <Typography variant="subtitle2" fontWeight={800} sx={{ mb: 1 }}>Style</Typography>
      <Box
        role="radiogroup"
        aria-label={`${type} style`}
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', sm: 'repeat(3, minmax(0, 1fr))', lg: 'repeat(6, minmax(0, 1fr))' },
          gap: 1,
        }}
      >
        {semanticStyleKeys.map((value) => {
          const semantic = getSemanticStyle(type, value);
          const { Icon } = semantic;
          const selected = value === selectedStyle;
          return (
            <Box
              key={value}
              role="radio"
              aria-checked={selected}
              tabIndex={0}
              onClick={() => onSelect(value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelect(value);
                }
              }}
              sx={{
                cursor: 'pointer',
                position: 'relative',
                minHeight: 82,
                p: 1.25,
                borderRadius: 2,
                border: `${selected ? 2 : 1}px solid ${selected ? semantic.accent : semantic.border}`,
                bgcolor: semantic.background,
                color: semantic.accent,
                transition: 'border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease',
                boxShadow: selected ? `0 0 0 3px ${semantic.accent}1a` : 'none',
                '&:hover': {
                  borderColor: semantic.accent,
                  boxShadow: `0 4px 12px ${semantic.accent}1a`,
                  transform: 'translateY(-1px)',
                },
                '&:focus-visible': { outline: `3px solid ${semantic.accent}33`, outlineOffset: 2 },
              }}
            >
              <Icon aria-hidden="true" sx={{ color: semantic.accent, fontSize: 20 }} />
              <Typography sx={{ mt: .65, color: semantic.accent, fontSize: '.72rem', fontWeight: 800, lineHeight: 1.2 }}>
                {semantic.label}
              </Typography>
              {selected ? <Check sx={{ position: 'absolute', top: 7, insetInlineEnd: 7, fontSize: 17, color: semantic.accent }} /> : null}
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}

const emptyContent = (blockType) => ({
  heading: { heading: '', subtitle: '', alignment: 'left' }, text: { text: '' }, highlight: { heading: '', text: '', style: 'important' }, alert: { heading: '', text: '', style: 'warning' }, image: { image_url: '', alt: '', caption: '' }, bullet_list: { heading: '', items: [''] }, image_text: { image_url: '', heading: '', text: '', alt: '', image_position: 'left' }, cta: { label: '', link: '/materials' }, divider: {},
}[blockType] || {});

const freshBlock = (blockType) => ({ id: `new-${Date.now()}-${Math.random().toString(36).slice(2)}`, block_type: blockType, content: emptyContent(blockType) });

const NEW_BRIEF_RECOVERY_KEY = 'daily-brief:new-brief-recovery';
const PREVIEW_RECOVERY_PREFIX = 'daily-brief:preview-recovery';

const createEmptyForm = () => ({
  title: '',
  brief_date: new Date().toISOString().slice(0, 10),
  blocks: [],
});

const restoreNewBriefForm = () => {
  try {
    const savedForm = JSON.parse(window.sessionStorage.getItem(NEW_BRIEF_RECOVERY_KEY) || 'null');
    if (!savedForm || !Array.isArray(savedForm.blocks)) return createEmptyForm();
    return {
      title: typeof savedForm.title === 'string' ? savedForm.title : '',
      brief_date: typeof savedForm.brief_date === 'string' ? savedForm.brief_date : createEmptyForm().brief_date,
      blocks: savedForm.blocks,
    };
  } catch {
    return createEmptyForm();
  }
};

export const restorePreviewSession = (recoveryKey) => {
  if (!recoveryKey) return null;
  try {
    const snapshot = JSON.parse(window.sessionStorage.getItem(recoveryKey) || 'null');
    window.sessionStorage.removeItem(recoveryKey);
    if (!snapshot?.form || !Array.isArray(snapshot.form.blocks)) return null;
    return snapshot;
  } catch {
    return null;
  }
};

export default function DailyBriefBuilder() {
  const { briefId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [previewRecovery] = useState(() => restorePreviewSession(location.state?.previewSessionKey));
  const [form, setForm] = useState(() => previewRecovery?.form || (briefId ? createEmptyForm() : restoreNewBriefForm()));
  const [briefStatus, setBriefStatus] = useState(() => previewRecovery?.briefStatus || 'DRAFT');
  const [loading, setLoading] = useState(() => Boolean(briefId) && !previewRecovery);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [publishOpen, setPublishOpen] = useState(false);
  const [dragIndex, setDragIndex] = useState(null);
  const [addAnchor, setAddAnchor] = useState(null);
  const fileInputRef = useRef(null);
  const uploadTargetRef = useRef(null);
  const savePendingRef = useRef(false);
  const savedIdRef = useRef(briefId || null);
  useEffect(() => { savedIdRef.current = briefId || null; }, [briefId]);

  useEffect(() => {
    if (!briefId) return;
    if (previewRecovery) {
      setLoading(false);
      return;
    }
    dailyBriefService.getBrief(briefId).then((response) => {
      const item = response.data.item;
      setForm({ title: item.title, brief_date: item.brief_date, blocks: item.blocks || [] });
      setBriefStatus(item.status || 'DRAFT');
    }).catch((requestError) => setError(requestError.response?.data?.detail || 'Unable to load Daily Brief.')).finally(() => setLoading(false));
  }, [briefId, previewRecovery]);

  useEffect(() => {
    if (briefId) return;
    try {
      window.sessionStorage.setItem(NEW_BRIEF_RECOVERY_KEY, JSON.stringify(form));
    } catch {
      // A preview should still work when browser storage is unavailable.
    }
  }, [briefId, form]);

  const openPreview = () => {
    const recoveryKey = `${PREVIEW_RECOVERY_PREFIX}:${briefId || 'new'}:${Date.now()}:${Math.random().toString(36).slice(2)}`;
    const previewBrief = {
      ...form,
      status: 'PREVIEW',
      blocks: form.blocks.map((block, index) => ({ ...block, position: index })),
    };
    try {
      window.sessionStorage.setItem(recoveryKey, JSON.stringify({ form, briefStatus }));
    } catch {
      // The preview still renders from route state when browser storage is unavailable.
    }
    navigate('/daily-brief/preview', {
      state: { brief: previewBrief, returnTo: location.pathname, previewSessionKey: recoveryKey },
    });
  };

  const updateBlock = (index, key, value) => setForm((current) => ({ ...current, blocks: current.blocks.map((block, blockIndex) => blockIndex === index ? { ...block, content: { ...block.content, [key]: value } } : block) }));
  const addBlock = (blockType) => setForm((current) => ({ ...current, blocks: [...current.blocks, freshBlock(blockType)] }));
  const moveBlock = (index, target) => setForm((current) => { if (target < 0 || target >= current.blocks.length) return current; const next = [...current.blocks]; [next[index], next[target]] = [next[target], next[index]]; return { ...current, blocks: next }; });
  const deleteBlock = (index) => setForm((current) => ({ ...current, blocks: current.blocks.filter((_, blockIndex) => blockIndex !== index) }));
  const duplicateBlock = (index) => setForm((current) => { const next = [...current.blocks]; next.splice(index + 1, 0, { ...current.blocks[index], id: `new-${Date.now()}-${index}`, content: { ...current.blocks[index].content } }); return { ...current, blocks: next }; });
  const save = async ({ exitAfterSave = false, stayInBuilder = false } = {}) => {
    if (savePendingRef.current) return;
    savePendingRef.current = true;
    setSaving(true); setError(''); setSuccessMessage('');
    try {
      const existingId = savedIdRef.current || briefId;
      const response = existingId ? await dailyBriefService.updateBrief(existingId, form) : await dailyBriefService.createBrief(form);
      const savedBrief = response.data?.item || response.data || {};
      // A successful update already has an authoritative ID in the route.
      // Creation still requires the server to return the new ID.
      const id = savedBrief.id || (existingId || null);
      if (!id) throw new Error('Daily Brief create response did not include an ID.');
      savedIdRef.current = id;
      if (!briefId) {
        try { window.sessionStorage.removeItem(NEW_BRIEF_RECOVERY_KEY); } catch { /* Storage may be unavailable. */ }
      }
      setBriefStatus(savedBrief.status || briefStatus);
      setForm((current) => ({
        title: savedBrief.title ?? current.title,
        brief_date: savedBrief.brief_date ?? current.brief_date,
        blocks: savedBrief.blocks || current.blocks,
      }));
      setSuccessMessage('Daily Brief saved successfully.');
      if (!stayInBuilder) {
        if (exitAfterSave) navigate('/daily-brief', { state: { tab: savedBrief.status || briefStatus, message: 'Daily Brief saved successfully.' } });
        else if (!briefId) navigate(`/daily-brief/${id}/edit`, { replace: true });
      }
      return id;
    }
    catch (requestError) {
      console.error('[Daily Brief] Save request failed', requestError);
      const detail = requestError.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(item => item.msg || 'Invalid field').join('; ') : requestError.message || `Unable to save Daily Brief${requestError.response?.status ? ` (HTTP ${requestError.response.status})` : ''}.`);
    }
    finally { savePendingRef.current = false; setSaving(false); }
  };
  const publish = async () => {
    if (briefStatus !== 'DRAFT' || saving) return;
    const validationError = publishValidationError(form);
    if (validationError) { setError(validationError); setSuccessMessage(''); setPublishOpen(false); return; }
    const id = await save({ stayInBuilder: true });
    if (!id) { setPublishOpen(false); return; }
    setSaving(true);
    setSuccessMessage('');
    try {
      await dailyBriefService.publishBrief(id);
      navigate('/daily-brief', { state: { tab: 'LIVE', message: 'Daily Brief is now Live. No email has been sent.' } });
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(item => item.msg || 'Invalid field').join('; ') : requestError.message || 'Unable to publish Daily Brief.');
    } finally { setSaving(false); setPublishOpen(false); }
  };
  const uploadImage = async (event) => { const file = event.target.files?.[0]; const index = uploadTargetRef.current; if (!file || index === null) return; try { const response = await dailyBriefService.uploadImage(file); updateBlock(index, 'image_url', response.data.image_url); } catch (requestError) { setError(requestError.response?.data?.detail || 'Image upload failed.'); } finally { event.target.value = ''; } };
  const renderEditorLegacy = (block, index) => {
    const content = block.content || {};
    const input = (key, label, extra = {}) => <TextField fullWidth size="small" label={label} value={content[key] || ''} onChange={(event) => updateBlock(index, key, event.target.value)} {...extra} />;
    if (block.block_type === 'heading') return <Stack spacing={1.25}>{input('heading', 'Heading')}{input('subtitle', 'Subtitle')}{input('alignment', 'Alignment', { select: true, children: ['left', 'center', 'right'].map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>) })}</Stack>;
    if (block.block_type === 'text') return <RichTextEditor label="Text block" value={content.html || (content.text ? `<p>${content.text.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>')}</p>` : '')} onChange={(html) => updateBlock(index, 'html', html)} />;
    if (block.block_type === 'highlight' || block.block_type === 'alert') { const selectedStyle = content.style || (block.block_type === 'alert' ? 'warning' : 'important'); return <Stack spacing={1.5}>{input('heading', 'Heading')}{input('text', 'Message', { multiline: true, minRows: 3 })}<Box><Typography variant="subtitle2" fontWeight={800} sx={{ mb: 1 }}>Style</Typography><Box role="radiogroup" aria-label={`${block.block_type} style`} sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', sm: 'repeat(5, minmax(0, 1fr))' }, gap: 1 }}>{semanticStyleKeys.map((value) => { const semantic = getSemanticStyle(block.block_type, value); const { Icon } = semantic; const selected = value === selectedStyle; return <Box key={value} role="radio" aria-checked={selected} tabIndex={0} onClick={() => updateBlock(index, 'style', value)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') updateBlock(index, 'style', value); }} sx={{ cursor: 'pointer', position: 'relative', p: 1.15, minHeight: 74, borderRadius: 1.75, border: `1px solid ${selected ? semantic.accent : '#dce3ea'}`, bgcolor: selected ? semantic.background : '#fff', color: semantic.title, '&:hover': { borderColor: semantic.accent, bgcolor: semantic.background } }}><Icon sx={{ color: semantic.accent, fontSize: 20 }} /><Typography sx={{ mt: .55, fontSize: '.72rem', fontWeight: 800, lineHeight: 1.2 }}>{semantic.label}</Typography>{selected ? <Check sx={{ position: 'absolute', top: 6, insetInlineEnd: 6, fontSize: 16, color: semantic.accent }} /> : null}</Box>; })}</Box></Box><Box><Typography variant="subtitle2" fontWeight={800} sx={{ mb: .8 }}>Retail preview</Typography><SemanticBlock type={block.block_type} style={selectedStyle} heading={content.heading} text={content.text} compact /></Box></Stack>; }
    if (block.block_type === 'image' || block.block_type === 'image_text') return <Stack spacing={1.25}>{input('image_url', 'Image URL', { InputProps: { readOnly: true } })}<Button startIcon={<ImageIcon />} variant="outlined" onClick={() => { uploadTargetRef.current = index; fileInputRef.current?.click(); }}>Upload image</Button>{block.block_type === 'image_text' ? <>{input('heading', 'Heading')}{input('text', 'Text', { multiline: true, minRows: 3 })}{input('image_position', 'Image position', { select: true, children: ['left', 'right'].map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>) })}</> : input('caption', 'Caption')}{input('alt', 'Alt text')}</Stack>;
    if (block.block_type === 'bullet_list') return <Stack spacing={1.25}>{input('heading', 'Optional heading')}{(content.items || []).map((item, itemIndex) => <Stack key={itemIndex} direction="row" spacing={1}><TextField fullWidth size="small" label={`Bullet ${itemIndex + 1}`} value={item} onChange={(event) => updateBlock(index, 'items', content.items.map((value, currentIndex) => currentIndex === itemIndex ? event.target.value : value))} /><IconButton color="error" onClick={() => updateBlock(index, 'items', content.items.filter((_, currentIndex) => currentIndex !== itemIndex))}><Delete /></IconButton></Stack>)}<Button onClick={() => updateBlock(index, 'items', [...(content.items || []), ''])}>Add item</Button></Stack>;
    if (block.block_type === 'cta') return <Stack spacing={1.25}>{input('label', 'Button label')}{input('link', 'Internal path or HTTPS URL')}</Stack>;
    return <Typography color="text.secondary">A visual divider will be shown in the published brief.</Typography>;
  };
  const renderEditor = (block, index) => {
    if (block.block_type !== 'highlight' && block.block_type !== 'alert') {
      return renderEditorLegacy(block, index);
    }
    const content = block.content || {};
    const selectedStyle = content.style || (block.block_type === 'alert' ? 'warning' : 'important');
    const input = (key, label, extra = {}) => (
      <TextField
        fullWidth
        size="small"
        label={label}
        value={content[key] || ''}
        onChange={(event) => updateBlock(index, key, event.target.value)}
        {...extra}
      />
    );
    return (
      <Stack spacing={1.5}>
        {input('heading', 'Heading')}
        {input('text', 'Message', { multiline: true, minRows: 3 })}
        <SemanticStyleSelector
          type={block.block_type}
          selectedStyle={selectedStyle}
          onSelect={(value) => updateBlock(index, 'style', value)}
        />
        <Box>
          <Typography variant="subtitle2" fontWeight={800} sx={{ mb: .8 }}>Retail preview</Typography>
          <SemanticBlock type={block.block_type} style={selectedStyle} heading={content.heading} text={content.text} compact />
        </Box>
      </Stack>
    );
  };
  if (loading) return <Typography>Loading Daily Brief...</Typography>;
  return <Box sx={{ maxWidth: 1180, mx: 'auto', py: 2 }}><Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2} sx={{ mb: 3 }}><Box><Typography variant="h4" fontWeight={800}>Daily Brief Builder</Typography><Typography color="text.secondary">Create controlled Fawry communication blocks for Retail users.</Typography></Box><Stack direction="row" spacing={1}><Button variant="outlined" startIcon={<Preview />} onClick={openPreview}>Preview Retail</Button><Button variant="outlined" startIcon={<Save />} onClick={() => save({ exitAfterSave: briefStatus !== 'DRAFT' })} disabled={saving}>{briefStatus === 'DRAFT' ? 'Save Draft' : 'Save Changes'}</Button>{briefStatus === 'DRAFT' && <Button variant="contained" startIcon={<Publish />} onClick={() => setPublishOpen(true)} disabled={saving}>Publish to Retail</Button>}</Stack></Stack>{error ? <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert> : null}{successMessage ? <Alert severity="success" sx={{ mb: 2 }}>{successMessage}</Alert> : null}<Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3, mb: 2.5 }}><Stack spacing={2}><TextField fullWidth label="Page title" value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} /><TextField label="Brief date" type="date" value={form.brief_date} onChange={(event) => setForm((current) => ({ ...current, brief_date: event.target.value }))} slotProps={{ inputLabel: { shrink: true } }} sx={{ maxWidth: 260 }} /></Stack></Paper><Typography variant="h6" fontWeight={800} sx={{ mb: 1.5 }}>Content canvas</Typography><Stack spacing={1.5}>{form.blocks.map((block, index) => <Card key={block.id} draggable onDragStart={() => setDragIndex(index)} onDragOver={(event) => event.preventDefault()} onDrop={() => { if (dragIndex !== null) moveBlock(dragIndex, index); setDragIndex(null); }} variant="outlined" sx={{ borderRadius: 3 }}><CardContent><Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}><Typography fontWeight={800}>{blockTypes.find(([key]) => key === block.block_type)?.[1]}</Typography><Stack direction="row"><Tooltip title="Move up"><IconButton onClick={() => moveBlock(index, index - 1)}><ArrowUpward /></IconButton></Tooltip><Tooltip title="Move down"><IconButton onClick={() => moveBlock(index, index + 1)}><ArrowDownward /></IconButton></Tooltip><Tooltip title="Duplicate"><IconButton onClick={() => duplicateBlock(index)}><ContentCopy /></IconButton></Tooltip><Tooltip title="Delete"><IconButton color="error" onClick={() => deleteBlock(index)}><Delete /></IconButton></Tooltip></Stack></Stack>{renderEditor(block, index)}</CardContent></Card>)}</Stack><Paper variant="outlined" sx={{ p: 2, borderRadius: 3, mt: 2.5 }}><Typography fontWeight={800} sx={{ mb: 1 }}>Add block</Typography><Stack direction="row" flexWrap="wrap" gap={1}>{blockTypes.map(([type, label]) => <Button key={type} variant="outlined" size="small" startIcon={<Add />} onClick={() => addBlock(type)}>{label}</Button>)}</Stack></Paper><input hidden ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp" onChange={uploadImage} /><Dialog open={publishOpen} onClose={() => setPublishOpen(false)}><DialogTitle>Publish Daily Brief?</DialogTitle><DialogContent>This will become the current Daily Brief visible to all Retail users. The current Live brief will be archived. Publishing does not send email; use Send Brief Email separately.</DialogContent><DialogActions><Button onClick={() => setPublishOpen(false)}>Cancel</Button><Button variant="contained" onClick={publish} disabled={saving}>Publish</Button></DialogActions></Dialog></Box>;
}
