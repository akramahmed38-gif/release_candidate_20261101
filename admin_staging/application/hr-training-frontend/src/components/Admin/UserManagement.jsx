import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  MenuItem,
  Alert,
  Grid,
  CircularProgress,
  TableSortLabel,
  TablePagination,
  Checkbox,
  Popover,
  List,
  ListItemButton,
  ListItemText,
  Divider,
  Autocomplete,
} from '@mui/material';
import { Add, Edit, Delete, Visibility, UploadFile, DeleteSweep, Download } from '@mui/icons-material';
import { authService, userService } from '../../services/auth';
import { useLanguage } from '../../context/LanguageContext';

const initialFormData = {
  email: '',
  hr_id: '',
  name: '',
  title: '',
  branch_code: '',
  department: 'Retail',
};

const initialBranchFormData = {
  branch_code: '',
  branch_name: '',
  branch_region: '',
  branch_area: '',
  branch_division: '',
  branch_sub_department: '',
};

const textFieldConfig = [
  { name: 'email', type: 'email', required: true, fullWidth: true },
  { name: 'hr_id', required: true },
  { name: 'name', required: true },
  { name: 'title', required: true },
];

const titleOptions = [
  { value: 'Team Leader', label: 'Team Leader' },
  { value: 'indoor Sales Representative', label: 'indoor Sales Representative' },
  { value: 'Acting as Team Leader', label: 'Acting as Team Leader' },
];

const USER_FILTER_FIELDS = ['email', 'hr_id', 'name', 'branch', 'branch_code', 'role'];

const buildEmptyFilterState = () =>
  USER_FILTER_FIELDS.reduce((acc, key) => {
    acc[key] = [];
    return acc;
  }, {});

const buildEmptyFilterSearchState = () =>
  USER_FILTER_FIELDS.reduce((acc, key) => {
    acc[key] = '';
    return acc;
  }, {});

const normalizeRoleValue = (value) => (value || '').toString().trim().toLowerCase();
const sortTextOptions = (values) =>
  Array.from(
    new Set(
      (values || [])
        .map((value) => (value == null ? '' : value.toString().trim()))
        .filter(Boolean)
    )
  ).sort((left, right) => left.localeCompare(right, undefined, { sensitivity: 'base' }));

const USER_MANAGEMENT_AR = {
  Email: 'البريد الإلكتروني',
  'HR ID': 'الرقم الوظيفي',
  'Full Name': 'الاسم الكامل',
  Title: 'المسمى الوظيفي',
  Admin: 'أدمن',
  'HR (Instructor)': 'موارد بشرية (مدرب)',
  'Retail (Employee)': 'ريتيل (موظف)',
  Name: 'الاسم',
  Branch: 'الفرع',
  Area: 'المنطقة',
  Region: 'الإقليم',
  Division: 'القطاع',
  Department: 'الإدارة',
  'Sub Department': 'الإدارة الفرعية',
  Password: 'كلمة المرور',
  'Failed to load users': 'تعذر تحميل المستخدمين',
  'Unable to load branches. Upload branch data first.': 'تعذر تحميل الفروع. قم برفع بيانات الفروع أولاً.',
  'Users uploaded successfully!': 'تم رفع المستخدمين بنجاح!',
  'Bulk upload failed': 'فشل الرفع الجماعي',
  'Delete users from this file? This action cannot be undone.': 'حذف المستخدمين من هذا الملف؟ لا يمكن التراجع عن هذا الإجراء.',
  'Users deleted successfully!': 'تم حذف المستخدمين بنجاح!',
  'Bulk delete failed': 'فشل الحذف الجماعي',
  'Selected user is missing an HR ID': 'المستخدم المحدد لا يحتوي على رقم وظيفي',
  'Failed to load user details': 'تعذر تحميل تفاصيل المستخدم',
  Reason: 'السبب',
  'unadded-users.csv': 'المستخدمون-غير-المضافين.csv',
  'Please select a branch': 'يرجى اختيار فرع',
  'Password is required when creating a user': 'كلمة المرور مطلوبة عند إنشاء مستخدم',
  'User updated successfully!': 'تم تحديث المستخدم بنجاح!',
  'User created successfully!': 'تم إنشاء المستخدم بنجاح!',
  'Operation failed': 'فشلت العملية',
  'Are you sure you want to delete this user?': 'هل أنت متأكد من حذف هذا المستخدم؟',
  'User deleted successfully!': 'تم حذف المستخدم بنجاح!',
  'Delete failed': 'فشل الحذف',
  Role: 'الدور',
  Actions: 'الإجراءات',
  'No users found.': 'لا يوجد مستخدمون.',
  'User Management': 'إدارة المستخدمين',
  'Search HR ID / Name / Email': 'بحث برقم وظيفي / اسم / بريد',
  'Search Email / HR ID / Name / Branch / Branch Code / Role': 'بحث بالبريد / الرقم الوظيفي / الاسم / الفرع / كود الفرع / الدور',
  'Search in list': 'بحث داخل القائمة',
  'Select all shown': 'تحديد كل المعروض',
  'Clear filter': 'إلغاء الفلتر',
  'Reset Filters': 'إعادة ضبط الفلاتر',
  Selected: 'محدد',
  Filters: 'الفلاتر',
  'No options found': 'لا توجد خيارات',
  'Uploading...': 'جارٍ الرفع...',
  'Bulk Upload Users': 'رفع جماعي للمستخدمين',
  'Deleting...': 'جارٍ الحذف...',
  'Bulk Delete Users': 'حذف جماعي للمستخدمين',
  'Delete Selected Users': 'حذف المستخدمين المحددين',
  'Select Filtered': 'تحديد نتائج البحث',
  'Select All Users': 'تحديد كل المستخدمين',
  'Clear Selection': 'إلغاء التحديد',
  'Delete selected users?': 'هل تريد حذف المستخدمين المحددين؟',
  'Selected users deleted successfully': 'تم حذف المستخدمين المحددين بنجاح',
  'Some users failed to delete': 'فشل حذف بعض المستخدمين',
  'No deletable users selected': 'لا يوجد مستخدمون قابلون للحذف في التحديد',
  'Role sort order: admin, Retail, hr': 'ترتيب الأدوار: أدمن، Retail، hr',
  ALL: 'الكل',
  'Rows per page': 'عدد الصفوف في الصفحة',
  'No rows': 'لا يوجد صفوف',
  'Create User': 'إنشاء مستخدم',
  'Bulk upload columns: HR ID, Name, Title, Department, Email, Branch_Code. Bulk delete columns: HR ID or Email.':
    'أعمدة الرفع الجماعي: الرقم الوظيفي، الاسم، المسمى الوظيفي، الإدارة، البريد الإلكتروني، كود الفرع. أعمدة الحذف الجماعي: الرقم الوظيفي أو البريد الإلكتروني.',
  Showing: 'عرض',
  of: 'من',
  users: 'مستخدمين',
  'Edit User': 'تعديل مستخدم',
  'Create New User': 'إنشاء مستخدم جديد',
  'Loading branches...': 'جارٍ تحميل الفروع...',
  'Pick a branch; its region/area/division/sub-department are derived automatically.':
    'اختر فرعاً وسيتم تعبئة الإقليم/المنطقة/القطاع/الإدارة الفرعية تلقائياً.',
  'No branches found. Upload branches first.': 'لا توجد فروع. ارفع بيانات الفروع أولاً.',
  'Department / Role': 'الإدارة / الدور',
  'New Password (leave blank to keep)': 'كلمة مرور جديدة (اتركه فارغاً للإبقاء الحالية)',
  'Leave blank to keep the existing password': 'اتركه فارغاً للإبقاء على كلمة المرور الحالية',
  'Minimum 8 characters': '8 أحرف كحد أدنى',
  Cancel: 'إلغاء',
  Update: 'تحديث',
  Create: 'إنشاء',
  'Bulk Upload Summary': 'ملخص الرفع الجماعي',
  Updated: 'تم التحديث',
  Created: 'تم الإنشاء',
  Unadded: 'غير مضاف',
  'Unadded Users': 'المستخدمون غير المضافين',
  'All users were processed successfully.': 'تمت معالجة جميع المستخدمين بنجاح.',
  'No results to display.': 'لا توجد نتائج للعرض.',
  'Download Unadded CSV': 'تنزيل CSV لغير المضافين',
  Close: 'إغلاق',
  'User Details': 'تفاصيل المستخدم',
  Hide: 'إخفاء',
  Show: 'إظهار',
  'No data available.': 'لا توجد بيانات.',
};

