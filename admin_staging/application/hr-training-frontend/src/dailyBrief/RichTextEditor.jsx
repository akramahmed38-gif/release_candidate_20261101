import React, { useEffect, useRef, useState } from 'react';
import { FormatAlignCenter, FormatAlignLeft, FormatAlignRight, FormatBold, FormatClear, FormatColorFill, FormatColorText, FormatItalic, FormatListBulleted, FormatListNumbered, FormatUnderlined, FormatQuote, Link, Redo, Undo } from '@mui/icons-material';
import { Box, Button, Divider, IconButton, Menu, MenuItem, Stack, TextField, Tooltip } from '@mui/material';

const colors = ['navy', 'black', 'gray', 'yellow', 'red', 'blue', 'green'];
const textColors = [{ name: 'Fawry navy', value: '#102a56' }, { name: 'Black', value: '#111827' }, { name: 'Dark gray', value: '#4b5563' }, { name: 'Warning red', value: '#b42318' }, { name: 'Information blue', value: '#0b4fa8' }, { name: 'Success green', value: '#176b3a' }];
const highlightColors = [{ name: 'Yellow', value: '#fff15c' }, { name: 'Blue', value: '#dceeff' }, { name: 'Green', value: '#e4f6e9' }, { name: 'Red', value: '#fee2e2' }];

export default function RichTextEditor({ value = '', onChange, label = 'Text' }) {
  const editorRef = useRef(null);
  const [palette, setPalette] = useState(null);
  useEffect(() => { if (editorRef.current && editorRef.current.innerHTML !== value) editorRef.current.innerHTML = value || ''; }, [value]);
  const update = () => onChange(editorRef.current?.innerHTML || '');
  const command = (name, commandValue) => { editorRef.current?.focus(); document.execCommand(name, false, commandValue); update(); };
  const pastePlainText = (event) => { event.preventDefault(); const text = event.clipboardData?.getData('text/plain') || ''; document.execCommand('insertText', false, text); update(); };
  const tool = (title, icon, action) => <Tooltip title={title} key={title}><IconButton aria-label={title} size="small" onMouseDown={(event) => event.preventDefault()} onClick={action}>{icon}</IconButton></Tooltip>;
  return <Box><Stack direction="row" flexWrap="wrap" alignItems="center" gap={0.25} sx={{ minHeight: 64, px: 1, py: .75, border: '1px solid #d8dee8', borderBottom: 0, borderRadius: '14px 14px 0 0', bgcolor: '#f8fafc' }}>
    <TextField select size="small" aria-label="Text style" defaultValue="p" sx={{ width: 142, '& .MuiOutlinedInput-root': { borderRadius: 1 }, '& .MuiOutlinedInput-notchedOutline': { border: 0 } }} onChange={(event) => command('formatBlock', event.target.value)}><MenuItem value="p">Normal</MenuItem><MenuItem value="h1">Heading 1</MenuItem><MenuItem value="h2">Heading 2</MenuItem><MenuItem value="h3">Heading 3</MenuItem></TextField>
    <TextField select size="small" aria-label="Font size" defaultValue="5" sx={{ width: 76, '& .MuiOutlinedInput-root': { borderRadius: 1 }, '& .MuiOutlinedInput-notchedOutline': { border: 0 } }} onChange={(event) => command('fontSize', event.target.value)}>{[['2', '12'], ['3', '14'], ['4', '16'], ['5', '18'], ['6', '20'], ['7', '24']].map(([value, labelText]) => <MenuItem key={value} value={value}>{labelText}</MenuItem>)}</TextField>
    <Divider flexItem orientation="vertical" sx={{ mx: 0.25 }} />
    {tool('Bold', <FormatBold />, () => command('bold'))}{tool('Italic', <FormatItalic />, () => command('italic'))}{tool('Underline', <FormatUnderlined />, () => command('underline'))}
    {tool('Text color', <FormatColorText />, (event) => setPalette({ type: 'text', anchor: event.currentTarget }))}{tool('Highlight', <FormatColorFill />, (event) => setPalette({ type: 'highlight', anchor: event.currentTarget }))}
    <Divider flexItem orientation="vertical" sx={{ mx: 0.25 }} />
    {tool('Align left', <FormatAlignLeft />, () => command('justifyLeft'))}{tool('Align center', <FormatAlignCenter />, () => command('justifyCenter'))}{tool('Align right', <FormatAlignRight />, () => command('justifyRight'))}
    {tool('Bulleted list', <FormatListBulleted />, () => command('insertUnorderedList'))}{tool('Numbered list', <FormatListNumbered />, () => command('insertOrderedList'))}{tool('Block quote', <FormatQuote />, () => command('formatBlock', 'blockquote'))}
    {tool('Undo', <Undo />, () => command('undo'))}{tool('Redo', <Redo />, () => command('redo'))}{tool('Clear formatting', <FormatClear />, () => command('removeFormat'))}
    {tool('Insert link', <Link />, () => { const url = window.prompt('HTTPS URL or internal path'); if (url) command('createLink', url); })}
    <Button size="small" onClick={() => command('formatBlock', 'div')}>LTR</Button><Button size="small" onClick={() => { editorRef.current?.setAttribute('dir', 'rtl'); editorRef.current?.focus(); }}>RTL</Button>
  </Stack><Menu anchorEl={palette?.anchor} open={Boolean(palette)} onClose={() => setPalette(null)}><Box sx={{ p: 1, display: 'grid', gridTemplateColumns: 'repeat(3, 36px)', gap: .75 }}>{(palette?.type === 'highlight' ? highlightColors : textColors).map((color) => <Tooltip key={color.name} title={color.name}><IconButton aria-label={color.name} onClick={() => { command(palette.type === 'highlight' ? 'hiliteColor' : 'foreColor', color.value); setPalette(null); }} sx={{ width: 32, height: 32, bgcolor: color.value, border: '1px solid #cbd5e1', '&:hover': { bgcolor: color.value, transform: 'scale(1.1)' } }} /></Tooltip>)}</Box></Menu><Box ref={editorRef} contentEditable suppressContentEditableWarning role="textbox" aria-label={label} onInput={update} onPaste={pastePlainText} onBlur={update} dir="auto" sx={{ minHeight: 210, p: 2.5, border: '1px solid #d8dee8', borderRadius: '0 0 14px 14px', outline: 'none', bgcolor: '#fff', lineHeight: 1.75, '&:focus': { borderColor: '#0b4fa8', boxShadow: '0 0 0 3px rgba(11,79,168,.12)' }, '& blockquote': { m: 0, pl: 2, borderLeft: '3px solid #ffd200', color: 'text.secondary' } }} />
  </Box>;
}
