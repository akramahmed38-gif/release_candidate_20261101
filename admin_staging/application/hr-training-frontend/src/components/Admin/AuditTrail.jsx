import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  MenuItem,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { DeleteSweep, Download, Refresh } from '@mui/icons-material';
import { auditService } from '../../services/auth';
import { useLanguage } from '../../context/LanguageContext';

const roleOptions = ['', 'admin', 'auditor', 'hr', 'retail', 'employee', 'anonymous'];
const methodOptions = ['', 'GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
const pageSizeOptions = [20, 50, 100];

const formatDateTime = (value, locale) => {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '-';
  return parsed.toLocaleString(locale, {
    timeZone: 'Africa/Cairo',
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

const AuditTrail = () => {
  const { t, isArabic } = useLanguage();
  const tr = useCallback((en, ar) => t(en, ar), [t]);

  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [purgeLoading, setPurgeLoading] = useState(false);
  const [alert, setAlert] = useState({ show: false, severity: 'success', message: '' });

  const [filters, setFilters] = useState({
    search: '',
    actor_email: '',
    actor_role: '',
    method: '',
    path_contains: '',
    status_code: '',
    from_ts: '',
    to_ts: '',
  });

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const response = await auditService.getLogs({
        page: page + 1,
        page_size: pageSize,
        search: filters.search || undefined,
        actor_email: filters.actor_email || undefined,
        actor_role: filters.actor_role || undefined,
        method: filters.method || undefined,
        path_contains: filters.path_contains || undefined,
        status_code: filters.status_code ? Number(filters.status_code) : undefined,
        from_ts: filters.from_ts || undefined,
        to_ts: filters.to_ts || undefined,
        sort_by: 'timestamp_utc',
        sort_dir: 'desc',
      });
      setLogs(response.data.logs || []);
      setTotal(response.data.total || 0);
    } catch (error) {
      setAlert({
        show: true,
        severity: 'error',
        message: error.response?.data?.message || tr('Failed to load audit logs', 'فشل تحميل سجل العمليات'),
      });
    } finally {
      setLoading(false);
    }
  }, [filters, page, pageSize, tr]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const handleApplyFilters = () => {
    setPage(0);
    loadLogs();
  };

  const handleResetFilters = () => {
    setFilters({
      search: '',
      actor_email: '',
      actor_role: '',
      method: '',
      path_contains: '',
      status_code: '',
      from_ts: '',
      to_ts: '',
    });
    setPage(0);
  };

  const exportParams = useMemo(
    () => ({
      search: filters.search || undefined,
      actor_email: filters.actor_email || undefined,
      actor_role: filters.actor_role || undefined,
      method: filters.method || undefined,
      path_contains: filters.path_contains || undefined,
      status_code: filters.status_code ? Number(filters.status_code) : undefined,
      from_ts: filters.from_ts || undefined,
      to_ts: filters.to_ts || undefined,
      sort_by: 'timestamp_utc',
      sort_dir: 'desc',
    }),
    [filters]
  );

  const handleExport = async () => {
    setExportLoading(true);
    try {
      const response = await auditService.exportLogs(exportParams);
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `audit-trail-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.xlsx`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      setAlert({
        show: true,
        severity: 'error',
        message: error.response?.data?.message || tr('Export failed', 'فشل التصدير'),
      });
    } finally {
      setExportLoading(false);
    }
  };

  const handlePurge = async () => {
    if (!window.confirm(tr('Purge audit logs? This cannot be undone.', 'حذف سجل العمليات؟ لا يمكن التراجع عن هذا الإجراء.'))) {
      return;
    }
    setPurgeLoading(true);
    try {
      await auditService.purgeLogs(null);
      setAlert({ show: true, severity: 'success', message: tr('Audit logs purged', 'تم حذف سجل العمليات') });
      setPage(0);
      loadLogs();
    } catch (error) {
      setAlert({
        show: true,
        severity: 'error',
        message: error.response?.data?.message || tr('Purge failed', 'فشل حذف السجل'),
      });
    } finally {
      setPurgeLoading(false);
    }
  };

  return (
    <Box sx={{ direction: isArabic ? 'rtl' : 'ltr' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="h4" fontWeight="bold">
          {tr('Audit Trail', 'سجل العمليات')}
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', width: { xs: '100%', md: 'auto' } }}>
          <Button variant="outlined" startIcon={<Refresh />} onClick={loadLogs} sx={{ width: { xs: '100%', sm: 'auto' } }}>
            {tr('Refresh', 'تحديث')}
          </Button>
          <Button variant="outlined" startIcon={<Download />} onClick={handleExport} disabled={exportLoading} sx={{ width: { xs: '100%', sm: 'auto' } }}>
            {exportLoading ? tr('Exporting...', 'جارٍ التصدير...') : tr('Export XLSX', 'تصدير XLSX')}
          </Button>
          <Button color="error" variant="contained" startIcon={<DeleteSweep />} onClick={handlePurge} disabled={purgeLoading} sx={{ width: { xs: '100%', sm: 'auto' } }}>
            {purgeLoading ? tr('Purging...', 'جارٍ الحذف...') : tr('Purge Logs', 'حذف السجل')}
          </Button>
        </Box>
      </Box>

      {alert.show && (
        <Alert severity={alert.severity} sx={{ mb: 2 }} onClose={() => setAlert((prev) => ({ ...prev, show: false }))}>
          {alert.message}
        </Alert>
      )}

      <Card sx={{ mb: 2 }}>
        <CardContent>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: {
                xs: '1fr',
                sm: 'repeat(2, minmax(0, 1fr))',
                md: 'repeat(4, minmax(0, 1fr))',
              },
              gap: 1.5,
              alignItems: 'stretch',
              '& .audit-filter-field .MuiInputBase-root': {
                minHeight: 42,
              },
            }}
          >
            <TextField
              className="audit-filter-field"
              fullWidth
              size="small"
              label={tr('Search', 'بحث')}
              value={filters.search}
              onChange={(e) => handleFilterChange('search', e.target.value)}
            />
            <TextField
              className="audit-filter-field"
              fullWidth
              size="small"
              label={tr('Actor Email', 'بريد المستخدم')}
              value={filters.actor_email}
              onChange={(e) => handleFilterChange('actor_email', e.target.value)}
            />
            <TextField
              className="audit-filter-field"
              fullWidth
              select
              size="small"
              label={tr('Role', 'الدور')}
              value={filters.actor_role}
              onChange={(e) => handleFilterChange('actor_role', e.target.value)}
            >
              {roleOptions.map((role) => (
                <MenuItem key={role || 'all'} value={role}>
                  {role || tr('All', 'الكل')}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              className="audit-filter-field"
              fullWidth
              select
              size="small"
              label={tr('Method', 'الطريقة')}
              value={filters.method}
              onChange={(e) => handleFilterChange('method', e.target.value)}
            >
              {methodOptions.map((method) => (
                <MenuItem key={method || 'all'} value={method}>
                  {method || tr('All', 'الكل')}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              className="audit-filter-field"
              fullWidth
              size="small"
              label={tr('Status Code', 'كود الحالة')}
              value={filters.status_code}
              onChange={(e) => handleFilterChange('status_code', e.target.value)}
            />
            <TextField
              className="audit-filter-field"
              fullWidth
              size="small"
              label={tr('Path contains', 'المسار يحتوي')}
              value={filters.path_contains}
              onChange={(e) => handleFilterChange('path_contains', e.target.value)}
            />
            <TextField
              className="audit-filter-field"
              fullWidth
              size="small"
              type="datetime-local"
              label={tr('From', 'من')}
              value={filters.from_ts}
              InputLabelProps={{ shrink: true }}
              onChange={(e) => handleFilterChange('from_ts', e.target.value)}
            />
            <TextField
              className="audit-filter-field"
              fullWidth
              size="small"
              type="datetime-local"
              label={tr('To', 'إلى')}
              value={filters.to_ts}
              InputLabelProps={{ shrink: true }}
              onChange={(e) => handleFilterChange('to_ts', e.target.value)}
            />
          </Box>
          <Box sx={{ mt: 1.5, display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 180px))' }, gap: 1, justifyContent: 'start' }}>
            <Button variant="contained" onClick={handleApplyFilters} sx={{ width: { xs: '100%', sm: 'auto' } }}>
              {tr('Apply', 'تطبيق')}
            </Button>
            <Button variant="outlined" onClick={handleResetFilters} sx={{ width: { xs: '100%', sm: 'auto' } }}>
              {tr('Reset', 'إعادة ضبط')}
            </Button>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent sx={{ p: 0 }}>
          <TableContainer sx={{ maxWidth: '100%', overflowX: 'auto' }}>
            <Table size="small" sx={{ minWidth: 1120 }}>
              <TableHead>
                <TableRow>
                  <TableCell><strong>{tr('Time (Cairo)', 'الوقت (القاهرة)')}</strong></TableCell>
                  <TableCell><strong>{tr('Actor Email', 'بريد المستخدم')}</strong></TableCell>
                  <TableCell><strong>{tr('Role', 'الدور')}</strong></TableCell>
                  <TableCell><strong>{tr('Action', 'الإجراء')}</strong></TableCell>
                  <TableCell><strong>{tr('Method', 'الطريقة')}</strong></TableCell>
                  <TableCell><strong>{tr('Path', 'المسار')}</strong></TableCell>
                  <TableCell><strong>{tr('Status', 'الحالة')}</strong></TableCell>
                  <TableCell><strong>{tr('Duration', 'المدة')}</strong></TableCell>
                  <TableCell><strong>{tr('IP', 'عنوان IP')}</strong></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={9} align="center" sx={{ py: 5 }}>
                      <CircularProgress size={28} />
                    </TableCell>
                  </TableRow>
                ) : logs.length ? (
                  logs.map((row) => (
                    <TableRow key={row.event_id || `${row.timestamp_utc}-${row.path}-${row.method}`}>
                      <TableCell>{formatDateTime(row.timestamp_cairo || row.timestamp_utc, isArabic ? 'ar-EG' : 'en-US')}</TableCell>
                      <TableCell sx={{ direction: 'ltr', unicodeBidi: 'plaintext' }}>{row.actor_email || '-'}</TableCell>
                      <TableCell>{row.actor_role || '-'}</TableCell>
                      <TableCell>{row.action || '-'}</TableCell>
                      <TableCell>{row.method || '-'}</TableCell>
                      <TableCell>{row.path || '-'}</TableCell>
                      <TableCell>{row.status_code ?? '-'}</TableCell>
                      <TableCell>{row.duration_ms != null ? `${row.duration_ms} ms` : '-'}</TableCell>
                      <TableCell>{row.ip_address || '-'}</TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={9} align="center" sx={{ py: 4 }}>
                      {tr('No audit records found', 'لا توجد سجلات')}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={total}
            page={page}
            rowsPerPage={pageSize}
            onPageChange={(_, nextPage) => setPage(nextPage)}
            onRowsPerPageChange={(event) => {
              const nextSize = Number(event.target.value) || 20;
              setPageSize(nextSize);
              setPage(0);
            }}
            rowsPerPageOptions={pageSizeOptions}
          />
        </CardContent>
      </Card>
    </Box>
  );
};

export default AuditTrail;