const UserManagement = () => {
  const { t, isArabic } = useLanguage();
  const tr = useCallback(
    (en, ar) => {
      const hasArabic = typeof ar === 'string' && /[\u0600-\u06FF]/.test(ar);
      return t(en, hasArabic ? ar : USER_MANAGEMENT_AR[en] || en);
    },
    [t]
  );
  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [totalUsers, setTotalUsers] = useState(0);
  const [userFilters, setUserFilters] = useState(() => buildEmptyFilterState());
  const [filterSearchText, setFilterSearchText] = useState(() => buildEmptyFilterSearchState());
  const [filterOptions, setFilterOptions] = useState(() => buildEmptyFilterState());
  const [filterOptionsLoading, setFilterOptionsLoading] = useState(false);
  const [activeFilterKey, setActiveFilterKey] = useState(null);
  const [filterAnchorEl, setFilterAnchorEl] = useState(null);
  const [currentPage, setCurrentPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(20);
  const [openDialog, setOpenDialog] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [formData, setFormData] = useState({ ...initialFormData });
  const [alert, setAlert] = useState({ show: false, message: '', severity: 'success' });
  const [viewDialogOpen, setViewDialogOpen] = useState(false);
  const [viewingUser, setViewingUser] = useState(null);
  const [viewLoading, setViewLoading] = useState(false);
  const [bulkUploadLoading, setBulkUploadLoading] = useState(false);
  const [bulkDeleteLoading, setBulkDeleteLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [bulkDeleteSelectedLoading, setBulkDeleteSelectedLoading] = useState(false);
  const [bulkSummaryOpen, setBulkSummaryOpen] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [sortConfig, setSortConfig] = useState({ key: 'role', direction: 'asc' });
  const [selectedEmails, setSelectedEmails] = useState(() => new Set());
  const usersRequestIdRef = useRef(0);
  const filterOptionsRequestIdRef = useRef(0);
  const fileInputRef = useRef(null);
  const bulkDeleteInputRef = useRef(null);
  const [branches, setBranches] = useState([]);
  const [branchesLoading, setBranchesLoading] = useState(false);
  const [openBranchDialog, setOpenBranchDialog] = useState(false);
  const [branchFormData, setBranchFormData] = useState({ ...initialBranchFormData });
  const [branchSaveLoading, setBranchSaveLoading] = useState(false);
  const currentUser = useMemo(() => authService.getCurrentUser(), []);
  const currentUserRole = useMemo(
    () => normalizeRoleValue(currentUser?.role || currentUser?.department),
    [currentUser]
  );
  const hasOptionalTitle = ['admin', 'auditor', 'hr'].includes(normalizeRoleValue(formData.department));
  const isHrViewer = currentUserRole === 'hr';
  const canManageAdminUsers = ['admin', 'auditor'].includes(currentUserRole);
  const isRetailRole = useCallback(
    (roleValue) => normalizeRoleValue(roleValue) === 'retail' || normalizeRoleValue(roleValue) === 'employee',
    []
  );
  const canManageUser = useCallback(
    (user) => {
      if (normalizeRoleValue(user?.role ?? user?.department) === 'auditor') return currentUserRole === 'admin';
      if (canManageAdminUsers) return true;
      return isRetailRole(user?.role ?? user?.department);
    },
    [canManageAdminUsers, isRetailRole, currentUserRole]
  );
  const isBranchRequired = useCallback(
    (departmentValue) => {
      const role = normalizeRoleValue(departmentValue);
      return !['admin', 'auditor', 'hr'].includes(role);
    },
    []
  );

  const fieldLabels = useMemo(
    () => ({
      email: tr('Email', '?????? ??????????'),
      hr_id: tr('HR ID', '????? ???????'),
      name: tr('Full Name', '????? ??????'),
      title: tr('Title', '?????? ???????'),
    }),
    [tr]
  );

  const availableTitleOptions = useMemo(() => {
    const currentTitle = (formData.title || '').toString().trim();
    if (!currentTitle || titleOptions.some((option) => option.value === currentTitle)) {
      return titleOptions;
    }

    return [...titleOptions, { value: currentTitle, label: currentTitle }];
  }, [formData.title]);

  const branchFieldLabels = useMemo(
    () => ({
      branch_code: tr('Branch Code', 'كود الفرع'),
      branch_name: tr('Branch Name', 'اسم الفرع'),
      branch_region: tr('Region', 'الإقليم'),
      branch_area: tr('Area', 'المنطقة'),
      branch_division: tr('Division', 'القطاع'),
      branch_sub_department: tr('Sub Department', 'الإدارة الفرعية'),
    }),
    [tr]
  );

  const branchDivisionOptions = useMemo(
    () => [
      { value: 'Fawry', label: 'Fawry' },
      { value: 'Fawry Plus', label: 'Fawry Plus' },
    ],
    []
  );

  const branchRegionOptions = useMemo(
    () => sortTextOptions(branches.map((branch) => branch.region)),
    [branches]
  );

  const branchAreaOptions = useMemo(() => {
    const selectedRegion = branchFormData.branch_region.trim().toLowerCase();
    const matchedBranches = selectedRegion
      ? branches.filter((branch) => (branch.region || '').trim().toLowerCase() === selectedRegion)
      : branches;
    return sortTextOptions(matchedBranches.map((branch) => branch.area));
  }, [branches, branchFormData.branch_region]);

  const branchSubDepartmentOptions = useMemo(() => {
    const selectedDivision = branchFormData.branch_division.trim().toLowerCase();
    const selectedRegion = branchFormData.branch_region.trim().toLowerCase();
    const selectedArea = branchFormData.branch_area.trim().toLowerCase();
    const hasScopedSelection = Boolean(selectedDivision || selectedRegion || selectedArea);
    const matchedBranches = hasScopedSelection
      ? branches.filter((branch) => {
          if (selectedDivision && (branch.division || '').trim().toLowerCase() !== selectedDivision) return false;
          if (selectedRegion && (branch.region || '').trim().toLowerCase() !== selectedRegion) return false;
          if (selectedArea && (branch.area || '').trim().toLowerCase() !== selectedArea) return false;
          return true;
        })
      : branches;
    return sortTextOptions(matchedBranches.map((branch) => branch.sub_department));
  }, [branches, branchFormData.branch_division, branchFormData.branch_region, branchFormData.branch_area]);

  const roleOptions = useMemo(() => {
    const baseOptions = [
      { value: 'hr', label: tr('HR', 'الموارد البشرية') },
      { value: 'Retail', label: tr('Retail (Employee)', '????? (????)') },
    ];
    if (!isHrViewer) {
      baseOptions.unshift({ value: 'admin', label: tr('Admin', '????') });
    }
    if (currentUserRole === 'admin') {
      baseOptions.unshift({ value: 'auditor', label: tr('Auditor', 'مدقق') });
    }
    return baseOptions;
  }, [isHrViewer, tr, isRetailRole, currentUserRole]);

  const userDetailFields = useMemo(
    () => [
      { key: 'email', label: tr('Email', '?????? ??????????') },
      { key: 'hr_id', label: tr('HR ID', '????? ???????') },
      { key: 'name', label: tr('Name', '?????') },
      { key: 'title', label: tr('Title', '?????? ???????') },
      { key: 'branch', label: tr('Branch', '?????') },
      { key: 'branch_code', label: tr('Branch Code', 'كود الفرع') },
      { key: 'area', label: tr('Area', '???????') },
      { key: 'region', label: tr('Region', '???????') },
      { key: 'division', label: tr('Division', '??????') },
      { key: 'department', label: tr('Department', '?????') },
      { key: 'sub_department', label: tr('Sub Department', '????? ??????') },
    ],
    [tr]
  );

  const filterDefinitions = useMemo(
    () => [
      { key: 'email', label: tr('Email', 'البريد الإلكتروني') },
      { key: 'hr_id', label: tr('HR ID', 'الرقم الوظيفي') },
      { key: 'name', label: tr('Name', 'الاسم') },
      { key: 'branch', label: tr('Branch', 'الفرع') },
      { key: 'branch_code', label: tr('Branch Code', 'كود الفرع') },
      { key: 'role', label: tr('Role', 'الدور') },
    ],
    [tr]
  );

  const loadUsers = useCallback(async () => {
    const requestId = ++usersRequestIdRef.current;
    setUsersLoading(true);
    try {
      const response = await userService.getAllUsers({
        page: currentPage + 1,
        page_size: rowsPerPage,
        sort_by: sortConfig.key,
        sort_direction: sortConfig.direction,
        filters: JSON.stringify(userFilters),
      });
      // Ignore an older response when a newer page-size, filter, or sort request is pending.
      if (requestId === usersRequestIdRef.current) {
        setUsers(response.data.users || []);
        setTotalUsers(response.data.total || 0);
      }
    } catch (error) {
      if (requestId === usersRequestIdRef.current) {
        setAlert({
          show: true,
          message: error.response?.data?.message || error.response?.data?.detail || tr('Failed to load users', '??? ????? ??????????'),
          severity: 'error',
        });
      }
    } finally {
      if (requestId === usersRequestIdRef.current) {
        setUsersLoading(false);
      }
    }
  }, [currentPage, rowsPerPage, sortConfig, tr, userFilters]);

  const loadBranches = useCallback(async () => {
    setBranchesLoading(true);
    try {
      const response = await userService.getAudienceHierarchy();
      const regions = response.data?.data?.regions || [];
      const flattened = [];
      regions.forEach((region) => {
        region.areas?.forEach((area) => {
          area.branches?.forEach((branch) => {
            flattened.push({
              branch_code: branch.branch_code,
              branch_name: branch.branch_name,
              region: region.region,
              area: area.area,
              division: branch.division,
              sub_department: branch.sub_department,
            });
          });
        });
      });
      setBranches(flattened);
    } catch (error) {
      console.error('Failed to load branches', error);
      setAlert((prev) => ({
        show: true,
        severity: 'error',
        message: tr('Unable to load branches. Upload branch data first.', '???? ????? ??????. ???? ??? ?????? ?????? ?????.'),
      }));
    } finally {
      setBranchesLoading(false);
    }
  }, [tr]);

  useEffect(() => {
    loadUsers();
    loadBranches();
  }, [loadUsers, loadBranches]);

  const handleFieldChange = useCallback((name, value) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
  }, []);

  const handleBranchFieldChange = useCallback((name, value) => {
    setBranchFormData((prev) => ({ ...prev, [name]: value }));
  }, []);

  const handleBulkUploadClick = useCallback(() => {
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
      fileInputRef.current.click();
    }
  }, []);

  const handleBulkDeleteClick = useCallback(() => {
    if (bulkDeleteInputRef.current) {
      bulkDeleteInputRef.current.value = '';
      bulkDeleteInputRef.current.click();
    }
  }, []);

  const handleBulkFileChange = useCallback(async (event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setBulkUploadLoading(true);
    try {
      const response = await userService.bulkUploadUsers(file);
      const summary = response.data || {};
      setBulkResult({
        updated: summary.updated ?? 0,
        created: summary.created ?? 0,
        unadded_count: summary.unadded_count ?? 0,
        unadded_users: summary.unadded_users || [],
      });
      setBulkSummaryOpen(true);
      setAlert({
        show: true,
        message: summary.message || tr('Users uploaded successfully!', '?? ??? ?????????? ?????!'),
        severity: 'success',
      });
      loadUsers();
    } catch (error) {
      setAlert({
        show: true,
        message: error.response?.data?.message || error.response?.data?.detail || tr('Bulk upload failed', '??? ????? ???????'),
        severity: 'error',
      });
    } finally {
      setBulkUploadLoading(false);
      if (event?.target) {
        event.target.value = '';
      }
    }
  }, [loadUsers, tr]);

  const handleBulkDeleteFileChange = useCallback(async (event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    if (!window.confirm(tr('Delete users from this file? This action cannot be undone.', '??? ?????????? ?? ??? ?????? ?? ???? ??????? ?? ??? ???????.'))) {
      if (event?.target) {
        event.target.value = '';
      }
      return;
    }

    setBulkDeleteLoading(true);
    try {
      const response = await userService.bulkDeleteUsers(file);
      const summary = response.data || {};
      setAlert({
        show: true,
        message: summary.message || tr('Users deleted successfully!', '?? ??? ?????????? ?????!'),
        severity: 'success',
      });
      loadUsers();
    } catch (error) {
      setAlert({
        show: true,
        message: error.response?.data?.message || error.response?.data?.detail || tr('Bulk delete failed', '??? ????? ???????'),
        severity: 'error',
      });
    } finally {
      setBulkDeleteLoading(false);
      if (event?.target) {
        event.target.value = '';
      }
    }
  }, [loadUsers, tr]);

  const handleExportUsers = useCallback(async () => {
    setExportLoading(true);
    try {
      const response = await userService.exportUsersExcel();
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      const timestamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
      link.href = url;
      link.setAttribute('download', `users-export-${timestamp}.xlsx`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      setAlert({
        show: true,
        message: error.response?.data?.message || error.response?.data?.detail || tr('Export failed', 'Export failed'),
        severity: 'error',
      });
    } finally {
      setExportLoading(false);
    }
  }, [tr]);

  const handleViewUser = useCallback(async (user) => {
    if (!user?.hr_id) {
      setAlert({
        show: true,
        message: tr('Selected user is missing an HR ID', '???????? ?????? ?? ????? ??? ??? ?????'),
        severity: 'error',
      });
      return;
    }

    setViewDialogOpen(true);
    setViewLoading(true);
    setViewingUser(null);
    try {
      const response = await userService.getUserByHrId(user.hr_id);
      setViewingUser(response.data.user || null);
    } catch (error) {
      setAlert({
        show: true,
        message: error.response?.data?.message || error.response?.data?.detail || tr('Failed to load user details', '??? ????? ?????? ????????'),
        severity: 'error',
      });
      setViewDialogOpen(false);
    } finally {
      setViewLoading(false);
    }
  }, [tr]);

  const handleCloseViewDialog = useCallback(() => {
    setViewDialogOpen(false);
    setViewingUser(null);
    setViewLoading(false);
  }, []);

  const handleCloseBulkSummary = useCallback(() => {
    setBulkSummaryOpen(false);
  }, []);

  const handleExportUnadded = useCallback(() => {
    if (!bulkResult?.unadded_users?.length) {
      return;
    }
    const header = [tr('HR ID', '????? ???????'), tr('Email', '?????? ??????????'), tr('Reason', '?????')];
    const rows = bulkResult.unadded_users.map((u) => [
      u.hr_id || '',
      u.email || '',
      (u.reason || '').replace(/[\r\n]+/g, ' '),
    ]);
    const csvContent = [header, ...rows]
      .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', tr('unadded-users.csv', '????????-???-??????.csv'));
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  }, [bulkResult, tr]);

  const selectedBranchMeta = useMemo(
    () => branches.find((branch) => branch.branch_code === formData.branch_code),
    [branches, formData.branch_code]
  );

  const handleOpenDialog = useCallback((user = null) => {
    if (user) {
      setEditingUser(user);
      setFormData({
        email: user.email || '',
        hr_id: user.hr_id || '',
        name: user.name || '',
        title: user.title || '',
        branch_code: user.branch_code || '',
        department: ['admin', 'auditor', 'hr'].includes(normalizeRoleValue(user.department))
          ? normalizeRoleValue(user.department)
          : user.department || 'Retail',
      });
    } else {
      setEditingUser(null);
      setFormData({ ...initialFormData });
    }
    setOpenDialog(true);
  }, []);

  const handleCloseDialog = useCallback(() => {
    setOpenDialog(false);
    setEditingUser(null);
    setFormData({ ...initialFormData });
  }, []);

  const handleOpenBranchDialog = useCallback(() => {
    setBranchFormData({ ...initialBranchFormData });
    setOpenBranchDialog(true);
  }, []);

  const handleCloseBranchDialog = useCallback(() => {
    setOpenBranchDialog(false);
    setBranchFormData({ ...initialBranchFormData });
  }, []);

  const handleSaveBranch = useCallback(async () => {
    const payload = Object.fromEntries(
      Object.entries(branchFormData).map(([key, value]) => [key, typeof value === 'string' ? value.trim() : value])
    );

    if (Object.values(payload).some((value) => !value)) {
      setAlert({
        show: true,
        message: tr('All branch fields are required.', 'جميع حقول الفرع مطلوبة.'),
        severity: 'error',
      });
      return;
    }

    setBranchSaveLoading(true);
    try {
      const response = await userService.createBranch(payload);
      setAlert({
        show: true,
        message: response.data?.message || tr('Branch created successfully!', 'تم إنشاء الفرع بنجاح!'),
        severity: 'success',
      });
      handleCloseBranchDialog();
      await loadBranches();
    } catch (error) {
      setAlert({
        show: true,
        message: error.response?.data?.message || error.response?.data?.detail || tr('Branch creation failed', 'فشل إنشاء الفرع'),
        severity: 'error',
      });
    } finally {
      setBranchSaveLoading(false);
    }
  }, [branchFormData, handleCloseBranchDialog, loadBranches, tr]);

  const handleSaveUser = useCallback(async () => {
    const payload = { ...formData };

    if (isBranchRequired(formData.department) && !formData.branch_code) {
      setAlert({
        show: true,
        message: tr('Please select a branch', '???? ?????? ???'),
        severity: 'error',
      });
      return;
    }
    if (!isBranchRequired(formData.department)) {
      delete payload.branch_code;
    }

    try {
      if (editingUser) {
        await userService.updateUser(editingUser.email, payload);
        setAlert({ show: true, message: tr('User updated successfully!', '?? ????? ???????? ?????!'), severity: 'success' });
      } else {
        await userService.createUser(payload);
        setAlert({ show: true, message: tr('User created successfully!', '?? ????? ???????? ?????!'), severity: 'success' });
      }
      handleCloseDialog();
      loadUsers();
    } catch (error) {
      setAlert({
        show: true,
        message: error.response?.data?.message || error.response?.data?.detail || tr('Operation failed', '???? ???????'),
        severity: 'error',
      });
    }
  }, [formData, editingUser, handleCloseDialog, loadUsers, tr, isBranchRequired]);

  const handleDeleteUser = useCallback(async (email) => {
    if (window.confirm(tr('Are you sure you want to delete this user?', '?? ??? ????? ?? ??? ??? ?????????'))) {
      try {
        await userService.deleteUser(email);
        setAlert({ show: true, message: tr('User deleted successfully!', '?? ??? ???????? ?????!'), severity: 'success' });
        loadUsers();
      } catch (error) {
        setAlert({
          show: true,
          message: error.response?.data?.message || error.response?.data?.detail || tr('Delete failed', '??? ?????'),
          severity: 'error',
        });
      }
    }
  }, [loadUsers, tr]);

  const getRoleColor = useCallback((role) => {
    switch (role) {
      case 'admin':
        return 'error';
      case 'hr':
        return 'warning';
      default:
        return 'info';
    }
  }, []);

  const normalizeRole = useCallback((user) => {
    const rawRole = user?.role ?? user?.department ?? '';
    return normalizeRoleValue(rawRole);
  }, []);

  const roleRank = useCallback((role) => {
    const value = (role || '').toLowerCase();
    if (value === 'admin') return 0;
    if (value === 'retail') return 1;
    if (value === 'hr') return 2;
    return 3;
  }, []);

  const compareMixed = useCallback((left, right) => {
    const a = (left ?? '').toString().trim();
    const b = (right ?? '').toString().trim();
    const aNum = a !== '' && !Number.isNaN(Number(a));
    const bNum = b !== '' && !Number.isNaN(Number(b));
    if (aNum && bNum) {
      return Number(a) - Number(b);
    }
    return a.localeCompare(b, undefined, { sensitivity: 'base' });
  }, []);

  const renderFilterOptionLabel = useCallback((key, value) => {
    if (key === 'role') {
      return value.toUpperCase();
    }
    return value;
  }, []);

  const loadFilterOptions = useCallback(async () => {
    if (!activeFilterKey) return;

    const requestId = ++filterOptionsRequestIdRef.current;
    setFilterOptionsLoading(true);
    try {
      const response = await userService.getUserFilterOptions({
        field: activeFilterKey,
        search: filterSearchText[activeFilterKey] || '',
        filters: JSON.stringify(userFilters),
      });
      if (requestId === filterOptionsRequestIdRef.current) {
        setFilterOptions((previous) => ({
          ...previous,
          [activeFilterKey]: response.data?.options || [],
        }));
      }
    } catch (error) {
      if (requestId === filterOptionsRequestIdRef.current) {
        setFilterOptions((previous) => ({ ...previous, [activeFilterKey]: [] }));
        console.error('Failed to load user filter options', error);
      }
    } finally {
      if (requestId === filterOptionsRequestIdRef.current) {
        setFilterOptionsLoading(false);
      }
    }
  }, [activeFilterKey, filterSearchText, userFilters]);

  useEffect(() => {
    if (!activeFilterKey) return undefined;

    const timer = window.setTimeout(loadFilterOptions, 250);
    return () => window.clearTimeout(timer);
  }, [activeFilterKey, loadFilterOptions]);

  const activeFilterOptions = useMemo(() => {
    if (!activeFilterKey) return [];
    const selectedValues = userFilters[activeFilterKey] || [];
    const values = Array.from(new Set([...(filterOptions[activeFilterKey] || []), ...selectedValues]));
    if (activeFilterKey === 'role') {
      return values.sort((a, b) => {
        const rankDiff = roleRank(a) - roleRank(b);
        return rankDiff || compareMixed(a, b);
      });
    }
    return values.sort(compareMixed);
  }, [activeFilterKey, filterOptions, userFilters, roleRank, compareMixed]);

  useEffect(() => {
    setCurrentPage(0);
  }, [userFilters, sortConfig, rowsPerPage]);

  const totalPages = useMemo(() => {
    if (rowsPerPage === -1) {
      return 1;
    }
    return Math.max(1, Math.ceil(totalUsers / rowsPerPage));
  }, [rowsPerPage, totalUsers]);

  useEffect(() => {
    setCurrentPage((prev) => Math.min(prev, totalPages - 1));
  }, [totalPages]);

  // Pagination, sorting, and active filters are applied by the database.
  const paginatedUsers = users;

  const selectedCount = selectedEmails.size;

  const pageDeletableEmails = useMemo(
    () =>
      paginatedUsers
        .filter((user) => canManageAdminUsers || isRetailRole(normalizeRole(user)))
        .map((user) => user.email),
    [paginatedUsers, normalizeRole, canManageAdminUsers, isRetailRole]
  );
  const filteredDeletableEmails = useMemo(
    () =>
      paginatedUsers
        .filter((user) => canManageAdminUsers || isRetailRole(normalizeRole(user)))
        .map((user) => user.email),
    [paginatedUsers, normalizeRole, canManageAdminUsers, isRetailRole]
  );

  const pageSelectedCount = useMemo(
    () => pageDeletableEmails.filter((email) => selectedEmails.has(email)).length,
    [pageDeletableEmails, selectedEmails]
  );

  const hasActiveFilters = useMemo(
    () => filterDefinitions.some(({ key }) => (userFilters[key] || []).length > 0),
    [filterDefinitions, userFilters]
  );

  const handleOpenFilterPopover = useCallback((event, key) => {
    setActiveFilterKey(key);
    setFilterAnchorEl(event.currentTarget);
  }, []);

  const handleCloseFilterPopover = useCallback(() => {
    setActiveFilterKey(null);
    setFilterAnchorEl(null);
  }, []);

  const handleFilterSearchChange = useCallback((key, value) => {
    setFilterSearchText((prev) => ({
      ...prev,
      [key]: value,
    }));
  }, []);

  const handleToggleFilterValue = useCallback((key, value) => {
    setUserFilters((prev) => {
      const currentValues = prev[key] || [];
      const exists = currentValues.includes(value);
      return {
        ...prev,
        [key]: exists ? currentValues.filter((entry) => entry !== value) : [...currentValues, value],
      };
    });
  }, []);

  const handleSelectAllShownOptions = useCallback(() => {
    if (!activeFilterKey) return;
    setUserFilters((prev) => {
      const existing = new Set(prev[activeFilterKey] || []);
      activeFilterOptions.forEach((value) => existing.add(value));
      return {
        ...prev,
        [activeFilterKey]: Array.from(existing),
      };
    });
  }, [activeFilterKey, activeFilterOptions]);

  const handleClearActiveFilter = useCallback(() => {
    if (!activeFilterKey) return;
    setUserFilters((prev) => ({
      ...prev,
      [activeFilterKey]: [],
    }));
    setFilterSearchText((prev) => ({
      ...prev,
      [activeFilterKey]: '',
    }));
  }, [activeFilterKey]);

  const handleResetAllFilters = useCallback(() => {
    setUserFilters(buildEmptyFilterState());
    setFilterSearchText(buildEmptyFilterSearchState());
  }, []);

  const handleSortRequest = useCallback((key) => {
    setSortConfig((prev) => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc',
    }));
  }, []);

  const handleToggleSelectRow = useCallback((email) => {
    setSelectedEmails((prev) => {
      const next = new Set(prev);
      if (next.has(email)) {
        next.delete(email);
      } else {
        next.add(email);
      }
      return next;
    });
  }, []);

  const handleToggleSelectPage = useCallback((checked) => {
    setSelectedEmails((prev) => {
      const next = new Set(prev);
      if (checked) {
        pageDeletableEmails.forEach((email) => next.add(email));
      } else {
        pageDeletableEmails.forEach((email) => next.delete(email));
      }
      return next;
    });
  }, [pageDeletableEmails]);

  const handleSelectFiltered = useCallback(() => {
    setSelectedEmails(new Set(filteredDeletableEmails));
  }, [filteredDeletableEmails]);

  const handleClearSelection = useCallback(() => {
    setSelectedEmails(new Set());
  }, []);

  const handleDeleteSelectedUsers = useCallback(async () => {
    const targetEmails = Array.from(selectedEmails).filter((email) =>
      users.some((user) => user.email === email && (canManageAdminUsers || isRetailRole(normalizeRole(user))))
    );
    if (!targetEmails.length) {
      setAlert({
        show: true,
        message: tr('No deletable users selected', 'لا يوجد مستخدمون قابلون للحذف في التحديد'),
        severity: 'warning',
      });
      return;
    }

    if (!window.confirm(tr('Delete selected users?', 'هل تريد حذف المستخدمين المحددين؟'))) {
      return;
    }

    setBulkDeleteSelectedLoading(true);
    try {
      const results = await Promise.allSettled(targetEmails.map((email) => userService.deleteUser(email)));
      const successCount = results.filter((result) => result.status === 'fulfilled').length;
      const failCount = results.length - successCount;

      if (successCount > 0) {
        await loadUsers();
      }

      setSelectedEmails((prev) => {
        const next = new Set(prev);
        targetEmails.forEach((email) => next.delete(email));
        return next;
      });

      setAlert({
        show: true,
        message:
          failCount === 0
            ? `${tr('Selected users deleted successfully', 'تم حذف المستخدمين المحددين بنجاح')}: ${successCount}`
            : `${tr('Some users failed to delete', 'فشل حذف بعض المستخدمين')}. ${tr('Deleted', 'تم الحذف')}: ${successCount}, ${tr('Failed', 'فشل')}: ${failCount}`,
        severity: failCount === 0 ? 'success' : 'warning',
      });
    } catch (error) {
      setAlert({
        show: true,
        message: error.response?.data?.message || error.response?.data?.detail || tr('Delete failed', 'فشل الحذف'),
        severity: 'error',
      });
    } finally {
      setBulkDeleteSelectedLoading(false);
    }
  }, [selectedEmails, users, loadUsers, tr, normalizeRole, canManageAdminUsers, isRetailRole]);

  const handleChangePage = useCallback((_event, newPage) => {
    setCurrentPage(newPage);
  }, []);

  const handleChangeRowsPerPage = useCallback((event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setCurrentPage(0);
  }, []);

  const usersTable = useMemo(
    () => (
      <Card>
        <CardContent>
          <TableContainer component={Paper} elevation={0} sx={{ maxWidth: '100%', overflowX: 'auto' }}>
            <Table sx={{ minWidth: 1180 }}>
              <TableHead>
                <TableRow sx={{ bgcolor: 'grey.100' }}>
                  <TableCell padding="checkbox">
                    <Checkbox
                      checked={pageDeletableEmails.length > 0 && pageSelectedCount === pageDeletableEmails.length}
                      indeterminate={pageSelectedCount > 0 && pageSelectedCount < pageDeletableEmails.length}
                      onChange={(event) => handleToggleSelectPage(event.target.checked)}
                    />
                  </TableCell>
                  <TableCell sortDirection={sortConfig.key === 'email' ? sortConfig.direction : false}>
                    <TableSortLabel
                      active={sortConfig.key === 'email'}
                      direction={sortConfig.key === 'email' ? sortConfig.direction : 'asc'}
                      hideSortIcon={false}
                      onClick={() => handleSortRequest('email')}
                    >
                      <strong>{tr('Email', 'البريد الإلكتروني')}</strong>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortConfig.key === 'hr_id' ? sortConfig.direction : false}>
                    <TableSortLabel
                      active={sortConfig.key === 'hr_id'}
                      direction={sortConfig.key === 'hr_id' ? sortConfig.direction : 'asc'}
                      hideSortIcon={false}
                      onClick={() => handleSortRequest('hr_id')}
                    >
                      <strong>{tr('HR ID', 'الرقم الوظيفي')}</strong>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortConfig.key === 'name' ? sortConfig.direction : false}>
                    <TableSortLabel
                      active={sortConfig.key === 'name'}
                      direction={sortConfig.key === 'name' ? sortConfig.direction : 'asc'}
                      hideSortIcon={false}
                      onClick={() => handleSortRequest('name')}
                    >
                      <strong>{tr('Name', 'الاسم')}</strong>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortConfig.key === 'branch' ? sortConfig.direction : false}>
                    <TableSortLabel
                      active={sortConfig.key === 'branch'}
                      direction={sortConfig.key === 'branch' ? sortConfig.direction : 'asc'}
                      hideSortIcon={false}
                      onClick={() => handleSortRequest('branch')}
                    >
                      <strong>{tr('Branch', 'الفرع')}</strong>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortConfig.key === 'branch_code' ? sortConfig.direction : false}>
                    <TableSortLabel
                      active={sortConfig.key === 'branch_code'}
                      direction={sortConfig.key === 'branch_code' ? sortConfig.direction : 'asc'}
                      hideSortIcon={false}
                      onClick={() => handleSortRequest('branch_code')}
                    >
                      <strong>{tr('Branch Code', 'كود الفرع')}</strong>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortConfig.key === 'role' ? sortConfig.direction : false}>
                    <TableSortLabel
                      active={sortConfig.key === 'role'}
                      direction={sortConfig.key === 'role' ? sortConfig.direction : 'asc'}
                      hideSortIcon={false}
                      onClick={() => handleSortRequest('role')}
                    >
                      <strong>{tr('Role', 'الدور')}</strong>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell align="right">
                    <strong>{tr('Actions', 'الإجراءات')}</strong>
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {!usersLoading && paginatedUsers.map((user) => (
                  <TableRow key={user.employee_id || user.email} hover>
                    <TableCell padding="checkbox">
                      <Checkbox
                        checked={selectedEmails.has(user.email)}
                        onChange={() => handleToggleSelectRow(user.email)}
                        disabled={!canManageUser(user)}
                      />
                    </TableCell>
                    <TableCell>{user.email}</TableCell>
                    <TableCell>{user.hr_id}</TableCell>
                    <TableCell>{user.name}</TableCell>
                    <TableCell>{user.branch}</TableCell>
                    <TableCell>{user.branch_code || '-'}</TableCell>
                    <TableCell>
                      <Chip
                        label={normalizeRole(user).toUpperCase()}
                        color={getRoleColor(normalizeRole(user))}
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="right">
                      <IconButton onClick={() => handleViewUser(user)} color="info">
                        <Visibility />
                      </IconButton>
                      <IconButton onClick={() => handleOpenDialog(user)} color="primary">
                        <Edit />
                      </IconButton>
                      <IconButton
                        onClick={() => handleDeleteUser(user.email)}
                        color="error"
                        disabled={!canManageUser(user)}
                      >
                        <Delete />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
                {usersLoading ? (
                  <TableRow>
                    <TableCell colSpan={8} sx={{ py: 5 }} align="center">
                      <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 1.25, color: 'text.secondary' }}>
                        <CircularProgress size={20} />
                        <Typography color="text.secondary">{tr('Loading users...', 'جارٍ تحميل المستخدمين...')}</Typography>
                      </Box>
                    </TableCell>
                  </TableRow>
                ) : !paginatedUsers.length && (
                  <TableRow>
                    <TableCell colSpan={8} sx={{ py: 4 }} align="center">
                      <Typography color="text.secondary">{tr('No users found.', 'لا يوجد مستخدمون.')}</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={totalUsers}
            page={currentPage}
            onPageChange={handleChangePage}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={handleChangeRowsPerPage}
            rowsPerPageOptions={[
              20,
              50,
              100,
              { label: tr('All', 'الكل'), value: -1 },
            ]}
            labelRowsPerPage={tr('Rows per page', 'عدد الصفوف في الصفحة')}
          />
        </CardContent>
      </Card>
    ),
    [
      paginatedUsers,
      selectedEmails,
      pageDeletableEmails.length,
      pageSelectedCount,
      canManageAdminUsers,
      handleToggleSelectPage,
      sortConfig,
      handleSortRequest,
      tr,
      handleToggleSelectRow,
      normalizeRole,
      canManageUser,
      getRoleColor,
      handleViewUser,
      handleOpenDialog,
      handleDeleteUser,
      totalUsers,
      currentPage,
      handleChangePage,
      rowsPerPage,
      handleChangeRowsPerPage,
    ]
  );

  return (
    <Box sx={{ direction: isArabic ? 'rtl' : 'ltr' }}>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: { xs: 'stretch', lg: 'center' },
          mb: 3,
          flexWrap: 'wrap',
          gap: 2,
        }}
      >
        <Typography
          variant="h4"
          fontWeight="bold"
          sx={{
            flex: '1 1 280px',
            minWidth: 0,
            whiteSpace: { xs: 'normal', md: 'nowrap' },
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {tr('User Management', '????? ??????????')}
        </Typography>
        <Box
          sx={{
            display: 'flex',
            gap: 1,
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: { xs: 'flex-start', md: 'flex-end' },
            flex: '1 1 520px',
            minWidth: 0,
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".xls,.xlsx"
            style={{ display: 'none' }}
            onChange={handleBulkFileChange}
          />
          <input
            ref={bulkDeleteInputRef}
            type="file"
            accept=".xls,.xlsx"
            style={{ display: 'none' }}
            onChange={handleBulkDeleteFileChange}
          />
          <Button
            variant="outlined"
            color="secondary"
            startIcon={isArabic ? null : <UploadFile />}
            endIcon={isArabic ? <UploadFile /> : null}
            onClick={handleBulkUploadClick}
            disabled={bulkUploadLoading}
            sx={{ whiteSpace: 'nowrap', flex: { xs: '1 1 100%', sm: '0 0 auto' } }}
          >
            {bulkUploadLoading ? tr('Uploading...', '???? ?????...') : tr('Bulk Upload Users', '??? ????? ??????????')}
          </Button>
          <Button
            variant="outlined"
            color="error"
            startIcon={isArabic ? null : <DeleteSweep />}
            endIcon={isArabic ? <DeleteSweep /> : null}
            onClick={handleBulkDeleteClick}
            disabled={bulkDeleteLoading}
            sx={{ whiteSpace: 'nowrap', flex: { xs: '1 1 100%', sm: '0 0 auto' } }}
          >
            {bulkDeleteLoading ? tr('Deleting...', '???? ?????...') : tr('Bulk Delete Users', '??? ????? ??????????')}
          </Button>
          <Button
            variant="outlined"
            color="primary"
            startIcon={isArabic ? null : <Download />}
            endIcon={isArabic ? <Download /> : null}
            onClick={handleExportUsers}
            disabled={exportLoading}
            sx={{ whiteSpace: 'nowrap', flex: { xs: '1 1 100%', sm: '0 0 auto' } }}
          >
            {exportLoading ? tr('Exporting...', 'Exporting...') : tr('Export Users XLSX', 'Export Users XLSX')}
          </Button>
          <Button
            variant="outlined"
            color="success"
            startIcon={isArabic ? null : <Add />}
            endIcon={isArabic ? <Add /> : null}
            onClick={handleOpenBranchDialog}
            sx={{ whiteSpace: 'nowrap', flex: { xs: '1 1 100%', sm: '0 0 auto' } }}
          >
            {tr('Add Branch', 'إضافة فرع')}
          </Button>
          <Button
            variant="contained"
            startIcon={isArabic ? null : <Add />}
            endIcon={isArabic ? <Add /> : null}
            onClick={() => handleOpenDialog()}
            sx={{ whiteSpace: 'nowrap', flex: { xs: '1 1 100%', sm: '0 0 auto' } }}
          >
            {tr('Create User', '????? ??????')}
          </Button>
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', width: '100%' }}>
          {tr(
            'Bulk upload columns: HR ID, Name, Title, Department, Email, Branch_Code. Bulk delete columns: HR ID or Email.',
            'أعمدة الرفع الجماعي: الرقم الوظيفي، الاسم، المسمى الوظيفي، الإدارة، البريد الإلكتروني، كود الفرع. أعمدة الحذف الجماعي: الرقم الوظيفي أو البريد الإلكتروني.'
          )}
        </Typography>
        <Box
          sx={{
            width: '100%',
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(170px, 1fr))', lg: 'repeat(6, minmax(140px, 1fr))' },
            gap: 1,
            mt: 0.5,
          }}
        >
          {filterDefinitions.map((filterDef) => {
            const selected = userFilters[filterDef.key] || [];
            return (
              <Button
                key={filterDef.key}
                variant={selected.length ? 'contained' : 'outlined'}
                color={selected.length ? 'primary' : 'inherit'}
                onClick={(event) => handleOpenFilterPopover(event, filterDef.key)}
                sx={{
                  justifyContent: 'space-between',
                  textTransform: 'none',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                <span>{filterDef.label}</span>
                <span>{selected.length ? `(${selected.length})` : ''}</span>
              </Button>
            );
          })}
        </Box>
        <Box sx={{ width: '100%', display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          <Button
            variant="outlined"
            color="primary"
            onClick={handleSelectFiltered}
            sx={{ whiteSpace: 'nowrap' }}
            disabled={!filteredDeletableEmails.length}
          >
            {tr('Select Filtered', 'تحديد نتائج البحث')}
          </Button>
          <Button
            variant="outlined"
            color="inherit"
            onClick={handleResetAllFilters}
            sx={{ whiteSpace: 'nowrap' }}
            disabled={!hasActiveFilters}
          >
            {tr('Reset Filters', 'إعادة ضبط الفلاتر')}
          </Button>
          {selectedCount > 0 && (
            <>
              <Typography variant="body2" color="text.secondary" sx={{ px: 0.5 }}>
                {`${tr('Selected', 'محدد')}: ${selectedCount}`}
              </Typography>
              <Button
                variant="outlined"
                color="inherit"
                onClick={handleClearSelection}
                sx={{ whiteSpace: 'nowrap' }}
              >
                {tr('Clear Selection', 'إلغاء التحديد')}
              </Button>
              <Button
                variant="outlined"
                color="error"
                onClick={handleDeleteSelectedUsers}
                disabled={bulkDeleteSelectedLoading}
                sx={{ whiteSpace: 'nowrap' }}
              >
                {bulkDeleteSelectedLoading
                  ? tr('Deleting...', 'جارٍ الحذف...')
                  : `${tr('Delete Selected Users', 'حذف المستخدمين المحددين')} (${selectedCount})`}
              </Button>
            </>
          )}
        </Box>
      </Box>

      {alert.show && (
        <Alert
          severity={alert.severity}
          sx={{ mb: 2 }}
          onClose={() => setAlert({ ...alert, show: false })}
        >
          {alert.message}
        </Alert>
      )}

      <Popover
        open={Boolean(activeFilterKey && filterAnchorEl)}
        anchorEl={filterAnchorEl}
        onClose={handleCloseFilterPopover}
        anchorOrigin={{ vertical: 'bottom', horizontal: isArabic ? 'right' : 'left' }}
        transformOrigin={{ vertical: 'top', horizontal: isArabic ? 'right' : 'left' }}
      >
        <Box sx={{ p: 1.5, width: 320, maxWidth: '90vw' }}>
          <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 700 }}>
            {activeFilterKey ? filterDefinitions.find((item) => item.key === activeFilterKey)?.label : tr('Filters', 'الفلاتر')}
          </Typography>
          <TextField
            size="small"
            fullWidth
            placeholder={tr('Search in list', 'بحث داخل القائمة')}
            value={activeFilterKey ? filterSearchText[activeFilterKey] || '' : ''}
            onChange={(event) => activeFilterKey && handleFilterSearchChange(activeFilterKey, event.target.value)}
          />
          <Box sx={{ mt: 1, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Button
              size="small"
              variant="outlined"
              onClick={handleSelectAllShownOptions}
              disabled={filterOptionsLoading || !activeFilterOptions.length}
            >
              {tr('Select all shown', 'تحديد كل المعروض')}
            </Button>
            <Button
              size="small"
              variant="text"
              onClick={handleClearActiveFilter}
              disabled={!activeFilterKey || !(userFilters[activeFilterKey] || []).length}
            >
              {tr('Clear filter', 'إلغاء الفلتر')}
            </Button>
          </Box>
          <Divider sx={{ my: 1 }} />
          <List dense sx={{ maxHeight: 260, overflowY: 'auto', pt: 0 }}>
            {filterOptionsLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
                <CircularProgress size={24} />
              </Box>
            ) : activeFilterOptions.length ? (
              activeFilterOptions.map((optionValue) => (
                <ListItemButton
                  key={`${activeFilterKey}-${optionValue}`}
                  dense
                  onClick={() => activeFilterKey && handleToggleFilterValue(activeFilterKey, optionValue)}
                  sx={{ px: 1 }}
                >
                  <Checkbox
                    size="small"
                    checked={Boolean(activeFilterKey && (userFilters[activeFilterKey] || []).includes(optionValue))}
                    sx={{ mr: 1 }}
                  />
                  <ListItemText
                    primary={activeFilterKey ? renderFilterOptionLabel(activeFilterKey, optionValue) : optionValue}
                    primaryTypographyProps={{ sx: { fontSize: 14 } }}
                  />
                </ListItemButton>
              ))
            ) : (
              <Typography variant="body2" color="text.secondary" sx={{ px: 1, py: 1.5 }}>
                {tr('No options found', 'لا توجد خيارات')}
              </Typography>
            )}
          </List>
        </Box>
      </Popover>

      {usersTable}

      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>{editingUser ? tr('Edit User', '????? ??????') : tr('Create New User', '????? ?????? ????')}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            {textFieldConfig.map((field) => {
              if (field.name === 'title' && !hasOptionalTitle) {
                return (
                  <Grid
                    item
                    xs={12}
                    sm={field.fullWidth ? 12 : 6}
                    key={field.name}
                    sx={{ minWidth: { xs: '100%', sm: 240 }, flex: '1 1 240px' }}
                  >
                    <TextField
                      select
                      fullWidth
                      label={fieldLabels[field.name]}
                      value={formData[field.name]}
                      onChange={(e) => handleFieldChange(field.name, e.target.value)}
                      margin="normal"
                      required={field.required}
                      SelectProps={{
                        displayEmpty: true,
                        renderValue: (selected) =>
                          selected || tr('Select title', 'اختر المسمى الوظيفي'),
                      }}
                      InputLabelProps={{ shrink: true }}
                    >
                      <MenuItem value="">{tr('Select title', 'اختر المسمى الوظيفي')}</MenuItem>
                      {availableTitleOptions.map((option) => (
                        <MenuItem key={option.value} value={option.value}>
                          {option.label}
                        </MenuItem>
                      ))}
                    </TextField>
                  </Grid>
                );
              }

              return (
                <Grid item xs={12} sm={field.fullWidth ? 12 : 6} key={field.name}>
                  <TextField
                    fullWidth
                    label={fieldLabels[field.name]}
                    type={field.type || 'text'}
                    value={formData[field.name]}
                    onChange={(e) => handleFieldChange(field.name, e.target.value)}
                    margin="normal"
                    required={field.name === 'title' ? !hasOptionalTitle : field.required}
                  />
                </Grid>
              );
            })}

            {isBranchRequired(formData.department) ? (
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  select
                  label={tr('Branch', '?????')}
                  value={formData.branch_code}
                  onChange={(e) => handleFieldChange('branch_code', e.target.value)}
                  margin="normal"
                  required
                  disabled={branchesLoading || branches.length === 0}
                  helperText={
                    branchesLoading
                      ? tr('Loading branches...', '???? ????? ??????...')
                      : branches.length
                      ? tr('Pick a branch; its region/area/division/sub-department are derived automatically.', '???? ????? ????? ????? ???????/???????/??????/????? ?????? ????????.')
                      : tr('No branches found. Upload branches first.', '?? ???? ????. ???? ??? ?????? ?????? ?????.')
                  }
                >
                  {branches.map((branch) => (
                    <MenuItem key={branch.branch_code} value={branch.branch_code}>
                      {branch.branch_name} ({branch.branch_code}) - {branch.area}, {branch.region}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
            ) : (
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label={tr('Branch', '?????')}
                  value={tr('Not required for Admin/HR', '??? ??????? ????/??????')}
                  margin="normal"
                  InputProps={{ readOnly: true }}
                />
              </Grid>
            )}

            {formData.branch_code && isBranchRequired(formData.department) ? (
              <Grid item xs={12}>
                <Alert severity="info" sx={{ mt: 1 }}>
                  {tr('Region', 'الإقليم')}: <strong>{selectedBranchMeta?.region || '-'}</strong> | {tr('Area', 'المنطقة')}:{' '}
                  <strong>{selectedBranchMeta?.area || '-'}</strong> | {tr('Division', 'القطاع')}:{' '}
                  <strong>{selectedBranchMeta?.division || '-'}</strong> | {tr('Sub Department', 'الإدارة الفرعية')}:{' '}
                  <strong>{selectedBranchMeta?.sub_department || '-'}</strong>
                </Alert>
              </Grid>
            ) : null}

            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                select
                label={tr('Department / Role', '????? / ?????')}
                value={formData.department}
                onChange={(e) => handleFieldChange('department', e.target.value)}
                margin="normal"
                required
              >
                {roleOptions.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
          </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleCloseDialog}>{tr('Cancel', '?????')}</Button>
        <Button onClick={handleSaveUser} variant="contained">
          {editingUser ? tr('Update', '?????') : tr('Create', '?????')}
        </Button>
      </DialogActions>
    </Dialog>

      <Dialog open={openBranchDialog} onClose={handleCloseBranchDialog} maxWidth="md" fullWidth>
        <DialogTitle>{tr('Add Branch', 'إضافة فرع')}</DialogTitle>
        <DialogContent>
          <Box
            sx={{
              mt: 2,
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' },
              gap: 2,
            }}
          >
            <TextField
              fullWidth
              label={branchFieldLabels.branch_code}
              value={branchFormData.branch_code}
              onChange={(e) => handleBranchFieldChange('branch_code', e.target.value)}
              required
            />
            <TextField
              fullWidth
              label={branchFieldLabels.branch_name}
              value={branchFormData.branch_name}
              onChange={(e) => handleBranchFieldChange('branch_name', e.target.value)}
              required
            />
            <Autocomplete
              freeSolo
              options={branchRegionOptions}
              value={branchFormData.branch_region}
              onChange={(_, value) => handleBranchFieldChange('branch_region', value || '')}
              onInputChange={(_, value) => handleBranchFieldChange('branch_region', value)}
              renderInput={(params) => (
                <TextField
                  {...params}
                  fullWidth
                  label={branchFieldLabels.branch_region}
                  helperText={tr(
                    'Choose an existing region or type a new one.',
                    'اختر إقليماً موجوداً أو اكتب إقليماً جديداً.'
                  )}
                  required
                />
              )}
            />
            <Autocomplete
              freeSolo
              options={branchAreaOptions}
              value={branchFormData.branch_area}
              onChange={(_, value) => handleBranchFieldChange('branch_area', value || '')}
              onInputChange={(_, value) => handleBranchFieldChange('branch_area', value)}
              renderInput={(params) => (
                <TextField
                  {...params}
                  fullWidth
                  label={branchFieldLabels.branch_area}
                  helperText={tr(
                    'Areas narrow down based on the selected region.',
                    'تتحدد المناطق بناءً على الإقليم المختار.'
                  )}
                  required
                />
              )}
            />
            <TextField
              fullWidth
              select
              label={branchFieldLabels.branch_division}
              value={branchFormData.branch_division}
              onChange={(e) => handleBranchFieldChange('branch_division', e.target.value)}
              required
            >
              <MenuItem value="">{tr('Select division', 'اختر القطاع')}</MenuItem>
              {branchDivisionOptions.map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </TextField>
            <Autocomplete
              freeSolo
              options={branchSubDepartmentOptions}
              value={branchFormData.branch_sub_department}
              onChange={(_, value) => handleBranchFieldChange('branch_sub_department', value || '')}
              onInputChange={(_, value) => handleBranchFieldChange('branch_sub_department', value)}
              renderInput={(params) => (
                <TextField
                  {...params}
                  fullWidth
                  label={branchFieldLabels.branch_sub_department}
                  helperText={tr(
                    'Pick a known sub department or type a new one.',
                    'اختر إدارة فرعية معروفة أو اكتب إدارة جديدة.'
                  )}
                  required
                />
              )}
            />
            <Alert severity="info" sx={{ gridColumn: '1 / -1', mt: 1 }}>
              {tr(
                'New branches become available in the Create User branch picker right after saving.',
                'سيظهر الفرع الجديد مباشرة في قائمة اختيار الفرع بعد الحفظ.'
              )}
            </Alert>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseBranchDialog} disabled={branchSaveLoading}>
            {tr('Cancel', '?????')}
          </Button>
          <Button onClick={handleSaveBranch} variant="contained" disabled={branchSaveLoading}>
            {branchSaveLoading ? tr('Saving...', 'جارٍ الحفظ...') : tr('Save Branch', 'حفظ الفرع')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={bulkSummaryOpen} onClose={handleCloseBulkSummary} maxWidth="md" fullWidth>
        <DialogTitle>{tr('Bulk Upload Summary', '???? ????? ???????')}</DialogTitle>
        <DialogContent dividers>
          {bulkResult ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <Grid container spacing={2}>
                {[
                  { label: tr('Updated', '?? ???????'), value: bulkResult.updated },
                  { label: tr('Created', '?? ???????'), value: bulkResult.created },
                  { label: tr('Unadded', '??? ??????'), value: bulkResult.unadded_count },
                ].map((item) => (
                  <Grid item xs={12} sm={4} key={item.label}>
                    <Box
                      sx={{
                        border: '1px solid',
                        borderColor: 'grey.200',
                        borderRadius: 2,
                        p: 2,
                        textAlign: 'center',
                        bgcolor: 'grey.50',
                      }}
                    >
                      <Typography variant="subtitle2" color="text.secondary">
                        {item.label}
                      </Typography>
                      <Typography variant="h5" fontWeight="bold">
                        {item.value ?? 0}
                      </Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>

              <Box sx={{ direction: isArabic ? 'rtl' : 'ltr' }}>
                <Typography variant="h6" gutterBottom>
                  {tr('Unadded Users', '?????????? ??? ????????')}
                </Typography>
                {bulkResult.unadded_users?.length ? (
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>{tr('HR ID', 'الرقم الوظيفي')}</TableCell>
                        <TableCell>{tr('Email', 'البريد الإلكتروني')}</TableCell>
                        <TableCell>{tr('Reason', '?????')}</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {bulkResult.unadded_users.map((user, idx) => (
                        <TableRow key={`${user.hr_id}-${user.email}-${idx}`}>
                          <TableCell>{user.hr_id || '-'}</TableCell>
                          <TableCell>{user.email || '-'}</TableCell>
                          <TableCell>{user.reason || '-'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <Typography color="text.secondary">{tr('All users were processed successfully.', '??? ?????? ?? ?????????? ?????.')}</Typography>
                )}
              </Box>
            </Box>
          ) : (
            <Typography color="text.secondary">{tr('No results to display.', '?? ???? ????? ?????.')}</Typography>
          )}
        </DialogContent>
        <DialogActions>
          {bulkResult?.unadded_users?.length ? (
            <Button onClick={handleExportUnadded}>{tr('Download Unadded CSV', '????? CSV ???? ????????')}</Button>
          ) : null}
          <Button onClick={handleCloseBulkSummary}>{tr('Close', '?????')}</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={viewDialogOpen} onClose={handleCloseViewDialog} maxWidth="sm" fullWidth>
        <DialogTitle>{tr('User Details', '?????? ????????')}</DialogTitle>
        <DialogContent dividers>
          {viewLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress size={32} />
            </Box>
          ) : viewingUser ? (
            <Grid container spacing={2}>
              {userDetailFields.map((field) => {
                const rawValue = viewingUser[field.key];
                return (
                  <Grid item xs={12} sm={6} key={field.key}>
                    <Box
                      sx={{
                        border: '1px solid',
                        borderColor: 'grey.200',
                        borderRadius: 1,
                        p: 2,
                        bgcolor: 'grey.50',
                        minHeight: 96,
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                      }}
                    >
                      <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                        {field.label}
                      </Typography>
                      <Typography variant="body1" fontWeight={600} sx={{ mt: 1 }}>
                        {rawValue || '-'}
                      </Typography>
                    </Box>
                  </Grid>
                );
              })}
            </Grid>
          ) : (
            <Typography color="text.secondary">{tr('No data available.', '?? ???? ?????? ?????.')}</Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseViewDialog}>{tr('Close', '?????')}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default UserManagement;
