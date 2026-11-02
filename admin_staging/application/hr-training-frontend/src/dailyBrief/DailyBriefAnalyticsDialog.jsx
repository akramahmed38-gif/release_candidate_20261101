import React, { useState } from 'react';
import { Search } from '@mui/icons-material';
import { Box, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, InputAdornment, InputLabel, MenuItem, Paper, Select, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Tooltip, Typography, Button } from '@mui/material';

const dateTime = (value, isArabic) => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat(isArabic ? 'ar-EG' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
};

const options = (rows, key, tr) => [...new Set((rows || []).map((row) => row[key] || 'Unassigned'))].sort((a, b) => a.localeCompare(b)).map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>);

function Metric({ label, value, color }) {
  return <Paper variant="outlined" sx={{ minWidth: 0, p: 1.5, borderRadius: 2, borderColor: '#dce5f0', borderTop: `3px solid ${color}`, bgcolor: '#fbfdff' }}>
    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', minHeight: 34, lineHeight: 1.35 }}>{label}</Typography>
    <Typography variant="h5" fontWeight={800} color="#102a56">{value}</Typography>
  </Paper>;
}

function Reaction({ value, tr }) {
  if (value === 'LIKE') return <Chip size="small" label={tr('Like')} color="success" variant="outlined" />;
  if (value === 'UNLIKE') return <Chip size="small" label={tr('Unlike')} color="error" variant="outlined" />;
  return <Chip size="small" label={tr('None')} variant="outlined" />;
}

