import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Box,
  Card,
  Tabs,
  Tab,
  TextField,
  Button,
  IconButton,
  Typography,
  Stack,
  MenuItem,
  Chip,
  FormControlLabel,
  Checkbox,
  Paper,
  Alert,
  Grid,
  CircularProgress,
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tooltip,
  ToggleButton,
  ToggleButtonGroup,
  ListSubheader,
  ListItemText,
  InputAdornment,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material';
import {
  ArrowBack,
  Add,
  Bookmark,
  BookmarkBorder,
  Delete,
  Download,
  LibraryAdd,
  Save,
  DriveFileRenameOutline,
  LabelOutlined,
  Search,
  Star,
  StarBorder,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { examService, materialService, userService } from '../../services/auth';
import { useLanguage } from '../../context/LanguageContext';

const defaultAudience = {
  mode: 'all',
  filters: {
    hr_ids: [],
    titles: [],
    branch_codes: [],
    branches: [],
    areas: [],
    regions: [],
    divisions: [],
    departments: ['Retail'],
    sub_departments: [],
  },
  manual_hr_ids: [],
};

const audienceModes = [
  {
    value: 'all',
    titleKey: 'All Employees',
    // description: 'Every active employee will be able to take this exam.',
  },
  {
    value: 'filters',
    titleKey: 'Filtered Audience',
    // description: 'Select branches, departments, titles, or regions to target specific groups.',
  },
  {
    value: 'manual',
    titleKey: 'Bulk HR IDs',
    // description: 'Paste or type the exact HR IDs to target hand-picked employees.',
  },
];

const toDateInputValue = (value) => {
  if (!value) return '';
  if (typeof value === 'string' && value.includes('T')) {
    return value.split('T')[0];
  }
  return value;
};

const toTimeInputValue = (value) => {
  if (!value) return '';
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    const hours = String(value.getHours()).padStart(2, '0');
    const minutes = String(value.getMinutes()).padStart(2, '0');
    return `${hours}:${minutes}`;
  }
  if (typeof value === 'string') {
    if (value.includes('T')) {
      const [, timePartRaw = ''] = value.split('T');
      return timePartRaw.slice(0, 5);
    }
    if (/^\d{2}:\d{2}/.test(value)) {
      return value.slice(0, 5);
    }
  }
  return '';
};

const sanitizeTimeValue = (timeStr) => {
  if (!timeStr) return '00:00';
  const [hours = '00', minutes = '00'] = timeStr.split(':');
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
};

const buildDateTimeObject = (dateStr, timeStr) => {
  if (!dateStr) return null;
  const sanitizedTime = sanitizeTimeValue(timeStr);
  const date = new Date(`${dateStr}T${sanitizedTime}:00`);
  return Number.isNaN(date.getTime()) ? null : date;
};

const formatDateTimeForPayload = (dateStr, timeStr) => {
  if (!dateStr) return '';
  const sanitizedTime = sanitizeTimeValue(timeStr);
  return `${dateStr}T${sanitizedTime}:00`;
};

const getApiErrorMessage = (error, fallbackMessage) => {
  const payload = error?.response?.data;
  if (typeof payload?.signal === 'string' && payload.signal.trim()) {
    return payload.signal;
  }
  if (typeof payload?.message === 'string' && payload.message.trim()) {
    return payload.message;
  }
  if (Array.isArray(payload?.detail) && payload.detail.length > 0) {
    return payload.detail
      .map((item) => item?.msg || item?.message)
      .filter(Boolean)
      .join(' | ');
  }
  if (typeof payload?.detail === 'string' && payload.detail.trim()) {
    return payload.detail;
  }
  if (typeof error?.message === 'string' && error.message.trim()) {
    return error.message;
  }
  return fallbackMessage;
};

const audienceFilterFields = [
  { key: 'departments', labelKey: 'Departments' },
  { key: 'divisions', labelKey: 'Divisions' },
  { key: 'titles', labelKey: 'Titles' },
  { key: 'sub_departments', labelKey: 'Sub Departments' },
  { key: 'hr_ids', labelKey: 'Specific HR IDs' },
];

const DEFAULT_GROUP_NAME = 'General';
const EXAM_LEVEL_OPTIONS = ['Entry Level', 'Professional Level', 'Expert Level'];

