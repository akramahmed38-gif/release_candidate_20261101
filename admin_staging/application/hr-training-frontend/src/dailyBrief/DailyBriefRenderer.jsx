import React from 'react';
import { Box, Button, Divider, Stack, Typography } from '@mui/material';
import { SemanticBlock } from './DailyBriefSemanticBlock';
const plain = (value) => String(value || '').split('\n').map((line, index) => <React.Fragment key={`${line}-${index}`}>{line}{index < String(value || '').split('\n').length - 1 ? <br /> : null}</React.Fragment>);

function safeHtml(value) {
  const node = new DOMParser().parseFromString(String(value || ''), 'text/html');
  const tags = new Set(['P', 'BR', 'STRONG', 'B', 'EM', 'I', 'U', 'H1', 'H2', 'H3', 'UL', 'OL', 'LI', 'A', 'BLOCKQUOTE', 'SPAN', 'DIV', 'FONT']);
  node.body.querySelectorAll('*').forEach((element) => {
    if (!tags.has(element.tagName)) { element.replaceWith(...element.childNodes); return; }
    [...element.attributes].forEach((attribute) => {
      const allowed = ['href', 'target', 'rel', 'dir', 'size', 'color'].includes(attribute.name);
      if (!allowed || (attribute.name === 'href' && !/^(\/|https:\/\/)/.test(attribute.value))) element.removeAttribute(attribute.name);
    });
    if (element.tagName === 'A') { element.setAttribute('rel', 'noreferrer noopener'); if (element.getAttribute('href')?.startsWith('https://')) element.setAttribute('target', '_blank'); }
  });
  return node.body.innerHTML;
}

function Image({ src, alt, caption }) {
  return !src ? null : <Box>
    <Box component="img" src={src} alt={alt || ''} sx={{ display: 'block', maxWidth: '100%', width: '100%', height: 'auto', maxHeight: 460, objectFit: 'contain', borderRadius: 3, border: '1px solid #e5e7eb', bgcolor: '#fff' }} />
    {caption ? <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1, textAlign: 'center' }}>{caption}</Typography> : null}
  </Box>;
}

export default function DailyBriefRenderer({ brief, apiBase = '', preview = false }) {
  const blocks = [...(brief?.blocks || [])].sort((left, right) => left.position - right.position);
  const firstTextId = blocks.find((block) => block.block_type === 'text')?.id;
  const resolveImage = (value) => value?.startsWith('/api/') ? `${apiBase}${value}` : value;
  const richTextSx = { color: '#334155', maxWidth: 960, fontSize: { xs: '1.0625rem', md: '1.125rem' }, lineHeight: 1.82, '& p': { m: 0, mb: 1.75 }, '& p:last-child': { mb: 0 }, '& h1,& h2,& h3': { color: '#102a56', lineHeight: 1.3, fontWeight: 800, mt: 3, mb: 1.25 }, '& h1': { fontSize: '1.7rem' }, '& h2': { fontSize: '1.4rem' }, '& h3': { fontSize: '1.2rem' }, '& ul,& ol': { my: 1.5, ps: 3.25 }, '& li': { mb: .75, ps: .35 }, '& blockquote': { borderInlineStart: '3px solid #ffd200', color: '#475569', m: '20px 0', px: 2, fontStyle: 'italic' }, '& a': { color: '#0b4fa8', fontWeight: 700, textDecorationThickness: '1.5px' } };
  return <Stack spacing={{ xs: 2.5, md: 3 }} dir="auto">{blocks.map((block) => { const content = block.content || {}; const key = block.id;
    if (block.block_type === 'heading') return <Box key={key} sx={{ textAlign: ['left', 'center', 'right'].includes(content.alignment) ? content.alignment : 'left' }}><Typography variant="h4" sx={{ fontWeight: 800, color: '#102a56', fontSize: { xs: '1.5rem', md: '1.75rem' } }}>{content.heading}</Typography>{content.subtitle && <Typography color="text.secondary" sx={{ mt: 1, fontSize: { xs: '1rem', md: '1.0625rem' } }}>{content.subtitle}</Typography>}</Box>;
    if (block.block_type === 'text') { const lead = key === firstTextId; const textSx = lead ? { ...richTextSx, fontSize: { xs: '1.125rem', md: '1.25rem' }, fontWeight: 500, color: '#243b61' } : richTextSx; return content.html ? <Box key={key} sx={textSx} dangerouslySetInnerHTML={{ __html: safeHtml(content.html) }} /> : <Typography key={key} sx={{ ...textSx, whiteSpace: 'pre-line' }}>{content.text || ''}</Typography>; }
    if (block.block_type === 'highlight' || block.block_type === 'alert') return <SemanticBlock key={key} type={block.block_type} style={content.style} heading={content.heading} text={content.text} />;
    if (block.block_type === 'image') return <Image key={key} src={resolveImage(content.image_url)} alt={content.alt} caption={content.caption} />;
    if (block.block_type === 'bullet_list') return <Box key={key} sx={{ maxWidth: 790 }}>{content.heading && <Typography fontWeight={800} color="#102a56" sx={{ mb: 1 }}>{content.heading}</Typography>}<Box component="ul" sx={{ m: 0, ps: 3.25, color: '#334155', '& li': { mb: 1, ps: .35, lineHeight: 1.7 } }}>{(content.items || []).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</Box></Box>;
    if (block.block_type === 'image_text') return <Box key={key} sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 1fr) minmax(0, 1.2fr)' }, gap: { xs: 2, md: 3 }, alignItems: 'center' }}><Box sx={{ order: { md: content.image_position === 'right' ? 2 : 1 } }}><Image src={resolveImage(content.image_url)} alt={content.alt} /></Box><Box sx={{ order: { md: content.image_position === 'right' ? 1 : 2 } }}><Typography variant="h6" fontWeight={800} color="#102a56">{content.heading}</Typography><Typography sx={{ mt: 1, color: '#334155', lineHeight: 1.75 }}>{plain(content.text)}</Typography></Box></Box>;
    if (block.block_type === 'cta') return <Button key={key} component="a" href={content.link || '#'} target={content.link?.startsWith('https://') ? '_blank' : undefined} rel="noreferrer" variant="contained" sx={{ alignSelf: 'flex-start', borderRadius: 2, px: 2.5, py: 1.1, bgcolor: '#ffd200', color: '#102a56', boxShadow: 'none', fontWeight: 800, '&:hover': { bgcolor: '#e9bd00', boxShadow: '0 6px 16px rgba(202,160,0,.2)' } }}>{content.label || 'Open'}</Button>;
    return block.block_type === 'divider' ? <Divider key={key} sx={{ borderColor: '#e5e7eb' }} /> : (preview ? <Typography key={key} color="warning.main">Unsupported block</Typography> : null);
  })}</Stack>;
}
