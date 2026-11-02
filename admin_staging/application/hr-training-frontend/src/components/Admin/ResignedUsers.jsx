import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  InputAdornment,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TableSortLabel,
  TextField,
  Typography,
} from '@mui/material';
import { Autorenew, Download, PersonOff, Refresh, Search } from '@mui/icons-material';
import { resignedUsersService } from '../../services/auth';
import { useLanguage } from '../../context/LanguageContext';

const SORTABLE_COLUMNS = {
  employee_name: { en: 'Employee Name', ar: 'اسم الموظف' },
  last_login_at: { en: 'Last Successful Login', ar: 'آخر تسجيل دخول ناجح' },
  resigned_at: { en: 'Resigned At', ar: 'تاريخ التحويل إلى مستقيل' },
  inactivity_days: { en: 'Inactivity Days', ar: 'أيام عدم النشاط' },
};

const ResignedUsers = () => {
  const { t, isArabic } = useLanguage();
  const tr = useCallback((en, ar) => t(en, ar), [t]);

  const [rows, setRows] = useState([]);
  const [totalRecords, setTotalRecords] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [alert, setAlert] = useState({ show: false, severity: 'success', message: '' });
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [sortBy, setSortBy] = useState('resigned_at');
  const [sortDir, setSortDir] = useState('desc');
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [reactivationDialog, setReactivationDialog] = useState({
    open: false,
    employee: null,
  });
  const [reactivationReason, setReactivationReason] = useState('');
  const [operationLoading, setOperationLoading] = useState({
    refresh: false,
    export: false,
    reactivate: false,
  });

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
    }, 300);

    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const activeParams = useMemo(
    () => ({
      page: page + 1,
      page_size: pageSize,
      sort_by: sortBy,
      sort_dir: sortDir,
      ...(search ? { search } : {}),
    }),
    [page, pageSize, search, sortBy, sortDir]
  );

  const setLoadingFlag = useCallback((key, value) => {
    setOperationLoading((prev) => ({ ...prev, [key]: value }));
  }, []);

  const showAlert = useCallback((severity, message) => {
    setAlert({ show: true, severity, message });
  }, []);

  const dispatchDashboardRefresh = useCallback(() => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('hr-training-dashboard-refresh'));
    }
  }, []);

  const formatDateTime = useCallback(
    (value) => {
      if (!value) {
        return '-';
      }
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) {
        return '-';
      }
      return new Intl.DateTimeFormat(isArabic ? 'ar-EG' : 'en-GB', {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone: 'Africa/Cairo',
      }).format(date);
    },
    [isArabic]
  );

  const formatBranch = useCallback((row) => {
    const branchName = row?.branch_name || '';
    const branchCode = row?.branch_code || '';
    if (branchName && branchCode) {
      return `${branchName} (${branchCode})`;
    }
    return branchName || branchCode || '-';
  }, []);

  const downloadBlobResponse = useCallback((response, fallbackName) => {
    const contentDisposition = response?.headers?.['content-disposition'] || '';
    const match = contentDisposition.match(/filename="([^"]+)"/i);
    const filename = match?.[1] || fallbackName;
    const blob = new Blob([response.data], {
      type:
        response?.headers?.['content-type'] ||
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  }, []);

  const loadRows = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await resignedUsersService.list(activeParams);
      const payload = response?.data || {};
      setRows(payload.items || []);
      setTotalRecords(Number(payload.total_records || 0));
    } catch (err) {
      setRows([]);
      setTotalRecords(0);
      setError(
        err?.response?.data?.message ||
          tr('Failed to load resigned users.', 'تعذر تحميل المستخدمين المستقيلين.')
      );
    } finally {
      setLoading(false);
      setLoadingFlag('refresh', false);
    }
  }, [activeParams, setLoadingFlag, tr]);

  useEffect(() => {
    loadRows();
  }, [loadRows]);

  const handleRefresh = useCallback(async () => {
    setLoadingFlag('refresh', true);
    await loadRows();
  }, [loadRows, setLoadingFlag]);

  const handleSort = useCallback(
    (column) => {
      if (!SORTABLE_COLUMNS[column]) {
        return;
      }
      setPage(0);
      setSortDir((prev) => (sortBy === column && prev === 'desc' ? 'asc' : 'desc'));
      setSortBy(column);
    },
    [sortBy]
  );

  const handleExport = useCallback(async () => {
    setLoadingFlag('export', true);
    try {
      const response = await resignedUsersService.export({
        ...activeParams,
        format: 'excel',
      });
      downloadBlobResponse(response, 'resigned_users.xlsx');
    } catch (err) {
      showAlert(
        'error',
        err?.response?.data?.message ||
          tr('Failed to export resigned users.', 'تعذر تصدير المستخدمين المستقيلين.')
      );
    } finally {
      setLoadingFlag('export', false);
    }
  }, [activeParams, downloadBlobResponse, setLoadingFlag, showAlert, tr]);

  const handleReactivate = useCallback(async () => {
    if (!reactivationDialog.employee) {
      return;
    }

    setLoadingFlag('reactivate', true);
    try {
      await resignedUsersService.reactivate(
        reactivationDialog.employee.employee_id,
        reactivationReason.trim()
      );
      setReactivationDialog({ open: false, employee: null });
      setReactivationReason('');
      showAlert(
        'success',
        tr('User reactivated successfully.', 'تمت إعادة تفعيل المستخدم بنجاح.')
      );
      await loadRows();
      dispatchDashboardRefresh();
    } catch (err) {
      showAlert(
        'error',
        err?.response?.data?.message ||
          tr('Failed to reactivate user.', 'تعذر إعادة تفعيل المستخدم.')
      );
    } finally {
      setLoadingFlag('reactivate', false);
    }
  }, [
    dispatchDashboardRefresh,
    loadRows,
    reactivationDialog.employee,
    reactivationReason,
    setLoadingFlag,
    showAlert,
    tr,
  ]);

  return (
    <Box sx={{ direction: isArabic ? 'rtl' : 'ltr' }}>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        justifyContent="space-between"
        alignItems={{ xs: 'flex-start', md: 'center' }}
        spacing={2}
        sx={{ mb: 3 }}
      >
        <Box>
          <Stack direction="row" spacing={1.25} alignItems="center" sx={{ mb: 1 }}>
            <PersonOff sx={{ color: '#D8AE00' }} />
            <Typography variant="h3" sx={{ fontWeight: 800, color: 'secondary.main' }}>
              {tr('Resigned Users', 'المستخدمون المستقيلون')}
            </Typography>
          </Stack>
          <Typography color="text.secondary" sx={{ maxWidth: 860 }}>
            {tr(
              'Review resigned accounts and reactivate returned employees without losing history.',
              'راجع الحسابات المستقيلة وأعد تفعيل الموظفين العائدين بدون فقدان التاريخ السابق.'
            )}
          </Typography>
        </Box>

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <Button
            variant="outlined"
            startIcon={operationLoading.refresh ? <CircularProgress size={16} /> : <Refresh />}
            onClick={handleRefresh}
            disabled={loading || operationLoading.export || operationLoading.reactivate}
          >
            {tr('Refresh', 'تحديث')}
          </Button>
          <Button
            variant="outlined"
            startIcon={operationLoading.export ? <CircularProgress size={16} /> : <Download />}
            onClick={handleExport}
            disabled={operationLoading.export || loading}
          >
            {tr('Export', 'تصدير')}
          </Button>
        </Stack>
      </Stack>

      {alert.show ? (
        <Alert
          severity={alert.severity}
          onClose={() => setAlert((prev) => ({ ...prev, show: false }))}
          sx={{ mb: 2 }}
        >
          {alert.message}
        </Alert>
      ) : null}

      <Card sx={{ mb: 2.5, maxWidth: 320 }}>
        <CardContent>
          <Typography variant="body1" color="text.secondary" sx={{ mb: 1 }}>
            {tr('Resigned Users', 'المستخدمون المستقيلون')}
          </Typography>
          <Typography variant="h2" sx={{ fontWeight: 800, color: 'secondary.main', lineHeight: 1 }}>
            {loading ? '--' : totalRecords}
          </Typography>
        </CardContent>
      </Card>

      <Card>
        <CardContent sx={{ p: 0 }}>
          <Stack
            direction={{ xs: 'column', md: 'row' }}
            alignItems={{ md: 'center' }}
            justifyContent="space-between"
            spacing={1.5}
            sx={{ p: 2.25, pb: 1.25 }}
          >
            <Box>
              <Typography variant="h6" sx={{ fontWeight: 800, color: 'secondary.main' }}>
                {tr('Resigned Users Table', 'جدول المستخدمين المستقيلين')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {tr(`${totalRecords} total records`, `${totalRecords} إجمالي السجلات`)}
              </Typography>
            </Box>
            <TextField
              fullWidth
              size="small"
              value={searchInput}
              onChange={(event) => {
                setSearchInput(event.target.value);
                setPage(0);
              }}
              placeholder={tr('Search name, HR ID, email, branch, or role', 'ابحث بالاسم أو الرقم الوظيفي أو البريد أو الفرع أو الدور')}
              inputProps={{ 'aria-label': tr('Search resigned users', 'البحث في المستخدمين المستقيلين') }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search fontSize="small" color="action" />
                  </InputAdornment>
                ),
              }}
              sx={{ maxWidth: { md: 440 } }}
            />
          </Stack>

          {error ? (
            <Alert severity="error" sx={{ mx: 2.25, mb: 2 }}>
              {error}
            </Alert>
          ) : null}

          <TableContainer sx={{ maxHeight: 680, overflow: 'auto' }}>
            <Table stickyHeader size="small" sx={{ minWidth: 1200 }}>
              <TableHead>
                <TableRow>
                  <TableCell sortDirection={sortBy === 'employee_name' ? sortDir : false}>
                    <TableSortLabel
                      active={sortBy === 'employee_name'}
                      direction={sortBy === 'employee_name' ? sortDir : 'asc'}
                      onClick={() => handleSort('employee_name')}
                    >
                      {tr('Employee Name', 'اسم الموظف')}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell>{tr('HR ID', 'الرقم الوظيفي')}</TableCell>
                  <TableCell>{tr('Email', 'البريد الإلكتروني')}</TableCell>
                  <TableCell>{tr('Branch', 'الفرع')}</TableCell>
                  <TableCell>{tr('Role', 'الدور')}</TableCell>
                  <TableCell sortDirection={sortBy === 'last_login_at' ? sortDir : false}>
                    <TableSortLabel
                      active={sortBy === 'last_login_at'}
                      direction={sortBy === 'last_login_at' ? sortDir : 'asc'}
                      onClick={() => handleSort('last_login_at')}
                    >
                      {tr('Last Successful Login', 'آخر تسجيل دخول ناجح')}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortBy === 'inactivity_days' ? sortDir : false}>
                    <TableSortLabel
                      active={sortBy === 'inactivity_days'}
                      direction={sortBy === 'inactivity_days' ? sortDir : 'asc'}
                      onClick={() => handleSort('inactivity_days')}
                    >
                      {tr('Inactivity Days', 'أيام عدم النشاط')}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortBy === 'resigned_at' ? sortDir : false}>
                    <TableSortLabel
                      active={sortBy === 'resigned_at'}
                      direction={sortBy === 'resigned_at' ? sortDir : 'asc'}
                      onClick={() => handleSort('resigned_at')}
                    >
                      {tr('Resigned At', 'تاريخ التحويل إلى مستقيل')}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell>{tr('Action', 'الإجراء')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={9} align="center" sx={{ py: 5 }}>
                      <CircularProgress />
                    </TableCell>
                  </TableRow>
                ) : rows.length ? (
                  rows.map((row) => (
                    <TableRow key={row.employee_id} hover>
                      <TableCell>{row.employee_name || '-'}</TableCell>
                      <TableCell>{row.hr_id || '-'}</TableCell>
                      <TableCell>{row.email || '-'}</TableCell>
                      <TableCell>{formatBranch(row)}</TableCell>
                      <TableCell>{row.role || '-'}</TableCell>
                      <TableCell>{formatDateTime(row.last_login_at)}</TableCell>
                      <TableCell>{row.inactivity_days ?? '-'}</TableCell>
                      <TableCell>{formatDateTime(row.resigned_at)}</TableCell>
                      <TableCell>
                        <Button
                          size="small"
                          variant="outlined"
                          startIcon={
                            operationLoading.reactivate &&
                            reactivationDialog.employee?.employee_id === row.employee_id ? (
                              <CircularProgress size={14} />
                            ) : (
                              <Autorenew />
                            )
                          }
                          onClick={() => {
                            setReactivationDialog({ open: true, employee: row });
                            setReactivationReason('');
                          }}
                        >
                          {tr('Reactivate', 'إعادة تفعيل')}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={9} align="center" sx={{ py: 5 }}>
                      <Typography color="text.secondary">
                        {tr('No resigned users found.', 'لا يوجد مستخدمون مستقيلون.')}
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>

          <TablePagination
            component="div"
            count={totalRecords}
            page={page}
            onPageChange={(_event, nextPage) => setPage(nextPage)}
            rowsPerPage={pageSize}
            onRowsPerPageChange={(event) => {
              setPageSize(Number(event.target.value));
              setPage(0);
            }}
            rowsPerPageOptions={[10, 25, 50, 100]}
            labelRowsPerPage={tr('Rows per page', 'عدد الصفوف في الصفحة')}
          />
        </CardContent>
      </Card>

      <Dialog
        open={reactivationDialog.open}
        onClose={() => setReactivationDialog({ open: false, employee: null })}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{tr('Reactivate User', 'إعادة تفعيل المستخدم')}</DialogTitle>
        <DialogContent>
          <Typography sx={{ mb: 1.25, fontWeight: 700 }}>
            {tr('Are you sure you want to reactivate this user?', 'هل أنت متأكد أنك تريد إعادة تفعيل هذا المستخدم؟')}
          </Typography>
          <Typography sx={{ mb: 0.75 }}>
            {tr('Employee Name', 'اسم الموظف')}: {reactivationDialog.employee?.employee_name || '-'}
          </Typography>
          <Typography sx={{ mb: 2 }}>
            {tr('HR ID', 'الرقم الوظيفي')}: {reactivationDialog.employee?.hr_id || '-'}
          </Typography>
          <TextField
            fullWidth
            multiline
            minRows={3}
            label={tr('Reactivation Note', 'ملاحظة إعادة التفعيل')}
            value={reactivationReason}
            onChange={(event) => setReactivationReason(event.target.value)}
            placeholder={tr(
              'Employee returned to the company',
              'عاد الموظف إلى الشركة'
            )}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReactivationDialog({ open: false, employee: null })}>
            {tr('Cancel', 'إلغاء')}
          </Button>
          <Button
            variant="contained"
            onClick={handleReactivate}
            disabled={operationLoading.reactivate}
            startIcon={operationLoading.reactivate ? <CircularProgress size={16} /> : <Autorenew />}
          >
            {tr('Confirm Reactivation', 'تأكيد إعادة التفعيل')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ResignedUsers;