const CreateExam = ({ editMode = false, initialData = null, examId = null }) => {
  const navigate = useNavigate();
  const { t, isArabic } = useLanguage();
  const tr = useCallback((en, ar) => t(en, ar), [t]);
  const [activeTab, setActiveTab] = useState(0);
  const [alert, setAlert] = useState({ show: false, message: '', severity: 'success' });
  const [loading, setLoading] = useState(false);
  const [audience, setAudience] = useState(defaultAudience);
  const [audienceUpdateMode, setAudienceUpdateMode] = useState('replace');
  const [audienceSettings, setAudienceSettings] = useState(null);
  const [audienceRegions, setAudienceRegions] = useState([]);
  const [audienceEmployees, setAudienceEmployees] = useState([]);
  const [audienceFilterSearch, setAudienceFilterSearch] = useState({});
  const [audiencePreview, setAudiencePreview] = useState({
    loading: false,
    count: 0,
    hr_ids: [],
    employees: [],
  });
  const [audienceDialogOpen, setAudienceDialogOpen] = useState(false);
  const [audienceExcelDownloading, setAudienceExcelDownloading] = useState(false);
  const [bulkDialogOpen, setBulkDialogOpen] = useState(false);
  const [bulkUploadStatus, setBulkUploadStatus] = useState({ message: '', severity: 'info' });
  const [bulkUploading, setBulkUploading] = useState(false);
  const [questionGroups, setQuestionGroups] = useState([DEFAULT_GROUP_NAME]);
  const [activeGroupTab, setActiveGroupTab] = useState('ALL');
  const [groupDialogState, setGroupDialogState] = useState({
    open: false,
    mode: 'add',
    value: '',
    originalName: '',
  });
  const [questionBankDialogOpen, setQuestionBankDialogOpen] = useState(false);
  const [questionBankLoading, setQuestionBankLoading] = useState(false);
  const [questionBankFavoriteId, setQuestionBankFavoriteId] = useState(null);
  const [questionBankSavingIndex, setQuestionBankSavingIndex] = useState(null);
  const [questionBankItems, setQuestionBankItems] = useState([]);
  const [questionBankGroups, setQuestionBankGroups] = useState([]);
  const [bankGroupCounts, setBankGroupCounts] = useState({});
  const [groupQuery, setGroupQuery] = useState('');
  const [questionBankQuery, setQuestionBankQuery] = useState('');
  const [questionBankTypeFilter, setQuestionBankTypeFilter] = useState('ALL');
  const [questionBankFavoritesOnly, setQuestionBankFavoritesOnly] = useState(false);
  const [selectedBankQuestionIds, setSelectedBankQuestionIds] = useState([]);

  const [formData, setFormData] = useState({
    title: '',
    description: '',
    exam_status: 'Open',
    exam_level: 'Entry Level',
    duration_minutes: 60,
    passing_percent: 60,
    number_of_attempts_allowed: 1,
    start_date: '',
    start_time: '',
    end_date: '',
    end_time: '',
    material_ids: [],
    questions: [],
  });

  const localizedAudienceModes = useMemo(
    () =>
      audienceModes.map((mode) => ({
        ...mode,
        title: tr(
          mode.titleKey,
          mode.titleKey === 'All Employees'
            ? 'كل الموظفين'
            : mode.titleKey === 'Filtered Audience'
            ? 'جمهور مفلتر'
            : 'رفع أرقام وظيفية'
        ),
      })),
    [tr]
  );

  const localizedAudienceFilterFields = useMemo(
    () =>
      audienceFilterFields.map((field) => ({
        ...field,
        label:
          field.labelKey === 'Departments'
            ? tr('Departments', 'الإدارات')
            : field.labelKey === 'Divisions'
            ? tr('Divisions', 'القطاعات')
            : field.labelKey === 'Titles'
            ? tr('Titles', 'المسميات الوظيفية')
            : field.labelKey === 'Sub Departments'
            ? tr('Sub Departments', 'الإدارات الفرعية')
            : tr('Specific HR IDs', 'أرقام وظيفية محددة'),
      })),
    [tr]
  );

  const levelLabel = useCallback(
    (level) => {
      if (level === 'Professional Level') return tr('Professional Level', 'مستوى احترافي');
      if (level === 'Expert Level') return tr('Expert Level', 'مستوى خبير');
      return tr('Entry Level', 'مستوى مبتدئ');
    },
    [tr]
  );

  useEffect(() => {
    loadMaterials();
    loadAudienceSettings();
    // load once when component mounts
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (editMode && initialData) {
      const detectedGroups = Array.from(
        new Set(
          (initialData.questions || [])
            .map((question) => (question.question_group || '').trim())
            .filter(Boolean)
        )
      );
      const normalizedGroups = detectedGroups.length > 0 ? detectedGroups : [DEFAULT_GROUP_NAME];
      setQuestionGroups(normalizedGroups);
      const fallbackGroup = normalizedGroups[0] || DEFAULT_GROUP_NAME;

      const mappedQuestions = (initialData.questions || []).map((question) => {
        const baseChoices =
          question.question_type === 'Essay'
            ? []
            : (question.choices || []).map((choice) => ({
                choice_text: choice.choice_text || '',
                is_correct: Boolean(choice.is_correct),
              }));

        const resolvedGroup = (question.question_group || '').trim() || fallbackGroup;

        return {
          question_text: question.question_text || '',
          question_type: question.question_type || 'MCQ',
          points: question.points || 1,
          question_group: resolvedGroup,
          bank_question_id: question.bank_question_id || null,
          bank_is_favorite: Boolean(question.is_favorite),
          choices:
            baseChoices.length > 0
              ? baseChoices
              : [
                  { choice_text: '', is_correct: false },
                  { choice_text: '', is_correct: false },
                ],
        };
      });

      setFormData({
        title: initialData.title || '',
        description: initialData.description || '',
        exam_status: initialData.exam_status || 'Open',
        exam_level: initialData.exam_level || 'Entry Level',
        duration_minutes: initialData.duration_minutes || 60,
        passing_percent: initialData.passing_percent ?? 60,
        number_of_attempts_allowed: initialData.number_of_attempts_allowed ?? 1,
        start_date: toDateInputValue(initialData.start_date),
        start_time: toTimeInputValue(initialData.start_date),
        end_date: toDateInputValue(initialData.end_date),
        end_time: toTimeInputValue(initialData.end_date),
        material_ids: (initialData.materials || []).map((material) => material.material_id),
        questions: mappedQuestions,
      });

      const storedAudience = initialData.audience_config || initialData.audience;
      const resolvedAudience = {
        ...defaultAudience,
        ...(storedAudience || {}),
        filters: {
          ...defaultAudience.filters,
          ...(storedAudience?.filters || {}),
        },
        manual_hr_ids: storedAudience?.manual_hr_ids || [],
      };
      setAudience(resolvedAudience);
    }
  }, [editMode, initialData]);

  useEffect(() => {
    let isSubscribed = true;
    const fetchAudiencePreview = async () => {
      setAudiencePreview((prev) => ({ ...prev, loading: true }));
      try {
        const response = await userService.resolveAudience(audience);
        if (!isSubscribed) return;
        const data = response.data || {};
        setAudiencePreview({
          loading: false,
          count: data.count || 0,
          hr_ids: data.hr_ids || [],
          employees: data.employees || [],
        });
      } catch (error) {
        if (!isSubscribed) return;
        console.error('Error resolving audience:', error);
        setAudiencePreview({
          loading: false,
          count: 0,
          hr_ids: [],
          employees: [],
        });
      }
    };

    fetchAudiencePreview();
    return () => {
      isSubscribed = false;
    };
  }, [audience]);

  const loadMaterials = async () => {
    try {
      const response = await materialService.getAllMaterials();
      const availableMaterials = (response.data.materials || []).filter((material) => !material.is_deleted);
      setFormData((prev) => ({
        ...prev,
        material_ids: availableMaterials.map((material) => material.material_id),
      }));
    } catch (error) {
      console.error('Error loading materials:', error);
    }
  };

  const loadAudienceSettings = useCallback(async () => {
    try {
      const response = await userService.getAudienceHierarchy();
      const payload = response.data?.data || {};
      const regions = payload.regions || [];
      setAudienceRegions(regions);
      const flattenedEmployees = [];
      regions.forEach((region) => {
        region.areas?.forEach((area) => {
          area.branches?.forEach((branch) => {
            branch.employees?.forEach((employee) => {
              flattenedEmployees.push({
                ...employee,
                region: region.region,
                area: area.area,
                branch_code: branch.branch_code,
                branch_name: branch.branch_name,
                division: branch.division,
                sub_department: branch.sub_department,
              });
            });
          });
        });
      });
      setAudienceEmployees(flattenedEmployees);
      setAudienceSettings(payload.filters || {});
    } catch (error) {
      console.error('Error loading audience settings:', error);
      setAlert({
        show: true,
        message: error.response?.data?.message || tr('Unable to load audience settings', 'تعذر تحميل إعدادات الجمهور'),
        severity: 'error',
      });
    }
  }, [tr]);

  const updateAudience = (updater) => {
    setAudience((prev) => (typeof updater === 'function' ? updater(prev) : updater));
  };

  const handleAudienceModeChange = (mode) => {
    updateAudience((prev) => {
      if (mode === 'all') {
        return { ...defaultAudience };
      }
      if (mode === 'filters') {
        return {
          ...prev,
          mode,
          manual_hr_ids: [],
        };
      }
      if (mode === 'manual') {
        return {
          ...prev,
          mode,
          filters: { ...defaultAudience.filters },
        };
      }
      return { ...prev, mode };
    });
  };

  const handleFilterSelect = (field, values) => {
    updateAudience((prev) => ({
      ...prev,
      mode: prev.mode === 'all' ? 'filters' : prev.mode,
      filters: {
        ...prev.filters,
        [field]: values,
      },
    }));
  };

  const handleClearFilters = () => {
    updateAudience((prev) => ({
      ...prev,
      filters: { ...defaultAudience.filters },
    }));
  };

  const handleOpenBulkDialog = () => {
    setBulkUploadStatus({ message: '', severity: 'info' });
    setBulkDialogOpen(true);
  };

  const processBulkUploadFile = async (file) => {
    setBulkUploading(true);
    setBulkUploadStatus({ message: tr('Uploading file...', 'جارٍ رفع الملف...'), severity: 'info' });
    try {
      const response = await userService.bulkValidateAudience(file);
      const payload = response.data?.data || {};
      const hrIds = payload.hr_ids || [];
      const invalidValues = payload.invalid_values || [];
      const branchesWithoutEmployees = payload.branches_without_employees || [];
      updateAudience((prev) => ({
        ...prev,
        mode: 'manual',
        manual_hr_ids: hrIds,
      }));
      let statusMessage = `${tr('Loaded', 'تم تحميل')} ${hrIds.length} ${tr('HR IDs from', 'رقم وظيفي من')} ${file.name}.`;
      if (invalidValues.length) {
        const preview = invalidValues.slice(0, 5).join(', ');
        statusMessage += ` ${invalidValues.length} ${tr('invalid entries ignored', 'مدخلاً غير صالح تم تجاهله')}: ${preview}${
          invalidValues.length > 5 ? '...' : ''
        }`;
      }
      if (branchesWithoutEmployees.length) {
        statusMessage += ` ${tr('Branches without employees', 'فروع بدون موظفين')}: ${branchesWithoutEmployees.join(', ')}`;
      }
      setBulkUploadStatus({
        message: statusMessage,
        severity: invalidValues.length || branchesWithoutEmployees.length ? 'warning' : 'success',
      });
    } catch (error) {
      setBulkUploadStatus({
        message: error.response?.data?.message || tr('Failed to process the uploaded file.', 'فشل معالجة الملف المرفوع.'),
        severity: 'error',
      });
    } finally {
      setBulkUploading(false);
    }
  };

  const handleBulkFileInputChange = async (event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    await processBulkUploadFile(file);
    event.target.value = '';
  };

  const regionOptions = useMemo(() => {
    const regions = audienceRegions?.map((region) => region.region) || [];
    return Array.from(new Set(regions)).sort((a, b) => a.localeCompare(b));
  }, [audienceRegions]);

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
    () => getAreasForRegions(audience.filters.regions),
    [getAreasForRegions, audience.filters.regions]
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
          if (!branchMap.has(branch.branch_code)) {
            branchMap.set(branch.branch_code, { ...branch, area: area.area, region: area.region });
          }
        });
      });
      return Array.from(branchMap.values());
    },
    [getAreasForRegions]
  );

  const branchOptions = useMemo(
    () => getBranchesForSelection(audience.filters.regions, audience.filters.areas),
    [getBranchesForSelection, audience.filters.regions, audience.filters.areas]
  );
  const filteredEmployeeOptions = useMemo(() => {
    const branchCodes =
      audience.filters.branch_codes.length > 0
        ? new Set(audience.filters.branch_codes)
        : new Set(branchOptions.map((branch) => branch.branch_code));
    return audienceEmployees.filter((employee) => {
      if (!branchCodes.has(employee.branch_code)) {
        return false;
      }
      if (audience.filters.departments.length && !audience.filters.departments.includes(employee.department)) {
        return false;
      }
      if (audience.filters.divisions.length && !audience.filters.divisions.includes(employee.division)) {
        return false;
      }
      if (
        audience.filters.sub_departments.length &&
        !audience.filters.sub_departments.includes(employee.sub_department)
      ) {
        return false;
      }
      if (audience.filters.titles.length && !audience.filters.titles.includes(employee.title)) {
        return false;
      }
      return true;
    });
  }, [audienceEmployees, branchOptions, audience.filters]);

  const availableOptions = (field) => {
    if (field === 'hr_ids') {
      return filteredEmployeeOptions.map((employee) => employee.hr_id);
    }
    const options = audienceSettings?.[field] || [];
    const sanitized = options.filter((option) => Boolean(option?.trim?.() ?? option));
    return Array.from(new Set(sanitized)).sort((a, b) => a.localeCompare(b));
  };

  const getAudienceSearchValue = useCallback(
    (key) => String(audienceFilterSearch?.[key] || ''),
    [audienceFilterSearch]
  );

  const setAudienceSearchValue = useCallback((key, value) => {
    setAudienceFilterSearch((prev) => ({
      ...(prev || {}),
      [key]: value,
    }));
  }, []);

  const filterOptionsBySearch = useCallback((options, searchValue, getLabel) => {
    const normalizedSearch = String(searchValue || '').trim().toLowerCase();
    if (!normalizedSearch) return options;
    return (options || []).filter((option) =>
      String(getLabel(option) || '').toLowerCase().includes(normalizedSearch)
    );
  }, []);

  const buildSelectSearchHeader = useCallback(
    ({ fieldKey, shownValues = [], onSelectAllShown, onClearSelection }) => (
      <ListSubheader
        key={`${fieldKey}-search-header`}
        disableSticky
        sx={{ bgcolor: 'background.paper', py: 1, px: 1.5, borderBottom: '1px solid rgba(11,79,168,0.12)' }}
        onMouseDown={(e) => {
          e.preventDefault();
          e.stopPropagation();
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <TextField
          fullWidth
          size="small"
          placeholder={tr('Search in list', 'بحث في القائمة')}
          value={getAudienceSearchValue(fieldKey)}
          onChange={(e) => setAudienceSearchValue(fieldKey, e.target.value)}
          onKeyDown={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search fontSize="small" sx={{ color: 'text.secondary' }} />
              </InputAdornment>
            ),
          }}
        />
        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
          <Button
            size="small"
            variant="outlined"
            onMouseDown={(e) => {
              e.preventDefault();
              e.stopPropagation();
            }}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onSelectAllShown?.(shownValues);
            }}
            disabled={!shownValues.length}
          >
            {tr('Select all shown', 'تحديد كل الظاهر')}
          </Button>
          <Button
            size="small"
            color="inherit"
            onMouseDown={(e) => {
              e.preventDefault();
              e.stopPropagation();
            }}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setAudienceSearchValue(fieldKey, '');
              onClearSelection?.();
            }}
          >
            {tr('Clear selection', 'مسح الاختيار')}
          </Button>
        </Stack>
      </ListSubheader>
    ),
    [getAudienceSearchValue, setAudienceSearchValue, tr]
  );

  const handleRegionSelect = (values) => {
    const regionsList = values || [];
    const allowedAreas = getAreasForRegions(regionsList);
    const allowedAreaNames = new Set(allowedAreas.map((area) => area.area));
    updateAudience((prev) => {
      const syncedAreas = prev.filters.areas.filter((area) => allowedAreaNames.has(area));
      const allowedBranches = getBranchesForSelection(regionsList, syncedAreas);
      const allowedBranchCodes = new Set(allowedBranches.map((branch) => branch.branch_code));
      return {
        ...prev,
        mode: regionsList.length ? 'filters' : prev.mode,
        filters: {
          ...prev.filters,
          regions: regionsList,
          areas: syncedAreas,
          branch_codes: prev.filters.branch_codes.filter((code) => allowedBranchCodes.has(code)),
          branches: prev.filters.branches.filter((name) =>
            allowedBranches.some((branch) => branch.branch_name === name)
          ),
        },
      };
    });
  };

  const handleAreaSelect = (values) => {
    const areasList = values || [];
    const allowedBranches = getBranchesForSelection(audience.filters.regions, areasList);
    const allowedBranchCodes = new Set(allowedBranches.map((branch) => branch.branch_code));
    updateAudience((prev) => ({
      ...prev,
      mode: areasList.length ? 'filters' : prev.mode,
      filters: {
        ...prev.filters,
        areas: areasList,
        branch_codes: prev.filters.branch_codes.filter((code) => allowedBranchCodes.has(code)),
        branches: prev.filters.branches.filter((name) =>
          allowedBranches.some((branch) => branch.branch_name === name)
        ),
      },
    }));
  };

  const handleBranchSelect = (branchCodes) => {
    const codesList = branchCodes || [];
    const allowedBranches = getBranchesForSelection(audience.filters.regions, audience.filters.areas);
    const selectedBranches = allowedBranches.filter((branch) => codesList.includes(branch.branch_code));
    updateAudience((prev) => ({
      ...prev,
      mode: codesList.length ? 'filters' : prev.mode,
      filters: {
        ...prev.filters,
        branch_codes: codesList,
        branches: selectedBranches.map((branch) => branch.branch_name),
      },
    }));
  };

  const renderSelectedValues = (selected) => {
    if (!selected?.length) {
      return 'None';
    }
    if (selected.length <= 2) {
      return selected.join(', ');
    }
    return `${selected.slice(0, 2).join(', ')} (+${selected.length - 2} more)`;
  };

  const handleOpenAudienceDialog = () => setAudienceDialogOpen(true);
  const handleCloseAudienceDialog = () => setAudienceDialogOpen(false);

  const handleCopyAudienceHrIds = async () => {
    if (!audiencePreview.hr_ids.length || !navigator?.clipboard) {
      return;
    }
    try {
      await navigator.clipboard.writeText(audiencePreview.hr_ids.join('\n'));
      setAlert({ show: true, message: tr('Audience HR IDs copied to clipboard', 'تم نسخ أرقام الجمهور إلى الحافظة'), severity: 'success' });
    } catch (error) {
      console.error('Clipboard copy failed:', error);
      setAlert({ show: true, message: tr('Unable to copy HR IDs', 'تعذر نسخ الأرقام الوظيفية'), severity: 'error' });
    }
  };

  const handleDownloadAudienceExcel = async () => {
    if (!audiencePreview.employees.length) {
      return;
    }

    try {
      setAudienceExcelDownloading(true);
      const response = await userService.exportResolvedAudienceExcel(audience);
      const blob = new Blob([response.data], {
        type:
          response.headers?.['content-type'] ||
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      const downloadUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = downloadUrl;
      anchor.download = 'audience_preview.xlsx';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(downloadUrl);

      setAlert({
        show: true,
        message: tr('Audience Excel downloaded successfully', 'تم تنزيل ملف الجمهور بنجاح'),
        severity: 'success',
      });
    } catch (error) {
      console.error('Audience Excel download failed:', error);
      setAlert({
        show: true,
        message: tr('Unable to download audience Excel', 'تعذر تنزيل ملف الجمهور'),
        severity: 'error',
      });
    } finally {
      setAudienceExcelDownloading(false);
    }
  };

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const primaryGroupName = questionGroups[0] || DEFAULT_GROUP_NAME;

  const groupCounts = useMemo(() => {
    const counts = {};
    questionGroups.forEach((group) => {
      counts[group] = counts[group] || 0;
    });
    formData.questions.forEach((question) => {
      const groupName = (question.question_group || '').trim() || primaryGroupName;
      counts[groupName] = (counts[groupName] || 0) + 1;
    });
    return counts;
  }, [formData.questions, questionGroups, primaryGroupName]);

  useEffect(() => {
    if (activeGroupTab !== 'ALL' && !questionGroups.includes(activeGroupTab)) {
      setActiveGroupTab('ALL');
    }
  }, [activeGroupTab, questionGroups]);

  const handleGroupTabChange = (event, newGroup) => {
    setActiveGroupTab(newGroup);
  };

  const openGroupDialog = (mode) => {
    if (mode === 'rename' && (activeGroupTab === 'ALL' || !questionGroups.includes(activeGroupTab))) {
      return;
    }
    setGroupDialogState({
      open: true,
      mode,
      value: mode === 'rename' ? activeGroupTab : '',
      originalName: mode === 'rename' ? activeGroupTab : '',
    });
  };

  const handleGroupDialogClose = () => {
    setGroupDialogState({ open: false, mode: 'add', value: '', originalName: '' });
  };

  const handleGroupDialogSave = () => {
    const trimmedName = groupDialogState.value.trim();
    if (!trimmedName) {
      setAlert({ show: true, severity: 'error', message: tr('Group name cannot be empty', 'اسم المجموعة لا يمكن أن يكون فارغاً') });
      return;
    }
    const normalizedName = trimmedName;
    const duplicateExists = questionGroups.some(
      (group) => group.toLowerCase() === normalizedName.toLowerCase() && group !== groupDialogState.originalName
    );
    if (duplicateExists) {
      setAlert({ show: true, severity: 'error', message: tr('Group name must be unique', 'يجب أن يكون اسم المجموعة فريداً') });
      return;
    }

    if (groupDialogState.mode === 'add') {
      setQuestionGroups((prev) => [...prev, normalizedName]);
      setActiveGroupTab(normalizedName);
    } else if (groupDialogState.mode === 'rename') {
      const originalName = groupDialogState.originalName;
      setQuestionGroups((prev) => prev.map((group) => (group === originalName ? normalizedName : group)));
      setFormData((prev) => ({
        ...prev,
        questions: prev.questions.map((question) =>
          (question.question_group || '').trim() === originalName
            ? { ...question, question_group: normalizedName }
            : question
        ),
      }));
      if (activeGroupTab === originalName) {
        setActiveGroupTab(normalizedName);
      }
    }
    handleGroupDialogClose();
  };

  const handleDeleteGroup = (groupName) => {
    if (!groupName || groupName === 'ALL') {
      return;
    }
    if (questionGroups.length <= 1) {
      setAlert({ show: true, severity: 'warning', message: tr('At least one group is required', 'يجب وجود مجموعة واحدة على الأقل') });
      return;
    }
    if ((groupCounts[groupName] || 0) > 0) {
      setAlert({
        show: true,
        severity: 'warning',
        message: tr('Move questions to another group before deleting it', 'انقل الأسئلة إلى مجموعة أخرى قبل حذفها'),
      });
      return;
    }
    setQuestionGroups((prev) => prev.filter((group) => group !== groupName));
    if (activeGroupTab === groupName) {
      setActiveGroupTab('ALL');
    }
  };

  const handleQuestionGroupChange = (questionIndex, groupName) => {
    const sanitizedGroup = groupName?.trim() || primaryGroupName;
    setFormData((prev) => {
      const updatedQuestions = [...prev.questions];
      updatedQuestions[questionIndex] = {
        ...updatedQuestions[questionIndex],
        question_group: sanitizedGroup,
        bank_question_id: null,
        bank_is_favorite: false,
      };
      return { ...prev, questions: updatedQuestions };
    });
  };

  const resolveQuestionGroup = useCallback(
    (question) => (question.question_group || '').trim() || primaryGroupName,
    [primaryGroupName]
  );

  const questionEntries = useMemo(
    () => formData.questions.map((question, index) => ({ question, index })),
    [formData.questions]
  );

  const filteredQuestionEntries = useMemo(() => {
    if (activeGroupTab === 'ALL') {
      return questionEntries;
    }
    return questionEntries.filter(({ question }) => resolveQuestionGroup(question) === activeGroupTab);
  }, [activeGroupTab, questionEntries, resolveQuestionGroup]);

  const supportedQuestionBankItems = useMemo(
    () =>
      questionBankItems.filter((item) =>
        ['MCQ', 'TF'].includes(String(item.question_type || '').toUpperCase())
      ),
    [questionBankItems]
  );

  const availableGroupItems = useMemo(() => {
    const used = new Set(formData.questions.map((item) => item.bank_question_id).filter(Boolean));
    return questionBankGroups.map((group) => ({
      ...group,
      available: supportedQuestionBankItems.filter((item) => item.group_id === group.group_id && !used.has(item.bank_question_id)),
    }));
  }, [formData.questions, questionBankGroups, supportedQuestionBankItems]);
  const requestedGroupTotal = Object.values(bankGroupCounts).reduce((sum, value) => sum + (Number(value) || 0), 0);
  const groupCountError = availableGroupItems.find((group) => {
    const raw = bankGroupCounts[group.group_id] ?? 0;
    const count = Number(raw);
    return !Number.isInteger(count) || count < 0 || count > group.available.length;
  });

  const filteredQuestionBankItems = useMemo(() => {
    const normalizedQuery = questionBankQuery.trim().toLowerCase();
    return supportedQuestionBankItems.filter((item) => {
      const normalizedType = String(item.question_type || '').toUpperCase();
      if (questionBankTypeFilter !== 'ALL' && normalizedType !== questionBankTypeFilter) {
        return false;
      }
      if (questionBankFavoritesOnly && !item.is_favorite) {
        return false;
      }
      if (!normalizedQuery) {
        return true;
      }

      const searchableText = [
        item.question_text,
        item.question_group,
        normalizedType,
        ...(item.choices || []).map((choice) => choice.choice_text),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();

      return searchableText.includes(normalizedQuery);
    });
  }, [questionBankFavoritesOnly, questionBankItems, questionBankQuery, questionBankTypeFilter, supportedQuestionBankItems]);

  const visibleQuestionBankIds = useMemo(
    () => filteredQuestionBankItems.map((item) => item.bank_question_id),
    [filteredQuestionBankItems]
  );

  const allVisibleQuestionBankSelected =
    visibleQuestionBankIds.length > 0 &&
    visibleQuestionBankIds.every((id) => selectedBankQuestionIds.includes(id));

  const someVisibleQuestionBankSelected =
    visibleQuestionBankIds.some((id) => selectedBankQuestionIds.includes(id)) &&
    !allVisibleQuestionBankSelected;

  const buildQuestionPayload = useCallback(
    (question, questionIndex = null) => {
      const questionLabel =
        typeof questionIndex === 'number'
          ? `${tr('Question', 'سؤال')} ${questionIndex + 1}`
          : tr('This question', 'هذا السؤال');
      const questionText = String(question.question_text || '').trim();
      if (!questionText) {
        return {
          error: `${questionLabel}: ${tr('Question text is required', 'نص السؤال مطلوب')}`,
        };
      }

      const normalizedType = String(question.question_type || 'MCQ').toUpperCase();
      const payload = {
        question_text: questionText,
        question_type: normalizedType,
        points: Math.max(1, Number.parseInt(question.points, 10) || 1),
        question_group: resolveQuestionGroup(question),
        choices: [],
      };

      if (normalizedType === 'MCQ' || normalizedType === 'TF') {
        const choices = (question.choices || []).map((choice) => ({
          choice_text: String(choice.choice_text || '').trim(),
          is_correct: Boolean(choice.is_correct),
        }));

        if (choices.length < 2) {
          return {
            error: `${questionLabel}: ${tr('Please keep at least two choices', 'يرجى الإبقاء على اختيارين على الأقل')}`,
          };
        }
        if (choices.some((choice) => !choice.choice_text)) {
          return {
            error: `${questionLabel}: ${tr('Every choice needs text', 'كل اختيار يحتاج إلى نص')}`,
          };
        }
        if (!choices.some((choice) => choice.is_correct)) {
          return {
            error: `${questionLabel}: ${tr('Mark at least one correct answer', 'حدد إجابة صحيحة واحدة على الأقل')}`,
          };
        }

        payload.choices = choices;
      }

      return { payload };
    },
    [resolveQuestionGroup, tr]
  );

  const mergeQuestionBankItem = useCallback((item) => {
    setQuestionBankItems((prev) => {
      const existingIndex = prev.findIndex(
        (entry) => entry.bank_question_id === item.bank_question_id
      );
      if (existingIndex === -1) {
        return [item, ...prev];
      }
      const nextItems = [...prev];
      nextItems[existingIndex] = item;
      return nextItems;
    });
  }, []);

  const syncDraftQuestionBankFavoriteState = useCallback((bankQuestionId, isFavorite) => {
    setFormData((prev) => ({
      ...prev,
      questions: prev.questions.map((question) =>
        question.bank_question_id === bankQuestionId
          ? { ...question, bank_is_favorite: isFavorite }
          : question
      ),
    }));
  }, []);

  const loadQuestionBank = useCallback(async () => {
    setQuestionBankLoading(true);
    try {
      const [response, groupsResponse] = await Promise.all([examService.getQuestionBank(), examService.getQuestionBankGroups()]);
      setQuestionBankItems(response.data?.items || []);
      setQuestionBankGroups(groupsResponse.data?.groups || []);
    } catch (error) {
      setAlert({
        show: true,
        message: getApiErrorMessage(
          error,
          tr('Unable to load the question bank', 'تعذر تحميل بنك الأسئلة')
        ),
        severity: 'error',
      });
    } finally {
      setQuestionBankLoading(false);
    }
  }, [tr]);

  const handleOpenQuestionBankDialog = useCallback(async () => {
    setSelectedBankQuestionIds([]);
    setBankGroupCounts({});
    setGroupQuery('');
    setQuestionBankDialogOpen(true);
    await loadQuestionBank();
  }, [loadQuestionBank]);

  const handleCloseQuestionBankDialog = useCallback(() => {
    setQuestionBankDialogOpen(false);
    setSelectedBankQuestionIds([]);
  }, []);

  const toggleQuestionBankSelection = useCallback((bankQuestionId) => {
    setSelectedBankQuestionIds((prev) =>
      prev.includes(bankQuestionId)
        ? prev.filter((id) => id !== bankQuestionId)
        : [...prev, bankQuestionId]
    );
  }, []);

  const handleToggleAllVisibleQuestionBankItems = useCallback(
    (checked) => {
      setSelectedBankQuestionIds((prev) => {
        if (checked) {
          return Array.from(new Set([...prev, ...visibleQuestionBankIds]));
        }
        return prev.filter((id) => !visibleQuestionBankIds.includes(id));
      });
    },
    [visibleQuestionBankIds]
  );

  const cloneBankQuestionToDraft = useCallback(
    (item) => {
      const resolvedGroup =
        activeGroupTab !== 'ALL' && questionGroups.includes(activeGroupTab)
          ? activeGroupTab
          : String(item.question_group || '').trim() || primaryGroupName;

      return {
        question_text: item.question_text || '',
        question_type: item.question_type || 'MCQ',
        points: item.points || 1,
        question_group: resolvedGroup,
        bank_question_id: item.bank_question_id,
        bank_is_favorite: Boolean(item.is_favorite),
        choices: (item.choices || [])
          .slice()
          .sort((left, right) => (left.choice_order || 0) - (right.choice_order || 0))
          .map((choice) => ({
            choice_text: choice.choice_text || '',
            is_correct: Boolean(choice.is_correct),
          })),
      };
    },
    [activeGroupTab, primaryGroupName, questionGroups]
  );

  const handleAddQuestionBankItems = useCallback(
    (items) => {
      const usedIds = new Set(formData.questions.map((question) => question.bank_question_id).filter(Boolean));
      const uniqueItems = items.filter((item) => {
        if (usedIds.has(item.bank_question_id)) return false;
        usedIds.add(item.bank_question_id);
        return true;
      });
      if (!uniqueItems.length) {
        return;
      }

      const draftQuestions = uniqueItems.map(cloneBankQuestionToDraft);
      const nextGroups = [...questionGroups];
      draftQuestions.forEach((question) => {
        const groupName = String(question.question_group || '').trim();
        if (
          groupName &&
          !nextGroups.some((existingGroup) => existingGroup.toLowerCase() === groupName.toLowerCase())
        ) {
          nextGroups.push(groupName);
        }
      });

      setQuestionGroups(nextGroups);
      setFormData((prev) => ({
        ...prev,
        questions: [...prev.questions, ...draftQuestions],
      }));
      setSelectedBankQuestionIds([]);
      setQuestionBankDialogOpen(false);
      setAlert({
        show: true,
        severity: 'success',
        message: tr(
          `${draftQuestions.length} question(s) added from the question bank`,
          `تمت إضافة ${draftQuestions.length} سؤال/أسئلة من بنك الأسئلة`
        ),
      });
    },
    [cloneBankQuestionToDraft, formData.questions, questionGroups, tr]
  );

  const handleAddGroupQuestions = async () => {
    if (requestedGroupTotal < 1 || groupCountError) return;
    setQuestionBankLoading(true);
    try {
      const response = await examService.selectQuestionBankGroups({
        groups: availableGroupItems.map((group) => ({ group_id: group.group_id, count: Number(bankGroupCounts[group.group_id] || 0) })),
        excluded_question_ids: formData.questions.map((item) => item.bank_question_id).filter(Boolean),
      });
      if (response.data.items.length !== requestedGroupTotal) throw new Error('Question selection count did not match the request.');
      handleAddQuestionBankItems(response.data.items);
    } catch (error) {
      setAlert({ show: true, severity: 'error', message: getApiErrorMessage(error, tr('Unable to add questions from groups.', 'تعذر إضافة الأسئلة من المجموعات.')) });
    } finally { setQuestionBankLoading(false); }
  };

  const handleToggleQuestionBankFavorite = useCallback(
    async (item) => {
      setQuestionBankFavoriteId(item.bank_question_id);
      try {
        const response = await examService.updateQuestionBankItem(item.bank_question_id, {
          question_text: item.question_text,
          question_type: item.question_type,
          points: item.points || 1,
          question_group: item.question_group || null,
          choices: (item.choices || []).map((choice) => ({
            choice_text: choice.choice_text,
            is_correct: Boolean(choice.is_correct),
          })),
          is_favorite: !item.is_favorite,
        });
        const updatedItem = response.data?.item;
        if (updatedItem) {
          mergeQuestionBankItem(updatedItem);
          syncDraftQuestionBankFavoriteState(
            updatedItem.bank_question_id,
            Boolean(updatedItem.is_favorite)
          );
        }
      } catch (error) {
        setAlert({
          show: true,
          severity: 'error',
          message: getApiErrorMessage(
            error,
            tr('Unable to update favorite status', 'تعذر تحديث حالة المفضلة')
          ),
        });
      } finally {
        setQuestionBankFavoriteId(null);
      }
    },
    [mergeQuestionBankItem, syncDraftQuestionBankFavoriteState, tr]
  );

  const handleSaveQuestionToBank = useCallback(
    async (questionIndex) => {
      const targetQuestion = formData.questions[questionIndex];
      if (!targetQuestion) {
        return;
      }

      const { payload, error } = buildQuestionPayload(targetQuestion, questionIndex);
      if (error) {
        setAlert({ show: true, severity: 'error', message: error });
        return;
      }

      setQuestionBankSavingIndex(questionIndex);
      try {
        const response = await examService.createQuestionBankItem({
          ...payload,
          is_favorite: Boolean(targetQuestion.bank_is_favorite),
        });
        const savedItem = response.data?.item;
        const created = response.data?.created !== false;
        if (savedItem) {
          mergeQuestionBankItem(savedItem);
          setFormData((prev) => ({
            ...prev,
            questions: prev.questions.map((question, index) =>
              index === questionIndex
                ? {
                    ...question,
                    bank_question_id: savedItem.bank_question_id,
                    bank_is_favorite: Boolean(savedItem.is_favorite),
                  }
                : question
            ),
          }));
        }
        setAlert({
          show: true,
          severity: 'success',
          message: created
            ? tr(
                'Question saved to the question bank',
                'تم حفظ السؤال في بنك الأسئلة'
              )
            : tr(
                'Question already existed in the bank, so this draft is now linked to it',
                'كان السؤال موجوداً بالفعل في بنك الأسئلة، وتم ربط هذه النسخة به'
              ),
        });
      } catch (error) {
        setAlert({
          show: true,
          severity: 'error',
          message: getApiErrorMessage(
            error,
            tr('Unable to save question to bank', 'تعذر حفظ السؤال في بنك الأسئلة')
          ),
        });
      } finally {
        setQuestionBankSavingIndex(null);
      }
    },
    [buildQuestionPayload, formData.questions, mergeQuestionBankItem, tr]
  );

  const createEmptyQuestion = (groupName) => ({
    question_text: '',
    question_type: 'MCQ',
    points: 1,
    question_group: groupName || (activeGroupTab !== 'ALL' && questionGroups.includes(activeGroupTab)
      ? activeGroupTab
      : primaryGroupName),
    bank_question_id: null,
    bank_is_favorite: false,
    choices: [
      { choice_text: '', is_correct: false },
      { choice_text: '', is_correct: false },
    ],
  });

  const handleAddQuestion = (insertIndex = formData.questions.length, groupName = null) => {
    const newQuestions = [...formData.questions];
    const targetGroup =
      groupName ||
      (activeGroupTab !== 'ALL' && questionGroups.includes(activeGroupTab)
        ? activeGroupTab
        : primaryGroupName);
    newQuestions.splice(insertIndex, 0, createEmptyQuestion(targetGroup));
    setFormData({ ...formData, questions: newQuestions });
  };

  const handleRemoveQuestion = (index) => {
    const newQuestions = formData.questions.filter((_, i) => i !== index);
    setFormData({ ...formData, questions: newQuestions });
  };

  const handleQuestionChange = (index, field, value) => {
    const newQuestions = [...formData.questions];
    newQuestions[index] = {
      ...newQuestions[index],
      [field]: value,
      bank_question_id: null,
      bank_is_favorite: false,
    };

    if (field === 'question_type') {
      if (value === 'TF') {
        newQuestions[index].choices = [
          { choice_text: 'True', is_correct: false },
          { choice_text: 'False', is_correct: false },
        ];
      } else if (value === 'Essay') {
        newQuestions[index].choices = [];
      } else {
        newQuestions[index].choices = [
          { choice_text: '', is_correct: false },
          { choice_text: '', is_correct: false },
        ];
      }
    }

    setFormData({ ...formData, questions: newQuestions });
  };

  const handleAddChoice = (questionIndex) => {
    const newQuestions = [...formData.questions];
    newQuestions[questionIndex] = {
      ...newQuestions[questionIndex],
      bank_question_id: null,
      bank_is_favorite: false,
    };
    newQuestions[questionIndex].choices.push({
      choice_text: '',
      is_correct: false,
    });
    setFormData({ ...formData, questions: newQuestions });
  };

  const handleRemoveChoice = (questionIndex, choiceIndex) => {
    const newQuestions = [...formData.questions];
    newQuestions[questionIndex] = {
      ...newQuestions[questionIndex],
      bank_question_id: null,
      bank_is_favorite: false,
    };
    newQuestions[questionIndex].choices = newQuestions[questionIndex].choices.filter(
      (_, i) => i !== choiceIndex
    );
    setFormData({ ...formData, questions: newQuestions });
  };

  const handleChoiceChange = (questionIndex, choiceIndex, field, value) => {
    const newQuestions = [...formData.questions];
    newQuestions[questionIndex] = {
      ...newQuestions[questionIndex],
      bank_question_id: null,
      bank_is_favorite: false,
    };
    newQuestions[questionIndex].choices[choiceIndex][field] = value;

    if (field === 'is_correct' && value) {
      const qType = newQuestions[questionIndex].question_type;
      if (qType === 'TF') {
        newQuestions[questionIndex].choices.forEach((choice, i) => {
          if (i !== choiceIndex) choice.is_correct = false;
        });
      }
    }

    setFormData({ ...formData, questions: newQuestions });
  };

  const handleSubmit = async () => {
    if (!formData.title || !formData.description) {
      setAlert({ show: true, message: 'Please fill in all required fields', severity: 'error' });
      return;
    }

    if (!formData.start_date || !formData.start_time || !formData.end_date || !formData.end_time) {
      setAlert({
        show: true,
        message: tr('Please select both date and time for the exam window.', 'يرجى اختيار التاريخ والوقت لنافذة الاختبار.'),
        severity: 'error',
      });
      return;
    }

    const startDateValue = buildDateTimeObject(formData.start_date, formData.start_time);
    const endDateValue = buildDateTimeObject(formData.end_date, formData.end_time);
    if (!startDateValue || !endDateValue) {
      setAlert({
        show: true,
        message: tr('Please select valid start and end date/time values', 'يرجى اختيار قيم صحيحة لتاريخ/وقت البداية والنهاية'),
        severity: 'error',
      });
      return;
    }

    if (startDateValue >= endDateValue) {
      setAlert({
        show: true,
        message: tr('End date/time must be after the start date/time', 'يجب أن يكون تاريخ/وقت النهاية بعد تاريخ/وقت البداية'),
        severity: 'error',
      });
      return;
    }

    if (formData.questions.length === 0) {
      setAlert({ show: true, message: tr('Please add at least one question', 'يرجى إضافة سؤال واحد على الأقل'), severity: 'error' });
      return;
    }

    const preparedQuestions = [];
    for (let index = 0; index < formData.questions.length; index += 1) {
      const { payload: preparedQuestion, error } = buildQuestionPayload(formData.questions[index], index);
      if (error) {
        setActiveTab(1);
        setAlert({ show: true, message: error, severity: 'error' });
        return;
      }
      preparedQuestions.push(preparedQuestion);
    }

    const startDatePayload = formatDateTimeForPayload(formData.start_date, formData.start_time);
    const endDatePayload = formatDateTimeForPayload(formData.end_date, formData.end_time);
    const { start_time, end_time, ...restFormData } = formData;

    const payload = {
      ...restFormData,
      questions: preparedQuestions,
      start_date: startDatePayload,
      end_date: endDatePayload,
      audience,
      ...(editMode ? { audience_update_mode: audienceUpdateMode } : {}),
    };

    setLoading(true);
    try {
      if (editMode && examId) {
        await examService.updateExam(examId, payload);
        setAlert({
          show: true,
          message: tr(
            'Exam updated successfully. Use Send Mail from Exam Management to notify the audience.',
            'تم تحديث الاختبار بنجاح. استخدم زر إرسال بريد من إدارة الاختبارات لإخطار الجمهور.'
          ),
          severity: 'success',
        });
      } else {
        await examService.createExam(payload);
        setAlert({
          show: true,
          message: tr(
            'Exam created successfully. Use Send Mail from Exam Management to notify the audience.',
            'تم إنشاء الاختبار بنجاح. استخدم زر إرسال بريد من إدارة الاختبارات لإخطار الجمهور.'
          ),
          severity: 'success',
        });
      }
      setTimeout(() => navigate('/hr/exams'), 1500);
    } catch (error) {
      setAlert({
        show: true,
        message: getApiErrorMessage(
          error,
          editMode
            ? tr('Failed to update exam', 'فشل تحديث الاختبار')
            : tr('Failed to create exam', 'فشل إنشاء الاختبار')
        ),
        severity: 'error',
      });
    } finally {
      setLoading(false);
    }
  };

  const cascadeSelectedFilters = [
    { label: tr('Regions', 'الأقاليم'), values: audience.filters.regions || [] },
    { label: tr('Areas', 'المناطق'), values: audience.filters.areas || [] },
    { label: tr('Branches', 'الفروع'), values: audience.filters.branches || [] },
  ];
  const selectedFilters = [
    ...cascadeSelectedFilters,
    ...localizedAudienceFilterFields.map((field) => ({
      label: field.label,
      values: audience.filters[field.key] || [],
    })),
  ].filter((item) => item.values.length > 0);

  return (
    <Box sx={{ direction: isArabic ? 'rtl' : 'ltr' }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <IconButton onClick={() => navigate('/hr/exams')} sx={{ mr: isArabic ? 0 : 2, ml: isArabic ? 2 : 0 }}>
          <ArrowBack />
        </IconButton>
        <Typography variant="h4" fontWeight="bold">
          {editMode ? tr('Edit Exam', 'تعديل الاختبار') : tr('Create New Exam', 'إنشاء اختبار جديد')}
        </Typography>
        <Box sx={{ ml: isArabic ? 0 : 'auto', mr: isArabic ? 'auto' : 0 }}>
          <Button
            variant="contained"
            startIcon={<Save />}
            onClick={handleSubmit}
            disabled={loading}
            size="large"
          >
            {loading ? tr('Saving...', 'جارٍ الحفظ...') : editMode ? tr('Update Exam', 'تحديث الاختبار') : tr('Save Exam', 'حفظ الاختبار')}
          </Button>
        </Box>
      </Box>

      {alert.show && (
        <Alert severity={alert.severity} sx={{ mb: 2 }} onClose={() => setAlert({ ...alert, show: false })}>
          {alert.message}
        </Alert>
      )}

      {/* Main Card with Tabs */}
      <Card elevation={3}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider', bgcolor: 'grey.50' }}>
          <Tabs
            value={activeTab}
            onChange={handleTabChange}
            sx={{
              px: 3,
              '& .MuiTab-root': {
                fontSize: '1rem',
                fontWeight: 600,
                textTransform: 'none',
                minHeight: 64,
                px: 4,
              },
            }}
            TabIndicatorProps={{
              style: { height: 3 }
            }}
          >
            <Tab label={tr('Exam Information', 'معلومات الاختبار')} />
            <Tab label={tr('Questions', 'الأسئلة')} />
            <Tab label={tr('Audience', 'الجمهور')} />
          </Tabs>
        </Box>

        <Box sx={{ p: 4, minHeight: 500 }}>
          {/* Tab 1: Exam Information */}
          {activeTab === 0 && (
            <Box>
              <Typography variant="h5" fontWeight="bold" sx={{ mb: 4 }}>
                {tr('Basic Information', 'المعلومات الأساسية')}
              </Typography>

              <Stack spacing={3}>
                {/* ROW 1: Title, Status, and Level */}
                <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                  <TextField
                    sx={{ flex: 2, minWidth: 280 }}
                    label={tr('Exam Title', 'عنوان الاختبار')}
                    required
                    placeholder={tr('e.g., Data Analysis Final Exam', 'مثال: اختبار تحليل البيانات النهائي')}
                    value={formData.title}
                    onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  />
                  <TextField
                    sx={{ flex: 1, minWidth: 180 }}
                    select
                    label={tr('Status', 'الحالة')}
                    value={formData.exam_status}
                    onChange={(e) => setFormData({ ...formData, exam_status: e.target.value })}
                  >
                    <MenuItem value="Open">{tr('Open', 'مفتوح')}</MenuItem>
                    <MenuItem value="Closed">{tr('Closed', 'مغلق')}</MenuItem>
                    <MenuItem value="On Hold">{tr('On Hold', 'معلق')}</MenuItem>
                  </TextField>
                  <TextField
                    sx={{ flex: 1, minWidth: 220 }}
                    select
                    label={tr('Level', 'المستوى')}
                    value={formData.exam_level}
                    onChange={(e) => setFormData({ ...formData, exam_level: e.target.value })}
                  >
                    {EXAM_LEVEL_OPTIONS.map((level) => (
                      <MenuItem key={level} value={level}>
                        {levelLabel(level)}
                      </MenuItem>
                    ))}
                  </TextField>
                </Box>

                {/* ROW 2: Description */}
                <TextField
                  fullWidth
                  multiline
                  rows={4}
                  label={tr('Description', 'الوصف')}
                  required
                  placeholder={tr('Enter detailed exam description...', 'أدخل وصفاً تفصيلياً للاختبار...')}
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                />

                {/* ROW 3: Duration, Start Date/Time, End Date/Time */}
                <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                    <TextField
                      sx={{ flex: 1 }}
                      type="number"
                      label={tr('Duration (minutes)', 'المدة (بالدقائق)')}
                      required
                      value={formData.duration_minutes}
                      onChange={(e) => setFormData({ ...formData, duration_minutes: parseInt(e.target.value) })}
                      inputProps={{ min: 5 }}
                    />
                    <TextField
                      sx={{ flex: 1 }}
                      type="number"
                      label={tr('Passing Percent', 'نسبة النجاح')}
                      required
                      value={formData.passing_percent}
                      onChange={(e) => setFormData({ ...formData, passing_percent: parseFloat(e.target.value) })}
                      inputProps={{ min: 0, max: 100, step: 1 }}
                    />
                    <TextField
                      sx={{ flex: 1 }}
                      type="number"
                      label={tr('Attempts Allowed', 'عدد المحاولات المسموح')}
                      required
                      value={formData.number_of_attempts_allowed}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          number_of_attempts_allowed: parseInt(e.target.value),
                        })
                      }
                      inputProps={{ min: 1 }}
                    />
                    <TextField
                    sx={{ flex: 1 }}
                    type="date"
                    label={tr('Start Date', 'تاريخ البداية')}
                    required
                    InputLabelProps={{ shrink: true }}
                    value={formData.start_date}
                    onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                  />
                  <TextField
                    sx={{ flex: 1 }}
                    type="time"
                    label={tr('Start Time', 'وقت البداية')}
                    required
                    InputLabelProps={{ shrink: true }}
                    value={formData.start_time}
                    onChange={(e) => setFormData({ ...formData, start_time: e.target.value })}
                    inputProps={{ step: 60 }}
                  />
                  <TextField
                    sx={{ flex: 1 }}
                    type="date"
                    label={tr('End Date', 'تاريخ النهاية')}
                    required
                    InputLabelProps={{ shrink: true }}
                    value={formData.end_date}
                    onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                  />
                  <TextField
                    sx={{ flex: 1 }}
                    type="time"
                    label={tr('End Time', 'وقت النهاية')}
                    required
                    InputLabelProps={{ shrink: true }}
                    value={formData.end_time}
                    onChange={(e) => setFormData({ ...formData, end_time: e.target.value })}
                    inputProps={{ step: 60 }}
                  />
                </Box>
              </Stack>
            </Box>
          )}

          {/* Tab 2: Questions */}
          {activeTab === 1 && (
            <Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2, mb: 3 }}>
                <Box>
                  <Typography variant="h5" fontWeight="bold">
                    {tr('Exam Questions', 'أسئلة الاختبار')}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
                    {tr(
                      'Build questions once, save the strong ones to your question bank, then reuse them in future exams.',
                      'أنشئ الأسئلة مرة واحدة، واحفظ الجيد منها في بنك الأسئلة، ثم أعد استخدامها في الاختبارات القادمة.'
                    )}
                  </Typography>
                </Box>
                <Stack direction="row" spacing={1.25} flexWrap="wrap">
                  <Button variant="outlined" startIcon={<LibraryAdd />} onClick={handleOpenQuestionBankDialog}>
                    {tr('Add From Question Bank', 'إضافة من بنك الأسئلة')}
                  </Button>
                  <Button variant="contained" startIcon={<Add />} onClick={() => handleAddQuestion()}>
                    {activeGroupTab !== 'ALL'
                      ? `${tr('Add Question to', 'إضافة سؤال إلى')} ${activeGroupTab}`
                      : tr('Add Question', 'إضافة سؤال')}
                  </Button>
                </Stack>
              </Box>

              <Paper sx={{ p: 3, mb: 3, border: '1px solid', borderColor: 'grey.200' }}>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: 2,
                    mb: 2,
                  }}
                >
                  <Box>
                    <Typography variant="subtitle1" fontWeight="bold">
                      {tr('Question Groups', 'مجموعات الأسئلة')}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {tr('Organize questions into logical sections to guide employees through the exam.', 'نظّم الأسئلة في مجموعات منطقية لتوجيه الموظفين خلال الاختبار.')}
                    </Typography>
                  </Box>
                  <Stack direction="row" spacing={1}>
                    <Button variant="outlined" startIcon={<Add />} onClick={() => openGroupDialog('add')}>
                      {tr('New Group', 'مجموعة جديدة')}
                    </Button>
                    <Tooltip title={activeGroupTab === 'ALL' ? tr('Select a group tab first', 'اختر تبويب مجموعة أولاً') : tr('Rename this group', 'إعادة تسمية المجموعة')}>
                      <span>
                        <Button
                          variant="outlined"
                          startIcon={<DriveFileRenameOutline />}
                          disabled={activeGroupTab === 'ALL'}
                          onClick={() => openGroupDialog('rename')}
                        >
                          {tr('Rename', 'إعادة تسمية')}
                        </Button>
                      </span>
                    </Tooltip>
                    <Tooltip title={tr('Delete group (must be empty)', 'حذف المجموعة (يجب أن تكون فارغة)')}>
                      <span>
                        <Button
                          variant="outlined"
                          color="error"
                          disabled={activeGroupTab === 'ALL' || (groupCounts[activeGroupTab] ?? 0) > 0}
                          onClick={() => handleDeleteGroup(activeGroupTab)}
                        >
                          {tr('Remove', 'حذف')}
                        </Button>
                      </span>
                    </Tooltip>
                  </Stack>
                </Box>
                <Tabs
                  value={activeGroupTab}
                  onChange={handleGroupTabChange}
                  variant="scrollable"
                  scrollButtons="auto"
                >
                  <Tab value="ALL" label={`${tr('All Questions', 'كل الأسئلة')} (${formData.questions.length})`} />
                  {questionGroups.map((group) => (
                    <Tab key={group} value={group} label={`${group} (${groupCounts[group] || 0})`} />
                  ))}
                </Tabs>
                {activeGroupTab !== 'ALL' && (
                  <Alert severity="info" sx={{ mt: 2 }}>
                    {tr('New questions will be assigned to', 'سيتم إسناد الأسئلة الجديدة إلى')} <strong>{activeGroupTab}</strong>. {tr('You can change a question group anytime.', 'يمكنك تغيير مجموعة السؤال في أي وقت.')}
                  </Alert>
                )}
              </Paper>

              {filteredQuestionEntries.length === 0 ? (
                <Paper
                  sx={{
                    p: 8,
                    textAlign: 'center',
                    bgcolor: 'grey.50',
                    border: '2px dashed',
                    borderColor: 'grey.300',
                  }}
                >
                  <Typography variant="h6" color="text.secondary">
                    {formData.questions.length === 0
                      ? tr('No questions yet', 'لا توجد أسئلة بعد')
                      : `${tr('No questions in', 'لا توجد أسئلة في')} ${activeGroupTab}. ${tr('Add or move questions to populate this group.', 'أضف أسئلة أو انقلها لملء هذه المجموعة.')}`}
                  </Typography>
                  <Stack direction="row" spacing={1.25} justifyContent="center" sx={{ mt: 2 }} flexWrap="wrap">
                    <Button variant="outlined" startIcon={<LibraryAdd />} onClick={handleOpenQuestionBankDialog}>
                      {tr('Browse Question Bank', 'تصفح بنك الأسئلة')}
                    </Button>
                    <Button variant="contained" startIcon={<Add />} onClick={handleAddQuestion}>
                      {formData.questions.length === 0 ? tr('Add First Question', 'إضافة أول سؤال') : tr('Add Question', 'إضافة سؤال')}
                    </Button>
                  </Stack>
                </Paper>
              ) : (
                filteredQuestionEntries.map(({ question, index: questionIndex }, filteredIndex) => (
                  <React.Fragment key={`question-${questionIndex}`}>
                    {filteredIndex === 0 && (
                      <Button
                        variant="outlined"
                        startIcon={<Add />}
                        fullWidth
                        sx={{ mb: 2, borderStyle: 'dashed' }}
                        onClick={() =>
                          handleAddQuestion(
                            questionIndex,
                            activeGroupTab !== 'ALL' ? activeGroupTab : resolveQuestionGroup(question)
                          )
                        }
                      >
                        {tr('Add Question to Start', 'إضافة سؤال في البداية')}
                      </Button>
                    )}
                    <Paper sx={{ p: 3, mb: 2, border: '2px solid', borderColor: 'primary.light' }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Chip label={`${tr('Question', 'سؤال')} ${questionIndex + 1}`} color="primary" />
                          <Chip
                            icon={<LabelOutlined fontSize="small" />}
                            label={resolveQuestionGroup(question)}
                            variant="outlined"
                            color="warning"
                          />
                        </Stack>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Button
                            size="small"
                            variant={question.bank_question_id ? 'outlined' : 'text'}
                            startIcon={question.bank_question_id ? <Bookmark /> : <Save />}
                            disabled={
                              questionBankSavingIndex === questionIndex ||
                              (Boolean(question.bank_question_id) && questionBankSavingIndex === null)
                            }
                            onClick={() => handleSaveQuestionToBank(questionIndex)}
                          >
                            {questionBankSavingIndex === questionIndex
                              ? tr('Saving...', 'جارٍ الحفظ...')
                              : question.bank_question_id
                              ? tr('Saved in Bank', 'محفوظ في بنك الأسئلة')
                              : tr('Save to Bank', 'حفظ في بنك الأسئلة')}
                          </Button>
                          <IconButton color="error" onClick={() => handleRemoveQuestion(questionIndex)}>
                            <Delete />
                          </IconButton>
                        </Stack>
                      </Box>

                      <Stack spacing={3}>
                        <TextField
                          fullWidth
                          label={tr('Question Text', 'نص السؤال')}
                          required
                          multiline
                          rows={3}
                          value={question.question_text}
                          onChange={(e) => handleQuestionChange(questionIndex, 'question_text', e.target.value)}
                        />

                        <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                          <TextField
                            sx={{ flex: 1, minWidth: 200 }}
                            select
                            label={tr('Question Group', 'مجموعة السؤال')}
                            value={resolveQuestionGroup(question)}
                            onChange={(e) => handleQuestionGroupChange(questionIndex, e.target.value)}
                          >
                            {questionGroups.map((group) => (
                              <MenuItem key={`group-${group}`} value={group}>
                                {group}
                              </MenuItem>
                            ))}
                          </TextField>

                          <TextField
                            sx={{ flex: 1, minWidth: 200 }}
                            select
                            label={tr('Question Type', 'نوع السؤال')}
                            value={question.question_type}
                            onChange={(e) => handleQuestionChange(questionIndex, 'question_type', e.target.value)}
                          >
                            <MenuItem value="MCQ">{tr('Multiple Choice', 'اختيار من متعدد')}</MenuItem>
                            <MenuItem value="TF">{tr('True/False', 'صح/خطأ')}</MenuItem>
                          </TextField>

                          <TextField
                            sx={{ flex: 1, minWidth: 160 }}
                            type="number"
                            label={tr('Points', 'الدرجات')}
                            value={question.points}
                            onChange={(e) => handleQuestionChange(questionIndex, 'points', parseInt(e.target.value))}
                            inputProps={{ min: 1 }}
                          />
                        </Box>

                        {(question.question_type === 'MCQ' || question.question_type === 'TF') && (
                          <Box sx={{ p: 3, bgcolor: 'grey.50', borderRadius: 2 }}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                              <Typography variant="subtitle1" fontWeight="bold">
                                {tr('Answer Choices', 'الاختيارات')}
                              </Typography>
                              {question.question_type === 'MCQ' && (
                                <Button size="small" startIcon={<Add />} onClick={() => handleAddChoice(questionIndex)}>
                                  {tr('Add Choice', 'إضافة اختيار')}
                                </Button>
                              )}
                            </Box>

                            {question.choices.map((choice, cIndex) => (
                              <Box key={cIndex} sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                                <TextField
                                  fullWidth
                                  size="small"
                                  label={`${tr('Choice', 'اختيار')} ${String.fromCharCode(65 + cIndex)}`}
                                  value={choice.choice_text}
                                  onChange={(e) => handleChoiceChange(questionIndex, cIndex, 'choice_text', e.target.value)}
                                  disabled={question.question_type === 'TF'}
                                />
                                <FormControlLabel
                                  control={
                                    <Checkbox
                                      checked={choice.is_correct}
                                      onChange={(e) =>
                                        handleChoiceChange(questionIndex, cIndex, 'is_correct', e.target.checked)
                                      }
                                      color="success"
                                    />
                                  }
                                  label={tr('Correct', 'صحيح')}
                                />
                                {question.question_type === 'MCQ' && question.choices.length > 2 && (
                                  <IconButton
                                    size="small"
                                    color="error"
                                    onClick={() => handleRemoveChoice(questionIndex, cIndex)}
                                  >
                                    <Delete />
                                  </IconButton>
                                )}
                              </Box>
                            ))}
                          </Box>
                        )}
                      </Stack>
                    </Paper>
                    <Button
                      variant="outlined"
                      startIcon={<Add />}
                      fullWidth
                      sx={{ mb: 2, borderStyle: 'dashed' }}
                      onClick={() =>
                        handleAddQuestion(
                          questionIndex + 1,
                          activeGroupTab !== 'ALL' ? activeGroupTab : resolveQuestionGroup(question)
                        )
                      }
                    >
                      {tr('Add Question Here', 'إضافة سؤال هنا')}
                    </Button>
                  </React.Fragment>
                ))
              )}
            </Box>
          )}

          {/* Tab 3: Audience */}
          {activeTab === 2 && (
            <Stack spacing={4}>
              <Box>
                <Typography variant="h5" fontWeight="bold" sx={{ mb: 1 }}>
                  {tr('Audience Targeting', 'استهداف الجمهور')}
                </Typography>
                {/* <Typography variant="body2" color="text.secondary">
                  Decide who should take this exam. Preview updates instantly as you fine-tune your selection.
                </Typography> */}
              </Box>

              {editMode && (
                <Paper sx={{ p: 3 }}>
                  <Stack spacing={1.5}>
                    <Typography variant="subtitle1" fontWeight="bold">
                      {tr('Audience Update Mode', 'طريقة تحديث الجمهور')}
                    </Typography>
                    <ToggleButtonGroup
                      value={audienceUpdateMode}
                      exclusive
                      onChange={(_, value) => {
                        if (!value) return;
                        setAudienceUpdateMode(value);
                      }}
                      sx={{ alignSelf: 'flex-start' }}
                    >
                      <ToggleButton value="replace" sx={{ px: 2.5, py: 1.1, fontWeight: 800 }}>
                        {tr('Replace Audience', 'استبدال الجمهور')}
                      </ToggleButton>
                      <ToggleButton value="append" sx={{ px: 2.5, py: 1.1, fontWeight: 800 }}>
                        {tr('Add to Current Audience', 'إضافة إلى الجمهور الحالي')}
                      </ToggleButton>
                    </ToggleButtonGroup>
                    <Typography variant="body2" color="text.secondary">
                      {audienceUpdateMode === 'append'
                        ? tr('Selected employees will be added to the current exam audience.', 'سيتم إضافة الموظفين المختارين إلى جمهور الاختبار الحالي.')
                        : tr('Selected employees will replace the current exam audience.', 'سيتم استبدال جمهور الاختبار الحالي بالموظفين المختارين.')}
                    </Typography>
                  </Stack>
                </Paper>
              )}

              <Grid container spacing={3} justifyContent="center">
                {localizedAudienceModes.map((mode) => (
                  <Grid item xs={12} sm={4} md={3} key={mode.value} display="flex" justifyContent="center">
                    <Paper
                      onClick={() => handleAudienceModeChange(mode.value)}
                      elevation={audience.mode === mode.value ? 6 : 1}
                      sx={{
                        p: 3,
                        height: '100%',
                        border: '2px solid',
                        borderColor: audience.mode === mode.value ? 'warning.main' : 'transparent',
                        cursor: 'pointer',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 1,
                        transition: 'all 0.2s ease-in-out',
                      }}
                    >
                      <Typography variant="subtitle1" fontWeight="bold">
                        {mode.title}
                      </Typography>
                      {mode.description ? (
                        <Typography variant="body2" color="text.secondary">
                          {mode.description}
                        </Typography>
                      ) : null}
                    </Paper>
                  </Grid>
                ))}
              </Grid>

              <Grid container spacing={3} alignItems="stretch">
                <Grid item xs={12} md={7}>
                  {audience.mode === 'filters' && (
                    <Paper sx={{ p: 3, height: '100%' }}>
                      {!audienceSettings ? (
                        <Box sx={{ textAlign: 'center', py: 4 }}>
                          <CircularProgress size={32} />
                          <Typography variant="body2" sx={{ mt: 2 }}>
                            {tr('Loading audience settings...', 'جارٍ تحميل إعدادات الجمهور...')}
                          </Typography>
                        </Box>
                      ) : (
                        <Stack spacing={3}>
                          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <Box>
                              <Typography variant="subtitle1" fontWeight="bold">
                                {tr('Filter Employees', 'فلترة الموظفين')}
                              </Typography>
                              {/* <Typography variant="body2" color="text.secondary">
                                Choose one or multiple attributes. We resolve the exact HR IDs in real time.
                              </Typography> */}
                            </Box>
                            <Button size="small" onClick={handleClearFilters} disabled={!selectedFilters.length}>
                              {tr('Clear Filters', 'مسح الفلاتر')}
                            </Button>
                          </Box>
                          <Grid container spacing={2}>
                            {/* <Grid item xs={12}>
                              <Typography variant="subtitle2" color="text.secondary">
                                Narrow down by region → area → branch to follow the HR hierarchy.
                              </Typography>
                            </Grid> */}
                            <Grid item xs={12} md={4}>
                              <TextField
                                fullWidth
                                select
                                label={tr('Regions', 'الأقاليم')}
                                helperText={tr('Select one or more regions', 'اختر إقليماً واحداً أو أكثر')}
                                SelectProps={{
                                  multiple: true,
                                  value: audience.filters.regions,
                                  onClose: () => setAudienceSearchValue('regions', ''),
                                  MenuProps: {
                                    disableAutoFocusItem: true,
                                    PaperProps: { style: { maxHeight: 460 } },
                                  },
                                  onChange: (e) =>
                                    handleRegionSelect(
                                      Array.isArray(e.target.value) ? e.target.value : e.target.value.split(',')
                                    ),
                                  renderValue: (selected) =>
                                    renderSelectedValues(selected, tr('None', 'لا يوجد'), tr('more', 'أخرى')),
                                }}
                              >
                                {(() => {
                                  const shownRegions = filterOptionsBySearch(
                                    regionOptions,
                                    getAudienceSearchValue('regions'),
                                    (value) => value
                                  );
                                  return (
                                    <>
                                      {buildSelectSearchHeader({
                                        fieldKey: 'regions',
                                        shownValues: shownRegions,
                                        onSelectAllShown: (shown) =>
                                          handleRegionSelect([
                                            ...new Set([...(audience.filters.regions || []), ...(shown || [])]),
                                          ]),
                                        onClearSelection: () => handleRegionSelect([]),
                                      })}
                                      {shownRegions.map((region) => (
                                        <MenuItem
                                          key={`region-${region}`}
                                          value={region}
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            const isSelected = (audience.filters.regions || []).includes(region);
                                            handleRegionSelect(
                                              isSelected
                                                ? audience.filters.regions.filter((r) => r !== region)
                                                : [...audience.filters.regions, region]
                                            );
                                          }}
                                        >
                                          <Checkbox
                                            checked={(audience.filters.regions || []).includes(region)}
                                            size="small"
                                            onClick={(e) => e.stopPropagation()}
                                          />
                                          <ListItemText primary={region} />
                                        </MenuItem>
                                      ))}
                                    </>
                                  );
                                })()}
                              </TextField>
                            </Grid>
                            <Grid item xs={12} md={4}>
                              <TextField
                                fullWidth
                                select
                                label={tr('Areas', 'المناطق')}
                                helperText={tr('Areas auto-filter based on selected regions', 'يتم فلترة المناطق تلقائياً حسب الأقاليم المختارة')}
                                SelectProps={{
                                  multiple: true,
                                  value: audience.filters.areas,
                                  onClose: () => setAudienceSearchValue('areas', ''),
                                  MenuProps: {
                                    disableAutoFocusItem: true,
                                    PaperProps: { style: { maxHeight: 460 } },
                                  },
                                  onChange: (e) =>
                                    handleAreaSelect(
                                      Array.isArray(e.target.value) ? e.target.value : e.target.value.split(',')
                                    ),
                                  renderValue: (selected) =>
                                    renderSelectedValues(selected, tr('None', 'لا يوجد'), tr('more', 'أخرى')),
                                }}
                              >
                                {(() => {
                                  const shownAreas = filterOptionsBySearch(
                                    areaOptions,
                                    getAudienceSearchValue('areas'),
                                    (area) => `${area.area} ${area.region || ''}`
                                  );
                                  const shownAreaNames = shownAreas.map((area) => area.area);
                                  return (
                                    <>
                                      {buildSelectSearchHeader({
                                        fieldKey: 'areas',
                                        shownValues: shownAreaNames,
                                        onSelectAllShown: (shown) =>
                                          handleAreaSelect([
                                            ...new Set([...(audience.filters.areas || []), ...(shown || [])]),
                                          ]),
                                        onClearSelection: () => handleAreaSelect([]),
                                      })}
                                      {shownAreas.map((area) => (
                                        <MenuItem
                                          key={`area-${area.area}`}
                                          value={area.area}
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            const isSelected = (audience.filters.areas || []).includes(area.area);
                                            handleAreaSelect(
                                              isSelected
                                                ? audience.filters.areas.filter((a) => a !== area.area)
                                                : [...audience.filters.areas, area.area]
                                            );
                                          }}
                                        >
                                          <Checkbox
                                            checked={(audience.filters.areas || []).includes(area.area)}
                                            size="small"
                                            onClick={(e) => e.stopPropagation()}
                                          />
                                          <ListItemText
                                            primary={`${area.area}${area.region ? ` (${area.region})` : ''}`}
                                          />
                                        </MenuItem>
                                      ))}
                                    </>
                                  );
                                })()}
                              </TextField>
                            </Grid>
                            <Grid item xs={12} md={4}>
                              <TextField
                                fullWidth
                                select
                                label={tr('Branches', 'الفروع')}
                                helperText={tr('Branches respect region + area selections', 'الفروع تعتمد على اختيار الإقليم والمنطقة')}
                                SelectProps={{
                                  multiple: true,
                                  value: audience.filters.branch_codes,
                                  onClose: () => setAudienceSearchValue('branch_codes', ''),
                                  MenuProps: {
                                    disableAutoFocusItem: true,
                                    PaperProps: { style: { maxHeight: 460 } },
                                  },
                                  onChange: (e) =>
                                    handleBranchSelect(
                                      Array.isArray(e.target.value) ? e.target.value : e.target.value.split(',')
                                    ),
                                  renderValue: (selected) => {
                                    const labels = branchOptions
                                      .filter((branch) => selected.includes(branch.branch_code))
                                      .map((branch) => branch.branch_name);
                                    return renderSelectedValues(labels, tr('None', 'لا يوجد'), tr('more', 'أخرى'));
                                  },
                                }}
                              >
                                {(() => {
                                  const shownBranches = filterOptionsBySearch(
                                    branchOptions,
                                    getAudienceSearchValue('branch_codes'),
                                    (branch) =>
                                      `${branch.branch_name} ${branch.branch_code} ${branch.area || ''} ${branch.region || ''} ${branch.division || ''} ${branch.sub_department || ''}`
                                  );
                                  const shownBranchCodes = shownBranches.map((branch) => branch.branch_code);
                                  return (
                                    <>
                                      {buildSelectSearchHeader({
                                        fieldKey: 'branch_codes',
                                        shownValues: shownBranchCodes,
                                        onSelectAllShown: (shown) =>
                                          handleBranchSelect([
                                            ...new Set([...(audience.filters.branch_codes || []), ...(shown || [])]),
                                          ]),
                                        onClearSelection: () => handleBranchSelect([]),
                                      })}
                                      {shownBranches.map((branch) => (
                                  <MenuItem
                                    key={`branch-${branch.branch_code}`}
                                    value={branch.branch_code}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      const isSelected = (audience.filters.branch_codes || []).includes(branch.branch_code);
                                      handleBranchSelect(
                                        isSelected
                                          ? audience.filters.branch_codes.filter((code) => code !== branch.branch_code)
                                          : [...audience.filters.branch_codes, branch.branch_code]
                                      );
                                    }}
                                  >
                                    <Checkbox
                                      checked={(audience.filters.branch_codes || []).includes(branch.branch_code)}
                                      size="small"
                                      onClick={(e) => e.stopPropagation()}
                                    />
                                    <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                                      <Typography variant="body2" fontWeight="bold">
                                        {branch.branch_name} ({branch.branch_code})
                                      </Typography>
                                      <Typography variant="caption" color="text.secondary">
                                        {branch.area} · {branch.region} · {branch.division} / {branch.sub_department}
                                      </Typography>
                                    </Box>
                                  </MenuItem>
                                      ))}
                                    </>
                                  );
                                })()}
                              </TextField>
                            </Grid>
                            <Grid item xs={12}>
                              <Divider sx={{ my: 1 }} />
                            </Grid>
                            {localizedAudienceFilterFields.map((field) => (
                              <Grid item xs={12} sm={6} key={field.key}>
                                <TextField
                                  fullWidth
                                  select
                                  label={field.label}
                                  SelectProps={{
                                    multiple: true,
                                    value: audience.filters[field.key],
                                    onClose: () => setAudienceSearchValue(field.key, ''),
                                    MenuProps: {
                                      disableAutoFocusItem: true,
                                      PaperProps: { style: { maxHeight: 460 } },
                                    },
                                    onChange: (e) => handleFilterSelect(field.key, e.target.value),
                                    renderValue: (selected) =>
                                      renderSelectedValues(selected, tr('None', 'لا يوجد'), tr('more', 'أخرى')),
                                  }}
                                  helperText={`${tr('Select', 'اختر')} ${field.label} ${tr('to include', 'للإدراج')}`}
                                >
                                  {(() => {
                                    const options = availableOptions(field.key) || [];
                                    const shownOptions = filterOptionsBySearch(
                                      options,
                                      getAudienceSearchValue(field.key),
                                      (value) => value
                                    );
                                    return (
                                      <>
                                        {buildSelectSearchHeader({
                                          fieldKey: field.key,
                                          shownValues: shownOptions,
                                          onSelectAllShown: (shown) =>
                                            handleFilterSelect(field.key, [
                                              ...new Set([
                                                ...(audience.filters[field.key] || []),
                                                ...(shown || []),
                                              ]),
                                            ]),
                                          onClearSelection: () => handleFilterSelect(field.key, []),
                                        })}
                                        {shownOptions.map((option) => (
                                          <MenuItem
                                            key={`${field.key}-${option}`}
                                            value={option}
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              const isSelected = (audience.filters[field.key] || []).includes(option);
                                              handleFilterSelect(
                                                field.key,
                                                isSelected
                                                  ? audience.filters[field.key].filter((o) => o !== option)
                                                  : [...audience.filters[field.key], option]
                                              );
                                            }}
                                          >
                                            <Checkbox
                                              checked={(audience.filters[field.key] || []).includes(option)}
                                              size="small"
                                              onClick={(e) => e.stopPropagation()}
                                            />
                                            <ListItemText primary={option} />
                                          </MenuItem>
                                        ))}
                                      </>
                                    );
                                  })()}
                                </TextField>
                              </Grid>
                            ))}
                          </Grid>
                        </Stack>
                      )}
                    </Paper>
                  )}

                  {audience.mode === 'manual' && (
                    <Paper sx={{ p: 3, height: '100%' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                        <Typography variant="subtitle1" fontWeight="bold">
                          {tr('Bulk HR IDs / Branch Codes', 'رفع أرقام وظيفية / أكواد فروع')}
                        </Typography>
                        <Button size="small" variant="outlined" onClick={handleOpenBulkDialog}>
                          {tr('Bulk Upload', 'رفع جماعي')}
                        </Button>
                      </Box>
                      <Typography variant="body2" color="text.secondary">
                        {tr('Upload an Excel/CSV file that contains a single column named', 'ارفع ملف Excel/CSV يحتوي على عمود واحد باسم')}{' '}
                        <strong>hr_ids</strong> {tr('or', 'أو')} <strong>branch_codes</strong>.
                      </Typography>
                      {/* <Typography variant="subtitle2" sx={{ mt: 2 }}>
                        Loaded HR IDs: {audience.manual_hr_ids.length}
                      </Typography>
                      {audience.manual_hr_ids.length === 0 && (
                        <Typography variant="body2" color="text.secondary">
                          No HR IDs loaded yet. Use the bulk upload button above to import them.
                        </Typography>
                      )}  */}
                    </Paper>
                  )}

                  {/* {audience.mode === 'all' && (
                    <Paper sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                      <Typography variant="subtitle1" fontWeight="bold">
                        All Employees Selected
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                        Every active employee will be able to take this exam. Switch to “Filtered Audience” or “Manual HR IDs”
                        to narrow the scope.
                      </Typography>
                    </Paper>
                  )} */}
                </Grid>

                <Grid item xs={12} md={5}>
                  <Stack spacing={3} sx={{ height: '100%' }}>
                    <Paper sx={{ p: 3, flex: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <Typography variant="subtitle1" fontWeight="bold">
                        {tr('Audience Preview', 'معاينة الجمهور')}
                      </Typography>
                      <Divider />
                      {audiencePreview.loading ? (
                        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 4 }}>
                          <CircularProgress size={36} />
                        </Box>
                      ) : (
                        <>
                          <Typography variant="h3" fontWeight="bold">
                            {audiencePreview.count}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {tr('Employees will receive this exam', 'سيتم إرسال هذا الاختبار إلى الموظفين')}
                          </Typography>
                          <Stack direction="row" spacing={2} sx={{ mt: 2, flexWrap: 'wrap' }}>
                            <Button
                              variant="outlined"
                              onClick={handleOpenAudienceDialog}
                              disabled={!audiencePreview.employees.length}
                            >
                              {tr('View Audience', 'عرض الجمهور')}
                            </Button>
                            <Button
                              variant="contained"
                              onClick={handleCopyAudienceHrIds}
                              disabled={!audiencePreview.hr_ids.length}
                            >
                              {tr('Copy HR IDs', 'نسخ الأرقام الوظيفية')}
                            </Button>
                            <Button
                              variant="contained"
                              color="secondary"
                              startIcon={<Download />}
                              onClick={handleDownloadAudienceExcel}
                              disabled={!audiencePreview.employees.length || audienceExcelDownloading}
                            >
                              {audienceExcelDownloading
                                ? tr('Downloading...', 'جارٍ التنزيل...')
                                : tr('Download Excel', 'تنزيل Excel')}
                            </Button>
                          </Stack>
                        </>
                      )}
                    </Paper>
                  </Stack>
                </Grid>
              </Grid>
            </Stack>
          )}
        </Box>
      </Card>

      <Dialog open={questionBankDialogOpen} onClose={handleCloseQuestionBankDialog} maxWidth="lg" fullWidth>
        <DialogTitle>{tr('Add Questions from Question Bank', 'إضافة أسئلة من بنك الأسئلة')}</DialogTitle>
        <DialogContent dividers sx={{ minHeight: 420 }}>
          <Stack spacing={2.5}>
            <Box sx={{ p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
              <Typography fontWeight={800} sx={{ mb: 1 }}>{tr('Select questions by group', 'اختر الأسئلة حسب المجموعة')}</Typography>
              <TextField size="small" fullWidth label={tr('Search groups', 'البحث في المجموعات')} value={groupQuery} onChange={(event) => setGroupQuery(event.target.value)} sx={{ mb: 1 }} />
              {availableGroupItems.filter((group) => group.name.toLowerCase().includes(groupQuery.toLowerCase())).map((group) => <Stack key={group.group_id} direction={{ xs: 'column', sm: 'row' }} alignItems={{ sm: 'center' }} justifyContent="space-between" gap={1} sx={{ py: 0.75 }}>
                <Box><Typography fontWeight={700}>{group.name}</Typography><Typography variant="body2" color="text.secondary">{group.available.length} {tr('available', 'متاح')}</Typography></Box>
                <TextField size="small" type="number" label={tr('Questions to Add', 'عدد الأسئلة للإضافة')} value={bankGroupCounts[group.group_id] ?? 0} onChange={(event) => setBankGroupCounts((current) => ({ ...current, [group.group_id]: event.target.value }))} inputProps={{ min: 0, max: group.available.length, step: 1 }} error={Number(bankGroupCounts[group.group_id] || 0) > group.available.length} sx={{ width: { xs: '100%', sm: 175 } }} />
              </Stack>)}
              {!availableGroupItems.length && !questionBankLoading && <Typography color="text.secondary">{tr('No groups available.', 'لا توجد مجموعات متاحة.')}</Typography>}
              {groupCountError && <Alert severity="error" sx={{ mt: 1 }}>{`${groupCountError.name} contains only ${groupCountError.available.length} available questions.`}</Alert>}
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 1 }}><Typography fontWeight={700}>{tr('Total Questions to Add', 'إجمالي الأسئلة للإضافة')}: {requestedGroupTotal}</Typography><Button variant="contained" disabled={questionBankLoading || Boolean(groupCountError) || requestedGroupTotal < 1} onClick={handleAddGroupQuestions}>{tr('Add Questions', 'إضافة الأسئلة')}</Button></Stack>
            </Box>
            <Typography variant="body2" color="text.secondary">
              {activeGroupTab !== 'ALL'
                ? tr(
                    `Imported questions will be assigned to the "${activeGroupTab}" group.`,
                    `سيتم إسناد الأسئلة المستوردة إلى مجموعة "${activeGroupTab}".`
                  )
                : tr(
                    'Imported questions keep their saved group unless the group does not exist yet.',
                    'الأسئلة المستوردة تحتفظ بالمجموعة المحفوظة ما لم تكن المجموعة غير موجودة بعد.'
                  )}
            </Typography>

            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <TextField
                sx={{ flex: 2, minWidth: 260 }}
                label={tr('Search question bank', 'البحث في بنك الأسئلة')}
                value={questionBankQuery}
                onChange={(e) => setQuestionBankQuery(e.target.value)}
                placeholder={tr('Search by question, group, type, or choice text', 'ابحث بنص السؤال أو المجموعة أو النوع أو نص الاختيار')}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search fontSize="small" sx={{ color: 'text.secondary' }} />
                    </InputAdornment>
                  ),
                }}
              />
              <TextField
                sx={{ flex: 1, minWidth: 180 }}
                select
                label={tr('Question Type', 'نوع السؤال')}
                value={questionBankTypeFilter}
                onChange={(e) => setQuestionBankTypeFilter(e.target.value)}
              >
                <MenuItem value="ALL">{tr('All Types', 'كل الأنواع')}</MenuItem>
                <MenuItem value="MCQ">{tr('Multiple Choice', 'اختيار من متعدد')}</MenuItem>
                <MenuItem value="TF">{tr('True/False', 'صح/خطأ')}</MenuItem>
              </TextField>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={questionBankFavoritesOnly}
                    onChange={(e) => setQuestionBankFavoritesOnly(e.target.checked)}
                  />
                }
                label={tr('Favorites only', 'المفضلة فقط')}
                sx={{ mr: 0 }}
              />
            </Box>

            {questionBankLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 8 }}>
                <CircularProgress size={34} />
              </Box>
            ) : filteredQuestionBankItems.length === 0 ? (
              <Alert severity="info">
                {supportedQuestionBankItems.length === 0
                  ? tr(
                      'No saved questions yet. Create a question in this exam, then use "Save to Bank" to reuse it later.',
                      'لا توجد أسئلة محفوظة بعد. أنشئ سؤالاً في هذا الاختبار ثم استخدم "حفظ في بنك الأسئلة" لإعادة استخدامه لاحقاً.'
                    )
                  : tr(
                      'No questions match the current filters.',
                      'لا توجد أسئلة تطابق الفلاتر الحالية.'
                    )}
              </Alert>
            ) : (
              <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 460 }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={allVisibleQuestionBankSelected}
                          indeterminate={someVisibleQuestionBankSelected}
                          onChange={(e) =>
                            handleToggleAllVisibleQuestionBankItems(e.target.checked)
                          }
                        />
                      </TableCell>
                      <TableCell>{tr('Favorite', 'مفضلة')}</TableCell>
                      <TableCell>{tr('Question', 'السؤال')}</TableCell>
                      <TableCell>{tr('Group', 'المجموعة')}</TableCell>
                      <TableCell>{tr('Type', 'النوع')}</TableCell>
                      <TableCell>{tr('Points', 'الدرجات')}</TableCell>
                      <TableCell align="right">{tr('Action', 'إجراء')}</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {filteredQuestionBankItems.map((item) => {
                      const isSelected = selectedBankQuestionIds.includes(item.bank_question_id);
                      const choicesPreview = (item.choices || [])
                        .slice()
                        .sort((left, right) => (left.choice_order || 0) - (right.choice_order || 0))
                        .map((choice) =>
                          choice.is_correct ? `${choice.choice_text} (${tr('Correct', 'صحيح')})` : choice.choice_text
                        )
                        .join(' • ');

                      return (
                        <TableRow key={item.bank_question_id} hover selected={isSelected}>
                          <TableCell padding="checkbox">
                            <Checkbox
                              checked={isSelected}
                              onChange={() => toggleQuestionBankSelection(item.bank_question_id)}
                            />
                          </TableCell>
                          <TableCell>
                            <IconButton
                              size="small"
                              color={item.is_favorite ? 'warning' : 'default'}
                              disabled={questionBankFavoriteId === item.bank_question_id}
                              onClick={() => handleToggleQuestionBankFavorite(item)}
                            >
                              {item.is_favorite ? <Star fontSize="small" /> : <StarBorder fontSize="small" />}
                            </IconButton>
                          </TableCell>
                          <TableCell sx={{ minWidth: 340 }}>
                            <Typography variant="body2" fontWeight={700}>
                              {item.question_text}
                            </Typography>
                            {choicesPreview ? (
                              <Typography variant="caption" color="text.secondary">
                                {choicesPreview}
                              </Typography>
                            ) : null}
                          </TableCell>
                          <TableCell>
                            <Chip
                              size="small"
                              label={item.question_group || DEFAULT_GROUP_NAME}
                              variant="outlined"
                              color="warning"
                            />
                          </TableCell>
                          <TableCell>
                            <Chip
                              size="small"
                              label={
                                item.question_type === 'TF'
                                  ? tr('True/False', 'صح/خطأ')
                                  : tr('Multiple Choice', 'اختيار من متعدد')
                              }
                              color="primary"
                              variant="outlined"
                            />
                          </TableCell>
                          <TableCell>{item.points}</TableCell>
                          <TableCell align="right">
                            <Button
                              size="small"
                              variant="outlined"
                              startIcon={<Add />}
                              onClick={() => handleAddQuestionBankItems([item])}
                            >
                              {tr('Add', 'إضافة')}
                            </Button>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseQuestionBankDialog}>{tr('Close', 'إغلاق')}</Button>
          <Button
            variant="contained"
            startIcon={<LibraryAdd />}
            disabled={!selectedBankQuestionIds.length}
            onClick={() =>
              handleAddQuestionBankItems(
                supportedQuestionBankItems.filter((item) =>
                  selectedBankQuestionIds.includes(item.bank_question_id)
                )
              )
            }
          >
            {selectedBankQuestionIds.length > 0
              ? `${tr('Add Selected', 'إضافة المحدد')} (${selectedBankQuestionIds.length})`
              : tr('Add Selected', 'إضافة المحدد')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={groupDialogState.open} onClose={handleGroupDialogClose} maxWidth="xs" fullWidth>
        <DialogTitle>
          {groupDialogState.mode === 'add'
            ? tr('Add Question Group', 'إضافة مجموعة أسئلة')
            : `${tr('Rename', 'إعادة تسمية')} "${groupDialogState.originalName}"`}
        </DialogTitle>
        <DialogContent dividers>
          <TextField
            autoFocus
            margin="dense"
            label={tr('Group Name', 'اسم المجموعة')}
            fullWidth
            value={groupDialogState.value}
            onChange={(e) => setGroupDialogState((prev) => ({ ...prev, value: e.target.value }))}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleGroupDialogClose}>{tr('Cancel', 'إلغاء')}</Button>
          <Button onClick={handleGroupDialogSave} variant="contained">
            {groupDialogState.mode === 'add' ? tr('Add Group', 'إضافة مجموعة') : tr('Save Name', 'حفظ الاسم')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={bulkDialogOpen} onClose={() => setBulkDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{tr('Bulk Upload HR IDs', 'رفع جماعي للأرقام الوظيفية')}</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" sx={{ mb: 2 }}>
            {tr('Upload an Excel or CSV file that contains a single column named', 'ارفع ملف Excel أو CSV يحتوي على عمود واحد باسم')}{' '}
            <strong>hr_ids</strong> {tr('or', 'أو')} <strong>branch_codes</strong>.{' '}
            {tr('Branch uploads automatically expand to every employee assigned to those branches.', 'تحميل الفروع يوسّع القائمة تلقائياً إلى جميع الموظفين المخصصين لهذه الفروع.')}
          </Typography>
          {bulkUploadStatus.message ? (
            <Alert severity={bulkUploadStatus.severity} sx={{ mb: 2 }}>
              {bulkUploadStatus.message}
            </Alert>
          ) : null}
          <Button variant="contained" component="label" disabled={bulkUploading}>
            {bulkUploading ? tr('Processing...', 'جارٍ المعالجة...') : tr('Select File', 'اختيار ملف')}
            <input type="file" hidden accept=".xlsx,.xls,.csv" onChange={handleBulkFileInputChange} />
          </Button>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBulkDialogOpen(false)} disabled={bulkUploading}>
            {tr('Close', 'إغلاق')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={audienceDialogOpen} onClose={handleCloseAudienceDialog} maxWidth="md" fullWidth>
        <DialogTitle>{tr('Audience Details', 'تفاصيل الجمهور')} ({audiencePreview.count})</DialogTitle>
        <DialogContent dividers sx={{ maxHeight: 450 }}>
          {audiencePreview.employees.length === 0 ? (
            <Typography color="text.secondary">{tr('No audience details available for the current selection.', 'لا توجد تفاصيل جمهور متاحة للاختيار الحالي.')}</Typography>
          ) : (
            <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 360 }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell><strong>{tr('HR ID', 'الرقم الوظيفي')}</strong></TableCell>
                    <TableCell><strong>{tr('Name', 'الاسم')}</strong></TableCell>
                    <TableCell><strong>{tr('Email', 'البريد الإلكتروني')}</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {audiencePreview.employees.map((employee, index) => (
                    <TableRow key={`audience-preview-${employee.hr_id || index}`} hover>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{employee.hr_id || '-'}</TableCell>
                      <TableCell>{employee.name || '-'}</TableCell>
                      <TableCell>{employee.email || '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCopyAudienceHrIds} disabled={!audiencePreview.hr_ids.length}>
            {tr('Copy All', 'نسخ الكل')}
          </Button>
          <Button
            onClick={handleDownloadAudienceExcel}
            disabled={!audiencePreview.employees.length || audienceExcelDownloading}
            startIcon={<Download />}
          >
            {audienceExcelDownloading
              ? tr('Downloading...', 'جارٍ التنزيل...')
              : tr('Download Excel', 'تنزيل Excel')}
          </Button>
          <Button onClick={handleCloseAudienceDialog}>{tr('Close', 'إغلاق')}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default CreateExam;