export default function DailyBriefAnalyticsDialog({ open, title, analytics, loading, error, exportLoading, onExport, onClose, translate, isArabic }) {
  const tr = translate || ((value) => value);
  const [search, setSearch] = useState('');
  const [viewFilter, setViewFilter] = useState('ALL');
  const [reactionFilter, setReactionFilter] = useState('ALL');
  const [regionFilter, setRegionFilter] = useState('ALL');
  const [areaFilter, setAreaFilter] = useState('ALL');
  const [branchFilter, setBranchFilter] = useState('ALL');
  const employees = analytics?.employees || [];
  const areas = analytics?.area_summary || [];
  const comments = analytics?.latest_comments || [];
  const query = search.trim().toLowerCase();
  const visibleEmployees = employees.filter((row) => {
    const searchMatches = !query || [row.name, row.email, row.hr_id, row.branch].some((value) => String(value || '').toLowerCase().includes(query));
    return searchMatches
      && (viewFilter === 'ALL' || (viewFilter === 'VIEWED' ? row.viewed : !row.viewed))
      && (reactionFilter === 'ALL' || (reactionFilter === 'NONE' ? !row.reaction : row.reaction === reactionFilter))
      && (regionFilter === 'ALL' || row.region === regionFilter)
      && (areaFilter === 'ALL' || row.area === areaFilter)
      && (branchFilter === 'ALL' || row.branch === branchFilter);
  });
  const totalViewed = analytics?.total_viewed ?? analytics?.viewed ?? 0;
  const metrics = [
    ['Total Eligible Employees', analytics?.total_eligible_employees ?? analytics?.eligible_retail_users ?? 0, '#f3c400'],
    ['Total Viewed', totalViewed, '#0b4fa8'], ['Not Viewed', analytics?.not_viewed ?? 0, '#c2413b'],
    ['View Rate', `${analytics?.view_rate ?? 0}%`, '#0b4fa8'], ['Total Likes', analytics?.total_likes ?? 0, '#2e7d32'],
    ['Total Unlikes', analytics?.total_unlikes ?? 0, '#c2413b'], ['Total Comments', analytics?.total_comments ?? 0, '#d6a900'],
  ];
  const coverage = (status) => status === 'complete'
    ? ['100% viewed', 'success'] : status === 'no_views'
      ? ['No views', 'error'] : status === 'low' ? ['Low coverage', 'warning'] : ['In progress', 'info'];

  return <Dialog open={open} onClose={onClose} maxWidth="xl" fullWidth PaperProps={{ sx: { borderRadius: 2 } }}>
    <DialogTitle sx={{ color: '#102a56', fontWeight: 800 }}>{tr('Viewed by')}{title ? `: ${title}` : ''}</DialogTitle>
    <DialogContent dividers sx={{ bgcolor: '#f8fafc' }}>
      {loading ? <Typography sx={{ py: 2 }}>{tr('Loading viewer statistics...')}</Typography>
        : error ? <Typography color="error">{tr(error)}</Typography>
          : analytics && <Stack spacing={2.5}>
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(132px, 1fr))', gap: 1.25 }}>
              {metrics.map(([label, value, color]) => <Metric key={label} label={tr(label)} value={value} color={color} />)}
            </Box>
            {totalViewed === 0 && <Typography color="text.secondary">{tr('No Retail users have viewed this Brief yet.')}</Typography>}
            <Box>
              <Stack direction="row" alignItems="baseline" justifyContent="space-between" sx={{ mb: 1 }}><Typography variant="h6" fontWeight={800} color="#102a56">{tr('Area Coverage')}</Typography><Typography variant="caption" color="text.secondary">{tr('Low coverage is below 70%')}</Typography></Stack>
              <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 2 }}><Table size="small" aria-label={tr('Area Coverage')}>
                <TableHead><TableRow sx={{ bgcolor: '#f1f5f9' }}>{['Area', 'Eligible', 'Viewed', 'Not Viewed', 'View Rate', 'Likes', 'Unlikes', 'Comments', 'Coverage'].map((label) => <TableCell key={label} sx={{ fontWeight: 800, whiteSpace: 'nowrap' }}>{tr(label)}</TableCell>)}</TableRow></TableHead>
                <TableBody>{areas.length ? areas.map((row) => { const [label, color] = coverage(row.coverage_status); return <TableRow key={`${row.region || ''}-${row.area}`} hover><TableCell><Typography fontWeight={700}>{row.area}</Typography>{row.region && <Typography variant="caption" color="text.secondary">{row.region}</Typography>}</TableCell><TableCell>{row.eligible}</TableCell><TableCell>{row.viewed}</TableCell><TableCell>{row.not_viewed}</TableCell><TableCell>{row.view_rate}%</TableCell><TableCell>{row.likes}</TableCell><TableCell>{row.unlikes}</TableCell><TableCell>{row.comments}</TableCell><TableCell><Chip size="small" color={color} variant="outlined" label={tr(label)} /></TableCell></TableRow>; }) : <TableRow><TableCell colSpan={9}>{tr('No eligible area data is available.')}</TableCell></TableRow>}</TableBody>
              </Table></TableContainer>
            </Box>
            <Box>
              <Typography variant="h6" fontWeight={800} color="#102a56" sx={{ mb: 1 }}>{tr('Employee Details')}</Typography>
              <Stack direction="row" useFlexGap flexWrap="wrap" gap={1} sx={{ mb: 1.25 }}>
                <TextField size="small" label={tr('Search name, email, ID, branch')} value={search} onChange={(event) => setSearch(event.target.value)} sx={{ minWidth: { xs: '100%', sm: 250 } }} InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
                <FormControl size="small" sx={{ minWidth: 130 }}><InputLabel id="brief-view-filter">{tr('Viewed')}</InputLabel><Select labelId="brief-view-filter" label={tr('Viewed')} value={viewFilter} onChange={(event) => setViewFilter(event.target.value)}><MenuItem value="ALL">{tr('All statuses')}</MenuItem><MenuItem value="VIEWED">{tr('Viewed')}</MenuItem><MenuItem value="NOT_VIEWED">{tr('Not viewed')}</MenuItem></Select></FormControl>
                <FormControl size="small" sx={{ minWidth: 130 }}><InputLabel id="brief-reaction-filter">{tr('Reaction')}</InputLabel><Select labelId="brief-reaction-filter" label={tr('Reaction')} value={reactionFilter} onChange={(event) => setReactionFilter(event.target.value)}><MenuItem value="ALL">{tr('All reactions')}</MenuItem><MenuItem value="LIKE">{tr('Like')}</MenuItem><MenuItem value="UNLIKE">{tr('Unlike')}</MenuItem><MenuItem value="NONE">{tr('None')}</MenuItem></Select></FormControl>
                <FormControl size="small" sx={{ minWidth: 145 }}><InputLabel id="brief-region-filter">{tr('Region')}</InputLabel><Select labelId="brief-region-filter" label={tr('Region')} value={regionFilter} onChange={(event) => setRegionFilter(event.target.value)}><MenuItem value="ALL">{tr('All regions')}</MenuItem>{options(employees, 'region', tr)}</Select></FormControl>
                <FormControl size="small" sx={{ minWidth: 145 }}><InputLabel id="brief-area-filter">{tr('Area')}</InputLabel><Select labelId="brief-area-filter" label={tr('Area')} value={areaFilter} onChange={(event) => setAreaFilter(event.target.value)}><MenuItem value="ALL">{tr('All areas')}</MenuItem>{options(employees, 'area', tr)}</Select></FormControl>
                <FormControl size="small" sx={{ minWidth: 145 }}><InputLabel id="brief-branch-filter">{tr('Branch')}</InputLabel><Select labelId="brief-branch-filter" label={tr('Branch')} value={branchFilter} onChange={(event) => setBranchFilter(event.target.value)}><MenuItem value="ALL">{tr('All branches')}</MenuItem>{options(employees, 'branch', tr)}</Select></FormControl>
              </Stack>
              <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 430, borderRadius: 2 }}><Table size="small" stickyHeader aria-label={tr('Employee Details')} sx={{ minWidth: 1080 }}>
                <TableHead><TableRow>{['Employee', 'Email / HR ID', 'Region', 'Area', 'Branch', 'Viewed', 'Viewed At', 'Reaction', 'Comment'].map((label) => <TableCell key={label} sx={{ fontWeight: 800, bgcolor: '#f1f5f9', whiteSpace: 'nowrap' }}>{tr(label)}</TableCell>)}</TableRow></TableHead>
                <TableBody>{visibleEmployees.length ? visibleEmployees.map((row) => <TableRow key={row.email} hover><TableCell sx={{ fontWeight: 700 }}>{row.name || tr('Unknown employee')}</TableCell><TableCell><Typography variant="body2">{row.email || '—'}</Typography><Typography variant="caption" color="text.secondary">{row.hr_id || '—'}</Typography></TableCell><TableCell>{row.region}</TableCell><TableCell>{row.area}</TableCell><TableCell>{row.branch}</TableCell><TableCell><Chip size="small" label={tr(row.viewed ? 'Viewed' : 'Not viewed')} color={row.viewed ? 'success' : 'default'} variant="outlined" /></TableCell><TableCell sx={{ whiteSpace: 'nowrap' }}>{dateTime(row.viewed_at, isArabic)}</TableCell><TableCell><Reaction value={row.reaction} tr={tr} /></TableCell><TableCell sx={{ maxWidth: 220 }}><Tooltip title={row.comment || ''} placement="top-start"><Typography variant="body2" noWrap sx={{ maxWidth: 205 }}>{row.comment || '—'}</Typography></Tooltip></TableCell></TableRow>) : <TableRow><TableCell colSpan={9} align="center"><Typography color="text.secondary" sx={{ py: 2 }}>{tr('No employees match these filters.')}</Typography></TableCell></TableRow>}</TableBody>
              </Table></TableContainer>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>{visibleEmployees.length} / {employees.length} {tr('eligible employees')}</Typography>
            </Box>
            <Box>
              <Typography variant="h6" fontWeight={800} color="#102a56" sx={{ mb: 1 }}>{tr('Latest Comments / Employee Feedback')}</Typography>
              {comments.length ? <Stack spacing={1}>{comments.map((row) => <Paper key={`${row.email}-${row.feedback_updated_at}`} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}><Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={0.75}><Box sx={{ minWidth: 0 }}><Typography fontWeight={800}>{row.name || tr('Unknown employee')} <Typography component="span" variant="body2" color="text.secondary">· {row.area} · {row.branch}</Typography></Typography><Typography variant="body2" sx={{ mt: 0.5, color: '#334155', overflowWrap: 'anywhere' }}>{row.comment}</Typography></Box><Stack alignItems={{ xs: 'flex-start', sm: 'flex-end' }} spacing={0.5} flexShrink={0}><Reaction value={row.reaction} tr={tr} /><Typography variant="caption" color="text.secondary">{dateTime(row.feedback_updated_at, isArabic)}</Typography></Stack></Stack></Paper>)}</Stack> : <Typography color="text.secondary">{tr('No comments have been submitted for this Brief.')}</Typography>}
            </Box>
          </Stack>}
    </DialogContent>
    <DialogActions sx={{ px: 2.5, py: 1.5 }}><Button onClick={onExport} disabled={loading || exportLoading || !analytics}>{exportLoading ? tr('Exporting...') : tr('Export Excel')}</Button><Button onClick={onClose} disabled={loading || exportLoading}>{tr('Close')}</Button></DialogActions>
  </Dialog>;
}