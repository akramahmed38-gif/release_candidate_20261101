import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Checkbox,
  ListItemText,
  OutlinedInput,
  Divider,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Paper,
  TablePagination,
  CircularProgress,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Tooltip,
} from '@mui/material';
import { Download, FilterList, Visibility } from '@mui/icons-material';
import { examService, userService } from '../../services/auth';
import { useLanguage } from '../../context/LanguageContext';

const defaultFilters = {
  regions: [],
  areas: [],
  branch_codes: [],
  divisions: [],
  titles: [],
  sub_departments: [],
};

const defaultPeriod = 'all';
const defaultRowsPerPage = 10;
const employeePerformanceStorageKey = 'hr-training-employee-performance-state';

const sanitizeExamJoinedState = (value) => {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
};

const readEmployeePerformanceState = () => {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const raw = window.sessionStorage.getItem(employeePerformanceStorageKey);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (_error) {
    return null;
  }
};

const sanitizeFilterState = (value) => {
  const candidate = value && typeof value === 'object' ? value : {};
  return {
    regions: Array.isArray(candidate.regions) ? candidate.regions : defaultFilters.regions,
    areas: Array.isArray(candidate.areas) ? candidate.areas : defaultFilters.areas,
    branch_codes: Array.isArray(candidate.branch_codes) ? candidate.branch_codes : defaultFilters.branch_codes,
    divisions: Array.isArray(candidate.divisions) ? candidate.divisions : defaultFilters.divisions,
    titles: Array.isArray(candidate.titles) ? candidate.titles : defaultFilters.titles,
    sub_departments: Array.isArray(candidate.sub_departments)
      ? candidate.sub_departments
      : defaultFilters.sub_departments,
  };
};

const buildInitialEmployeePerformanceState = () => {
  const stored = readEmployeePerformanceState();
  const rowsPerPage = Number.parseInt(stored?.rowsPerPage, 10);
  return {
    filters: sanitizeFilterState(stored?.filters),
    period: ['all', 'week', 'month', 'year'].includes(stored?.period) ? stored.period : defaultPeriod,
    rowsPerPage: [10, 25, 50, 100].includes(rowsPerPage) ? rowsPerPage : defaultRowsPerPage,
    examsJoined: sanitizeExamJoinedState(stored?.examsJoined),
  };
};

const renderSelectedValues = (selected, noneLabel = 'None', moreLabel = 'more') => {
  if (!selected?.length) {
    return noneLabel;
  }
  if (selected.length <= 2) {
    return selected.join(', ');
  }
  return `${selected.slice(0, 2).join(', ')} (+${selected.length - 2} ${moreLabel})`;
};

const MultiSelectDropdown = ({
  label,
  value,
  options,
  onChange,
  tr,
  getOptionValue = (option) => option,
  getOptionLabel = (option) => option,
}) => {
  const normalizedOptions = useMemo(
    () =>
      (options || [])
        .map((option) => ({
          value: getOptionValue(option),
          label: getOptionLabel(option),
        }))
        .filter((option) => option.value !== undefined && option.value !== null && `${option.value}`.trim() !== ''),
    [options, getOptionLabel, getOptionValue]
  );

  const optionValues = normalizedOptions.map((option) => option.value);
  const allSelected = optionValues.length > 0 && value.length === optionValues.length;
  const someSelected = value.length > 0 && !allSelected;
  const selectedLabels = normalizedOptions
    .filter((option) => value.includes(option.value))
    .map((option) => option.label);

  return (
    <FormControl fullWidth>
      <InputLabel>{label}</InputLabel>
      <Select
        multiple
        value={value}
        onChange={(event) => onChange(Array.isArray(event.target.value) ? event.target.value : [event.target.value])}
        input={<OutlinedInput label={label} />}
        renderValue={() => renderSelectedValues(selectedLabels, tr('All', 'الكل'), tr('more', 'أخرى'))}
        MenuProps={{ PaperProps: { sx: { maxHeight: 360 } } }}
      >
        <MenuItem
          value="__select_all__"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onChange(allSelected ? [] : optionValues);
          }}
        >
          <Checkbox checked={allSelected} indeterminate={someSelected} />
          <ListItemText primary={tr('Select all', 'تحديد الكل')} />
        </MenuItem>
        <Divider />
        {normalizedOptions.map((option) => (
          <MenuItem key={`${label}-${option.value}`} value={option.value}>
            <Checkbox checked={value.includes(option.value)} />
            <ListItemText primary={option.label} />
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
};

const EmployeePerformance = () => {
  const { t, isArabic } = useLanguage();
  const tr = useCallback((en, ar) => t(en, ar), [t]);
  const initialState = useMemo(() => buildInitialEmployeePerformanceState(), []);
  const [filters, setFilters] = useState(initialState.filters);
  const [audienceRegions, setAudienceRegions] = useState([]);
  const [audienceSettings, setAudienceSettings] = useState(null);
  const [rows, setRows] = useState([]);
  const [period, setPeriod] = useState(initialState.period);
  const [totalRecords, setTotalRecords] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(initialState.rowsPerPage);
  const [selectedExamsJoined, setSelectedExamsJoined] = useState(initialState.examsJoined);
  const [availableExamCounts, setAvailableExamCounts] = useState([]);
  const [sortBy, setSortBy] = useState('average_percentage');
  const [sortDir, setSortDir] = useState('desc');
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [alert, setAlert] = useState(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyRows, setHistoryRows] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyEmployee, setHistoryEmployee] = useState(null);

  const loadAudienceSettings = useCallback(async () => {
    try {
      const response = await userService.getAudienceHierarchy();
      const payload = response.data?.data || {};
      setAudienceRegions(payload.regions || []);
      setAudienceSettings(payload.filters || {});
    } catch (error) {
      console.error('Error loading audience settings:', error);
      setAlert({
        severity: 'error',
        message: error.response?.data?.message || tr('Unable to load audience settings', 'تعذر تحميل إعدادات الجمهور'),
      });
    }
  }, [tr]);

  useEffect(() => {
    loadAudienceSettings();
  }, [loadAudienceSettings]);

  const getAreasForRegions = useCallback(
    (regionsSelection) => {
      const pool =
        Array.isArray(regionsSelection) && regionsSelection.length > 0
          ? audienceRegions.filter((region) => regionsSelection.includes(region.region))
          : audienceRegions;
      const areaMap = new Map();
      pool.forEach((region) => {
        region.areas?.forEach((area) => {
          if (!areaMap.has(area.area)) {
            areaMap.set(area.area, { ...area, region: region.region });
          }
        });
      });
      return Array.from(areaMap.values());
    },
    [audienceRegions]
  );

  const areaOptions = useMemo(
    () => getAreasForRegions(filters.regions),
    [getAreasForRegions, filters.regions]
  );

  const getBranchesForSelection = useCallback(
    (regionsSelection, areasSelection) => {
      const areasPool = getAreasForRegions(regionsSelection);
      const filteredAreas =
        Array.isArray(areasSelection) && areasSelection.length > 0
          ? areasPool.filter((area) => areasSelection.includes(area.area))
          : areasPool;
      const branchMap = new Map();
      filteredAreas.forEach((area) => {
        area.branches?.forEach((branch) => {
          const branchCode = String(branch.branch_code || '');
          if (!branchCode) {
            return;
          }
          if (!branchMap.has(branchCode)) {
            branchMap.set(branchCode, { ...branch, branch_code: branchCode, area: area.area, region: area.region });
          }
        });
      });
      return Array.from(branchMap.values());
    },
    [getAreasForRegions]
  );

  const branchOptions = useMemo(
    () => getBranchesForSelection(filters.regions, filters.areas),
    [getBranchesForSelection, filters.regions, filters.areas]
  );

  const examCountOptions = useMemo(
    () =>
      Array.from(
        new Set(
          [1, 2, 3, ...availableExamCounts, selectedExamsJoined]
            .filter((value) => Number.isFinite(value) && value > 0)
            .map((value) => Number.parseInt(value, 10))
        )
      ).sort((a, b) => a - b),
    [availableExamCounts, selectedExamsJoined]
  );

  const regionOptions = useMemo(() => {
    const regions = audienceRegions?.map((region) => region.region) || [];
    return Array.from(new Set(regions)).sort((a, b) => a.localeCompare(b));
  }, [audienceRegions]);

  const availableOptions = (field) => {
    const options = audienceSettings?.[field] || [];
    const sanitized = options.filter((option) => Boolean(option?.trim?.() ?? option));
    return Array.from(new Set(sanitized)).sort((a, b) => a.localeCompare(b));
  };

  const handleRegionSelect = (values) => {
    const regionsList = values || [];
    const allowedAreas = getAreasForRegions(regionsList);
    const allowedAreaNames = new Set(allowedAreas.map((area) => area.area));
    const allowedBranches = getBranchesForSelection(regionsList, []);
    const allowedBranchCodes = new Set(allowedBranches.map((branch) => branch.branch_code));
    setFilters((prev) => ({
      ...prev,
      regions: regionsList,
      areas: prev.areas.filter((area) => allowedAreaNames.has(area)),
      branch_codes: prev.branch_codes.filter((code) => allowedBranchCodes.has(code)),
    }));
    setPage(0);
  };

  const handleAreaSelect = (values) => {
    const areasList = values || [];
    const allowedBranches = getBranchesForSelection(filters.regions, areasList);
    const allowedBranchCodes = new Set(allowedBranches.map((branch) => branch.branch_code));
    setFilters((prev) => ({
      ...prev,
      areas: areasList,
      branch_codes: prev.branch_codes.filter((code) => allowedBranchCodes.has(code)),
    }));
    setPage(0);
  };

  const handleBranchSelect = (branchCodes) => {
    const codesList = branchCodes || [];
    setFilters((prev) => ({
      ...prev,
      branch_codes: codesList,
    }));
    setPage(0);
  };

  const handleFilterSelect = (field, values) => {
    setFilters((prev) => ({
      ...prev,
      [field]: values,
    }));
    setPage(0);
  };

  const handleClearFilters = () => {
    setFilters(defaultFilters);
    setPeriod(defaultPeriod);
    setSelectedExamsJoined(null);
    setPage(0);
  };

  const fetchPerformance = useCallback(async () => {
    setLoading(true);
    setAlert(null);
    try {
      const response = await examService.getEmployeePerformance({
        filters,
        period,
        exams_joined: selectedExamsJoined,
        page: page + 1,
        page_size: rowsPerPage,
        sort_by: sortBy,
        sort_dir: sortDir,
      });
      const payload = response.data || {};
      setRows(payload.employees || []);
      setTotalRecords(payload.total_records || 0);
      setAvailableExamCounts(
        Array.isArray(payload.available_exam_counts)
          ? payload.available_exam_counts
              .map((value) => Number.parseInt(value, 10))
              .filter((value) => Number.isFinite(value) && value > 0)
          : []
      );
    } catch (error) {
      console.error('Error loading performance data:', error);
      setAlert({
        severity: 'error',
        message: error.response?.data?.message || tr('Unable to load employee performance', 'تعذر تحميل أداء الموظفين'),
      });
    } finally {
      setLoading(false);
    }
  }, [filters, page, period, rowsPerPage, selectedExamsJoined, sortBy, sortDir, tr]);

  useEffect(() => {
    fetchPerformance();
  }, [fetchPerformance]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    try {
      window.sessionStorage.setItem(
        employeePerformanceStorageKey,
          JSON.stringify({
            filters,
            period,
            rowsPerPage,
            examsJoined: selectedExamsJoined,
          })
        );
    } catch (_error) {
      // Ignore storage failures and keep the live state.
    }
  }, [filters, period, rowsPerPage, selectedExamsJoined]);

  const handleChangePage = (_event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleSort = (field) => {
    if (sortBy === field) {
      setSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(field);
      setSortDir(
        field === 'average_percentage' || field === 'exams_joined'
          ? 'desc'
          : 'asc'
      );
    }
    setPage(0);
  };

  const handleExamsJoinedFilterChange = (event) => {
    const nextValue = sanitizeExamJoinedState(event.target.value);
    setSelectedExamsJoined(nextValue);
    setPage(0);
  };

  const handleDownload = async () => {
    setExporting(true);
    setAlert(null);
    try {
      const response = await examService.downloadEmployeePerformance({
        filters,
        period,
        exams_joined: selectedExamsJoined,
        sort_by: sortBy,
        sort_dir: sortDir,
      });
      const blob = new Blob([response.data], {
        type:
          response.headers['content-type'] ||
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      const stamp = new Date().toISOString().replace(/[:T]/g, '-').split('.')[0];
      link.href = url;
      link.download = `employee_performance_${stamp}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error downloading performance data:', error);
      setAlert({
        severity: 'error',
        message: error.response?.data?.message || tr('Unable to download employee performance', 'تعذر تنزيل أداء الموظفين'),
      });
    } finally {
      setExporting(false);
    }
  };

  const handleOpenHistory = async (row) => {
    if (!row?.employee_id) {
      return;
    }
    setHistoryEmployee(row);
    setHistoryOpen(true);
    setHistoryLoading(true);
    setHistoryRows([]);
    try {
      const response = await examService.getEmployeePerformanceHistory(row.employee_id);
      const payload = response.data || {};
      setHistoryRows(payload.history || []);
    } catch (error) {
      console.error('Error loading employee history:', error);
      setAlert({
        severity: 'error',
        message: error.response?.data?.message || tr('Unable to load employee history', 'تعذر تحميل سجل الموظف'),
      });
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleCloseHistory = () => {
    setHistoryOpen(false);
    setHistoryRows([]);
    setHistoryEmployee(null);
  };

  const periodLabel = useMemo(() => {
    const labels = {
      all: tr('All Time', 'كل الوقت'),
      week: tr('This Week', 'هذا الأسبوع'),
      month: tr('This Month', 'هذا الشهر'),
      year: tr('This Year', 'هذه السنة'),
    };
    return labels[period] || labels.all;
  }, [period, tr]);

  return (
    <Box sx={{ direction: isArabic ? 'rtl' : 'ltr' }}>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: { xs: 'stretch', sm: 'center' },
          mb: 2,
          gap: 1,
          flexWrap: 'wrap',
        }}
      >
        <Typography variant="h5" fontWeight="bold">
          {tr('Employee Performance', 'أداء الموظفين')}
        </Typography>
        <Button
          variant="outlined"
          startIcon={<Download />}
          onClick={handleDownload}
          disabled={exporting}
          sx={{ width: { xs: '100%', sm: 'auto' } }}
        >
          {exporting ? tr('Preparing...', 'جارٍ التحضير...') : tr('Download Excel', 'تنزيل إكسل')}
        </Button>
      </Box>

      {alert && (
        <Alert severity={alert.severity} sx={{ mb: 2 }}>
          {alert.message}
        </Alert>
      )}

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: 2,
              alignItems: 'start',
            }}
          >
            <MultiSelectDropdown
              label={tr('Regions', 'الأقاليم')}
              value={filters.regions}
              options={regionOptions}
              onChange={handleRegionSelect}
              tr={tr}
            />
            <MultiSelectDropdown
              label={tr('Areas', 'المناطق')}
              value={filters.areas}
              options={areaOptions}
              onChange={handleAreaSelect}
              tr={tr}
              getOptionValue={(area) => area.area}
              getOptionLabel={(area) => `${area.area}${area.region ? ` (${area.region})` : ''}`}
            />
            <MultiSelectDropdown
              label={tr('Branches', 'الفروع')}
              value={filters.branch_codes}
              options={branchOptions}
              onChange={handleBranchSelect}
              tr={tr}
              getOptionValue={(branch) => branch.branch_code}
              getOptionLabel={(branch) => `${branch.branch_name} (${branch.branch_code})`}
            />
            <MultiSelectDropdown
              label={tr('Divisions', 'القطاعات')}
              value={filters.divisions}
              options={availableOptions('divisions')}
              onChange={(values) => handleFilterSelect('divisions', values)}
              tr={tr}
            />
            <MultiSelectDropdown
              label={tr('Titles', 'المسميات الوظيفية')}
              value={filters.titles}
              options={availableOptions('titles')}
              onChange={(values) => handleFilterSelect('titles', values)}
              tr={tr}
            />
            <MultiSelectDropdown
              label={tr('Sub Departments', 'الإدارات الفرعية')}
              value={filters.sub_departments}
              options={availableOptions('sub_departments')}
              onChange={(values) => handleFilterSelect('sub_departments', values)}
              tr={tr}
            />
            <FormControl fullWidth>
              <InputLabel>{tr('Period', 'الفترة')}</InputLabel>
              <Select
                value={period}
                label={tr('Period', 'الفترة')}
                onChange={(event) => {
                  setPeriod(event.target.value);
                  setPage(0);
                }}
              >
                <MenuItem value="all">{tr('All Time', 'كل الوقت')}</MenuItem>
                <MenuItem value="week">{tr('This Week', 'هذا الأسبوع')}</MenuItem>
                <MenuItem value="month">{tr('This Month', 'هذا الشهر')}</MenuItem>
                <MenuItem value="year">{tr('This Year', 'هذه السنة')}</MenuItem>
              </Select>
            </FormControl>
            <FormControl fullWidth>
              <InputLabel>{tr('Exams Joined', 'الاختبارات المنضمة')}</InputLabel>
              <Select
                value={selectedExamsJoined ?? ''}
                label={tr('Exams Joined', 'الاختبارات المنضمة')}
                onChange={handleExamsJoinedFilterChange}
              >
                <MenuItem value="">{tr('All exams', 'كل الاختبارات')}</MenuItem>
                {examCountOptions.map((count) => (
                  <MenuItem key={`exams-joined-${count}`} value={count}>
                    {count} {count === 1 ? tr('exam', 'اختبار') : tr('exams', 'اختبارات')}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end', gridColumn: '1 / -1' }}>
              <Button variant="outlined" onClick={handleClearFilters}>
                {tr('Clear Filters', 'مسح الفلاتر')}
              </Button>
            </Box>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <>
              <TableContainer component={Paper} elevation={0} sx={{ maxWidth: '100%', overflowX: 'auto' }}>
                <Table size="small" sx={{ minWidth: 960 }}>
                  <TableHead>
                    <TableRow sx={{ bgcolor: 'grey.100' }}>
                      <TableCell><strong>{tr('History', 'السجل')}</strong></TableCell>
                      <TableCell>
                        <TableSortLabel
                          active={sortBy === 'hr_id'}
                          direction={sortBy === 'hr_id' ? sortDir : 'asc'}
                          onClick={() => handleSort('hr_id')}
                          hideSortIcon={false}
                        >
                          <strong>{tr('HR ID', 'الرقم الوظيفي')}</strong>
                        </TableSortLabel>
                      </TableCell>
                      <TableCell>
                        <TableSortLabel
                          active={sortBy === 'name'}
                          direction={sortBy === 'name' ? sortDir : 'asc'}
                          onClick={() => handleSort('name')}
                          hideSortIcon={false}
                        >
                          <strong>{tr('Name', 'الاسم')}</strong>
                        </TableSortLabel>
                      </TableCell>
                      <TableCell>
                        <TableSortLabel
                          active={sortBy === 'branch_code'}
                          direction={sortBy === 'branch_code' ? sortDir : 'asc'}
                          onClick={() => handleSort('branch_code')}
                          hideSortIcon={false}
                        >
                          <strong>{tr('Branch Code', 'كود الفرع')}</strong>
                        </TableSortLabel>
                      </TableCell>
                      <TableCell>
                        <TableSortLabel
                          active={sortBy === 'exams_joined'}
                          direction={sortBy === 'exams_joined' ? sortDir : 'asc'}
                          onClick={() => handleSort('exams_joined')}
                          hideSortIcon={false}
                        >
                          <strong>{tr('Exams Joined', 'الاختبارات المنضمة')}</strong>
                        </TableSortLabel>
                        <Box
                          sx={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 0.5,
                            color: selectedExamsJoined !== null ? 'primary.main' : 'text.secondary',
                            fontSize: '0.75rem',
                          }}
                        >
                          <FilterList sx={{ fontSize: '0.9rem' }} />
                          {selectedExamsJoined !== null
                            ? `${tr('Exact', 'مطابق')}: ${selectedExamsJoined}`
                            : tr('All exams', 'كل الاختبارات')}
                        </Box>
                      </TableCell>
                      <TableCell>
                        <TableSortLabel
                          active={sortBy === 'average_percentage'}
                          direction={sortBy === 'average_percentage' ? sortDir : 'asc'}
                          onClick={() => handleSort('average_percentage')}
                          hideSortIcon={false}
                        >
                          <strong>{tr('Average Percentage', 'متوسط النسبة المئوية')}</strong>
                        </TableSortLabel>
                      </TableCell>
                      <TableCell><strong>{tr('Period', 'الفترة')}</strong></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rows.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} align="center">
                          {tr('No records found.', 'لا توجد بيانات.')}
                        </TableCell>
                      </TableRow>
                    ) : (
                      rows.map((row) => (
                        <TableRow key={row.employee_id}>
                          <TableCell>
                            <Tooltip title={tr('View history', 'عرض السجل')}>
                              <IconButton
                                size="small"
                                onClick={() => handleOpenHistory(row)}
                              >
                                <Visibility fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          </TableCell>
                          <TableCell>{row.hr_id}</TableCell>
                          <TableCell>{row.name}</TableCell>
                          <TableCell>{row.branch_code}</TableCell>
                          <TableCell>{row.exams_joined ?? 0}</TableCell>
                          <TableCell>
                            {row.average_percentage !== null && row.average_percentage !== undefined
                              ? `${row.average_percentage.toFixed(2)}%`
                              : '-'}
                          </TableCell>
                          <TableCell>{periodLabel}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
              <TablePagination
                component="div"
                count={totalRecords}
                page={page}
                onPageChange={handleChangePage}
                rowsPerPage={rowsPerPage}
                onRowsPerPageChange={handleChangeRowsPerPage}
                rowsPerPageOptions={[10, 25, 50]}
                labelRowsPerPage={tr('Rows per page', 'عدد الصفوف لكل صفحة')}
                labelDisplayedRows={({ from, to, count }) =>
                  `${from}-${to} ${tr('of', 'من')} ${
                    count !== -1 ? count : `${tr('more than', 'أكثر من')} ${to}`
                  }`
                }
              />
            </>
          )}
        </CardContent>
      </Card>

      <Dialog open={historyOpen} onClose={handleCloseHistory} maxWidth="lg" fullWidth>
        <DialogTitle>
          {historyEmployee
            ? `${tr('History', 'السجل')}: ${historyEmployee.name} (${historyEmployee.hr_id})`
            : tr('Employee History', 'سجل الموظف')}
        </DialogTitle>
        <DialogContent dividers>
          {historyLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <TableContainer component={Paper} elevation={0} sx={{ maxWidth: '100%', overflowX: 'auto' }}>
              <Table size="small" sx={{ minWidth: 900 }}>
                <TableHead>
                  <TableRow sx={{ bgcolor: 'grey.100' }}>
                    <TableCell><strong>{tr('Exam', 'الاختبار')}</strong></TableCell>
                    <TableCell><strong>{tr('Attempt', 'المحاولة')}</strong></TableCell>
                    <TableCell><strong>{tr('Total Score', 'إجمالي الدرجة')}</strong></TableCell>
                    <TableCell><strong>{tr('Max Score', 'أقصى درجة')}</strong></TableCell>
                    <TableCell><strong>{tr('Score %', 'نسبة الدرجة')}</strong></TableCell>
                    <TableCell><strong>{tr('Passed', 'النجاح')}</strong></TableCell>
                    <TableCell><strong>{tr('Submitted At', 'وقت التسليم')}</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {historyRows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} align="center">
                        {tr('No attempts found.', 'لا توجد محاولات.')}
                      </TableCell>
                    </TableRow>
                  ) : (
                    historyRows.map((attempt) => (
                      <TableRow key={`${attempt.exam_id}-${attempt.attempt_number}-${attempt.submitted_at || ''}`}>
                        <TableCell>{attempt.exam_title || attempt.exam_id}</TableCell>
                        <TableCell>{attempt.attempt_number}</TableCell>
                        <TableCell>{attempt.total_score ?? '-'}</TableCell>
                        <TableCell>{attempt.max_score ?? '-'}</TableCell>
                        <TableCell>
                          {attempt.score_percentage !== null && attempt.score_percentage !== undefined
                            ? `${attempt.score_percentage}%`
                            : '-'}
                        </TableCell>
                        <TableCell>{attempt.passed ? tr('Yes', 'نعم') : tr('No', 'لا')}</TableCell>
                        <TableCell>{attempt.submitted_at || '-'}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseHistory}>{tr('Close', 'إغلاق')}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default EmployeePerformance;
