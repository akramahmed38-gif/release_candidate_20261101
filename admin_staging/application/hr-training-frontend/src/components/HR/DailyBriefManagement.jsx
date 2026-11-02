import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  MenuItem,
  Snackbar,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  ArrowBack,
  CreateNewFolder,
  Delete,
  Edit,
  Folder,
  FolderOpen,
  NavigateNext,
  OpenInNew,
  PictureAsPdf,
  PlayCircleOutline,
  Refresh,
  Search,
  Slideshow,
  TableChart,
  UploadFile,
} from '@mui/icons-material';
import { authService, dailyBriefLibraryService as dailyBriefService } from '../../services/auth';
import { useLanguage } from '../../context/LanguageContext';
import LibraryItemCard, { libraryCardGridSx } from './LibraryItemCard';

const emptyLibraryState = {
  currentPath: '',
  breadcrumb: [{ name: 'Script Book', path: '' }],
  folders: [],
  files: [],
  counts: {
    total_materials: 0,
    folders: 0,
    videos: 0,
    pdfs: 0,
    powerpoints: 0,
    excels: 0,
    skipped_files: 0,
  },
  skippedCount: 0,
  message: '',
};

const emptyGlobalSearchState = {
  loading: false,
  files: [],
  error: '',
  message: '',
};

const materialTypeMeta = {
  video: {
    color: '#1f63be',
    lightColor: 'rgba(31, 99, 190, 0.12)',
    badgeColor: '#dce9ff',
    Icon: PlayCircleOutline,
  },
  pdf: {
    color: '#d32f2f',
    lightColor: 'rgba(211, 47, 47, 0.11)',
    badgeColor: '#ffe4e4',
    Icon: PictureAsPdf,
  },
  powerpoint: {
    color: '#ef6c00',
    lightColor: 'rgba(239, 108, 0, 0.12)',
    badgeColor: '#ffe6cc',
    Icon: Slideshow,
  },
  excel: {
    color: '#2e7d32',
    lightColor: 'rgba(46, 125, 50, 0.12)',
    badgeColor: '#e0f2e4',
    Icon: TableChart,
  },
};

const folderMeta = {
  color: '#0b4fa8',
  lightColor: 'rgba(11, 79, 168, 0.12)',
};

const unifiedMaterialCardSx = {
  height: '100%',
  display: 'flex',
  flexDirection: 'column',
  bgcolor: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: 3.5,
  boxShadow: '0 8px 22px rgba(15, 42, 79, 0.07)',
  cursor: 'pointer',
  transition: 'transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease',
  '&:hover': {
    transform: 'translateY(-3px)',
    borderColor: 'rgba(11, 79, 168, 0.24)',
    boxShadow: '0 16px 30px rgba(15, 42, 79, 0.13)',
  },
  '&:focus-visible': {
    outline: '3px solid rgba(11, 79, 168, 0.28)',
    outlineOffset: 2,
  },
};

const materialCardContentSx = {
  display: 'flex',
  flexDirection: 'column',
  height: '100%',
  p: 2.5,
  gap: 1.5,
};

const materialActionButtonSx = {
  minHeight: 40,
  borderRadius: 2.5,
  bgcolor: '#0b4fa8',
  boxShadow: 'none',
  fontWeight: 700,
  '&:hover': {
    bgcolor: '#083d80',
    boxShadow: '0 6px 14px rgba(11, 79, 168, 0.2)',
  },
};

const metadataLabelSx = {
  display: 'block',
  color: '#6b7280',
  fontSize: '0.78rem',
  fontWeight: 600,
  lineHeight: 1.35,
};

const metadataValueSx = {
  mt: 0.35,
  color: '#1f2937',
  fontSize: '0.9rem',
  fontWeight: 600,
  lineHeight: 1.4,
};

const actionClusterSx = {
  display: 'flex',
  alignItems: 'center',
  gap: 0.25,
  p: 0.25,
  border: '1px solid #e5e7eb',
  borderRadius: 2.5,
  bgcolor: '#f9fafb',
  '& .MuiIconButton-root': {
    width: 32,
    height: 32,
    borderRadius: 2,
    color: '#4b5563',
    '&:hover': { bgcolor: '#e5e7eb' },
  },
  '& .MuiIconButton-colorError': {
    color: '#d32f2f',
    '&:hover': { bgcolor: 'rgba(211, 47, 47, 0.10)' },
  },
};

const isDownloadOnlyMaterialType = (fileType) => fileType === 'powerpoint' || fileType === 'excel';

const getMaterialTypeLabel = (fileType, tr) => {
  if (fileType === 'video') return tr('Video', 'فيديو');
  if (fileType === 'pdf') return tr('PDF', 'PDF');
  if (fileType === 'powerpoint') return tr('PowerPoint', 'PowerPoint');
  if (fileType === 'excel') return tr('Excel', 'Excel');
  return fileType || tr('File', 'ملف');
};

const getFileFolderPath = (filePath) => {
  const segments = String(filePath || '')
    .split('/')
    .filter(Boolean);
  return segments.slice(0, -1).join('/');
};

const formatDateTime = (value, locale) => {
  if (!value) {
    return '-';
  }

  const parsedValue = new Date(value);
  if (Number.isNaN(parsedValue.getTime())) {
    return '-';
  }

  return parsedValue.toLocaleString(locale, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const triggerObjectUrlOpen = (objectUrl, fileName, isDownload) => {
  const link = document.createElement('a');
  link.href = objectUrl;
  if (isDownload) {
    link.setAttribute('download', fileName);
  } else {
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
  }
  document.body.appendChild(link);
  link.click();
  link.remove();
};

const openLoadingPreviewWindow = (title, message) => {
  const previewWindow = window.open('', '_blank');
  if (!previewWindow) {
    return null;
  }

  previewWindow.document.title = title;
  previewWindow.document.body.innerHTML = `
    <div style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f4f8ff;color:#0b1f4d;font-family:Arial,sans-serif;padding:24px;">
      <div style="max-width:420px;text-align:center;">
        <div style="width:52px;height:52px;border-radius:16px;background:rgba(11,79,168,0.12);display:flex;align-items:center;justify-content:center;margin:0 auto 16px;font-size:24px;color:#0b4fa8;">...</div>
        <h2 style="margin:0 0 8px;font-size:22px;">${title}</h2>
        <p style="margin:0;font-size:15px;line-height:1.6;color:#526480;">${message}</p>
      </div>
    </div>
  `;

  return previewWindow;
};

const buildObjectUrlAndOpen = ({ blob, fileName, mimeType, isDownload, previewWindow }) => {
  const sourceBlob = blob instanceof Blob ? blob : new Blob([blob], { type: mimeType });
  const resolvedBlob =
    sourceBlob.type || !mimeType ? sourceBlob : sourceBlob.slice(0, sourceBlob.size, mimeType);
  const objectUrl = window.URL.createObjectURL(resolvedBlob);

  if (isDownload) {
    if (previewWindow && !previewWindow.closed) {
      previewWindow.close();
    }
    triggerObjectUrlOpen(objectUrl, fileName, true);
  } else if (previewWindow && !previewWindow.closed) {
    previewWindow.location.replace(objectUrl);
  } else {
    triggerObjectUrlOpen(objectUrl, fileName, false);
  }

  setTimeout(() => window.URL.revokeObjectURL(objectUrl), 120000);
};

const DailyBriefManagement = () => {
  const { t, isArabic } = useLanguage();
  const navigate = useNavigate();
  const locale = isArabic ? 'ar-EG' : 'en-US';
  const currentUser = authService.getCurrentUser();
  const normalizedRole = String(currentUser?.role || currentUser?.department || '').toLowerCase();
  const isAdmin = ['admin', 'auditor'].includes(normalizedRole);
  const uploadInputRef = useRef(null);

  const tr = (englishText, arabicText) => (isArabic ? arabicText : englishText);

  const [libraryState, setLibraryState] = useState(emptyLibraryState);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [globalSearchState, setGlobalSearchState] = useState(emptyGlobalSearchState);
  const [errorMessage, setErrorMessage] = useState('');
  const [toast, setToast] = useState({ open: false, severity: 'success', message: '' });
  const [dialogState, setDialogState] = useState({
    type: '',
    title: '',
    label: '',
    confirmLabel: '',
    targetPath: '',
    value: '',
  });
  const [dialogLoading, setDialogLoading] = useState(false);
  const [pendingKey, setPendingKey] = useState('');

  const showToast = (message, severity = 'success') => {
    setToast({ open: true, severity, message });
  };

  const handleOpenVideoFile = (file) => {
    navigate(`/daily-brief/player?path=${encodeURIComponent(file.path || '')}`, {
      state: {
        fileName: file.name,
      },
    });
  };

  const loadLibrary = async (targetPath = libraryState.currentPath, showLoader = true) => {
    if (showLoader) {
      setLoading(true);
    }
    setErrorMessage('');

    try {
      const response = await dailyBriefService.getLibraryMaterials(targetPath);
      setLibraryState({
        currentPath: response.data.currentPath || '',
        breadcrumb: response.data.breadcrumb || emptyLibraryState.breadcrumb,
        folders: response.data.folders || [],
        files: response.data.files || [],
        counts: response.data.counts || emptyLibraryState.counts,
        skippedCount: response.data.skippedCount || 0,
        message: response.data.message || '',
      });
    } catch (error) {
      setLibraryState((previousState) => ({
        ...emptyLibraryState,
        currentPath: targetPath || '',
      }));
      setErrorMessage(
        error.response?.data?.detail ||
          error.response?.data?.message ||
          tr('Failed to load the training material folder.', 'تعذر تحميل مجلد المواد التدريبية.')
      );
    } finally {
      if (showLoader) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    loadLibrary('', true);
  }, []);

  const normalizedSearch = searchTerm.trim().toLowerCase();
  const isGlobalSearch = normalizedSearch.length > 0;

  useEffect(() => {
    if (!isGlobalSearch) {
      setGlobalSearchState(emptyGlobalSearchState);
      return undefined;
    }

    let isCurrent = true;
    const searchTimer = window.setTimeout(async () => {
      setGlobalSearchState((previousState) => ({
        ...previousState,
        loading: true,
        error: '',
      }));

      try {
        const response = await dailyBriefService.searchLibraryMaterials(searchTerm.trim(), typeFilter);
        if (!isCurrent) {
          return;
        }

        setGlobalSearchState({
          loading: false,
          files: response.data?.files || [],
          error: '',
          message: response.data?.message || '',
        });
      } catch (error) {
        if (!isCurrent) {
          return;
        }

        setGlobalSearchState({
          loading: false,
          files: [],
          message: '',
          error:
            error.response?.data?.detail ||
            error.response?.data?.message ||
            tr('Failed to search all training materials.', 'تعذر البحث في كافة المواد التدريببية.'),
        });
      }
    }, 220);

    return () => {
      isCurrent = false;
      window.clearTimeout(searchTimer);
    };
  }, [isArabic, isGlobalSearch, searchTerm, typeFilter]);

  const currentPathLabel = useMemo(() => {
    if (!libraryState.currentPath) {
      return tr('Script Book', 'كتاب السكربتات');
    }
    return `${tr('Script Book', 'كتاب السكربتات')} / ${libraryState.currentPath}`;
  }, [libraryState.currentPath, isArabic]);

  const parentPath = useMemo(() => {
    if (!libraryState.currentPath) {
      return '';
    }
    const segments = libraryState.currentPath.split('/').filter(Boolean);
    return segments.slice(0, -1).join('/');
  }, [libraryState.currentPath]);

  const materialsRootLabel = tr('Script Book', 'كتاب السكربتات');
  const displayPathLabel = isArabic ? currentPathLabel : currentPathLabel.replace(/^Material\b/, 'Materials');
  const displayBreadcrumb = useMemo(
    () =>
      libraryState.breadcrumb.map((crumb, index) =>
        index === 0
          ? {
              ...crumb,
              name: materialsRootLabel,
            }
          : crumb
      ),
    [libraryState.breadcrumb, materialsRootLabel]
  );
  // Daily Brief is intentionally a flat, files-only library.
  const visibleFolders = useMemo(() => [], []);

  const visibleFiles = useMemo(() => {
    if (isGlobalSearch) {
      return globalSearchState.files;
    }

    return libraryState.files.filter((file) => {
      const matchesType = typeFilter === 'all' || file.file_type === typeFilter;
      return matchesType;
    });
  }, [globalSearchState.files, isGlobalSearch, libraryState.files, typeFilter]);

  const totalVisibleItems = visibleFiles.length;
  const totalCurrentItems = libraryState.files.length;
  const searchSummary = isGlobalSearch
    ? globalSearchState.loading
      ? tr('Searching all material files...', 'جارٍ البحث في كافة ملفات المواد...')
      : tr(
          `Showing ${visibleFiles.length} matching files across all folders`,
          `يتم عرض ${visibleFiles.length} ملف مطابق عبر كافة المجلدات`
        )
    : tr(
        `Showing ${totalVisibleItems} of ${totalCurrentItems} files`,
        `يتم عرض ${totalVisibleItems} من أصل ${totalCurrentItems} ملف`
      );

  const summaryCards = [
    {
      key: 'total',
      title: tr('Total Materials', 'إجمالي المواد'),
      value: libraryState.counts.total_materials,
      subtitle: tr('Supported files in this folder tree', 'الملفات المدعومة داخل هذا المسار'),
      color: '#0b4fa8',
      lightColor: 'rgba(11, 79, 168, 0.12)',
      Icon: FolderOpen,
    },
    {
      key: 'folders',
      title: tr('Folders', 'المجلدات'),
      value: libraryState.counts.folders,
      subtitle: tr('Subfolders in this view', 'المجلدات الفرعية في هذا العرض'),
      color: '#375a7f',
      lightColor: 'rgba(55, 90, 127, 0.12)',
      Icon: Folder,
    },
    {
      key: 'videos',
      title: tr('Videos', 'فيديوهات'),
      value: libraryState.counts.videos,
      subtitle: tr('Training video files', 'ملفات الفيديو التدريبية'),
      color: '#1f63be',
      lightColor: 'rgba(31, 99, 190, 0.12)',
      Icon: PlayCircleOutline,
    },
    {
      key: 'pdfs',
      title: tr('PDFs', 'ملفات PDF'),
      value: libraryState.counts.pdfs,
      subtitle: tr('PDF training documents', 'مستندات PDF التدريبية'),
      color: '#d32f2f',
      lightColor: 'rgba(211, 47, 47, 0.11)',
      Icon: PictureAsPdf,
    },
    {
      key: 'powerpoints',
      title: tr('PowerPoint', 'PowerPoint'),
      value: libraryState.counts.powerpoints,
      subtitle: tr('Presentation slide decks', 'عروض الشرائح التدريبية'),
      color: '#ef6c00',
      lightColor: 'rgba(239, 108, 0, 0.12)',
      Icon: Slideshow,
    },
    {
      key: 'excels',
      title: tr('Excel', 'Excel'),
      value: libraryState.counts.excels,
      subtitle: tr('Spreadsheet training files', 'ملفات جداول البيانات التدريبية'),
      color: '#2e7d32',
      lightColor: 'rgba(46, 125, 50, 0.12)',
      Icon: TableChart,
    },
  ];

  const typeOptions = [
    { value: 'all', label: tr('All Types', 'كل الأنواع') },
    { value: 'video', label: tr('Videos', 'فيديوهات') },
    { value: 'pdf', label: tr('PDFs', 'ملفات PDF') },
    { value: 'powerpoint', label: tr('PowerPoint', 'PowerPoint') },
    { value: 'excel', label: tr('Excel', 'Excel') },
  ];

  const openDialog = (config) => {
    setDialogState({
      type: config.type,
      title: config.title,
      label: config.label,
      confirmLabel: config.confirmLabel,
      targetPath: config.targetPath || '',
      value: config.value || '',
    });
  };

  const closeDialog = (force = false) => {
    if (dialogLoading && !force) {
      return;
    }
    setDialogState({
      type: '',
      title: '',
      label: '',
      confirmLabel: '',
      targetPath: '',
      value: '',
    });
  };

  const handleDialogConfirm = async () => {
    if (!dialogState.value.trim()) {
      showToast(tr('Please enter a valid name.', 'يرجى إدخال اسم صالح.'), 'error');
      return;
    }

    setDialogLoading(true);
    try {
      if (dialogState.type === 'new-folder') {
        await dailyBriefService.createLibraryFolder(libraryState.currentPath, dialogState.value.trim());
        showToast(tr('Folder created successfully.', 'تم إنشاء المجلد بنجاح.'));
      } else if (dialogState.type === 'rename-folder') {
        await dailyBriefService.renameLibraryFolder(dialogState.targetPath, dialogState.value.trim());
        showToast(tr('Folder renamed successfully.', 'تمت إعادة تسمية المجلد بنجاح.'));
      } else if (dialogState.type === 'rename-file') {
        await dailyBriefService.renameLibraryFile(dialogState.targetPath, dialogState.value.trim());
        showToast(tr('File renamed successfully.', 'تمت إعادة تسمية الملف بنجاح.'));
      }

      closeDialog(true);
      await loadLibrary(libraryState.currentPath, true);
    } catch (error) {
      showToast(
        error.response?.data?.detail ||
          error.response?.data?.message ||
          tr('The requested action could not be completed.', 'تعذر إكمال العملية المطلوبة.'),
        'error'
      );
    } finally {
      setDialogLoading(false);
    }
  };

  const handleDeleteFolder = async (folderPath, folderName) => {
    const confirmed = window.confirm(
      tr(
        `Delete the folder "${folderName}" and all of its contents?`,
        `هل تريد حذف المجلد "${folderName}" وكل محتوياته؟`
      )
    );
    if (!confirmed) {
      return;
    }

    setPendingKey(`delete-folder:${folderPath}`);
    try {
      await dailyBriefService.deleteLibraryFolder(folderPath);
      showToast(tr('Folder deleted successfully.', 'تم حذف المجلد بنجاح.'));
      await loadLibrary(libraryState.currentPath, true);
    } catch (error) {
      showToast(
        error.response?.data?.detail ||
          error.response?.data?.message ||
          tr('The folder could not be deleted.', 'تعذر حذف المجلد.'),
        'error'
      );
    } finally {
      setPendingKey('');
    }
  };

  const handleDeleteFile = async (filePath, fileName) => {
    const confirmed = window.confirm(
      tr(`Delete the file "${fileName}"?`, `هل تريد حذف الملف "${fileName}"؟`)
    );
    if (!confirmed) {
      return;
    }

    setPendingKey(`delete-file:${filePath}`);
    try {
      await dailyBriefService.deleteLibraryFile(filePath);
      showToast(tr('File deleted successfully.', 'تم حذف الملف بنجاح.'));
      await loadLibrary(libraryState.currentPath, true);
    } catch (error) {
      showToast(
        error.response?.data?.detail ||
          error.response?.data?.message ||
          tr('The file could not be deleted.', 'تعذر حذف الملف.'),
        'error'
      );
    } finally {
      setPendingKey('');
    }
  };

  const handleUploadClick = () => {
    uploadInputRef.current?.click();
  };

  const handleUploadFiles = async (event) => {
    const selectedFiles = Array.from(event.target.files || []);
    event.target.value = '';
    if (!selectedFiles.length) {
      return;
    }

    setPendingKey('upload');
    try {
      const response = await dailyBriefService.uploadLibraryFiles(libraryState.currentPath, selectedFiles);
      const uploadedCount = Number(response.data?.uploaded_count || 0);
      const skippedCount = Number(response.data?.skipped_count || 0);
      const successMessage =
        skippedCount > 0
          ? tr(
              `${uploadedCount} files uploaded, ${skippedCount} skipped.`,
              `تم رفع ${uploadedCount} ملف وتخطي ${skippedCount} ملف.`
            )
          : tr(
              `${uploadedCount} files uploaded successfully.`,
              `تم رفع ${uploadedCount} ملف بنجاح.`
            );
      showToast(successMessage);
      await loadLibrary(libraryState.currentPath, true);
    } catch (error) {
      showToast(
        error.response?.data?.detail ||
          error.response?.data?.message ||
          tr('The selected files could not be uploaded.', 'تعذر رفع الملفات المحددة.'),
        'error'
      );
    } finally {
      setPendingKey('');
    }
  };

  const handleOpenFile = async (file) => {
    const previewWindow =
      isDownloadOnlyMaterialType(file.file_type)
        ? null
        : openLoadingPreviewWindow(
            tr('Opening training material...', 'جارٍ فتح المادة التدريبية...'),
            tr(
              'Preparing your file in a new tab. Please wait a moment.',
              'يتم تجهيز الملف في علامة تبويب جديدة. برجاء الانتظار قليلاً.'
            )
          );

    setPendingKey(`open:${file.path}`);
    try {
      const response = await dailyBriefService.openLibraryMaterial(file.path);
      const mimeType = response.headers['content-type'] || file.mime_type || 'application/octet-stream';
      buildObjectUrlAndOpen({
        blob: response.data,
        fileName: file.name,
        mimeType,
        isDownload: isDownloadOnlyMaterialType(file.file_type),
        previewWindow,
      });
    } catch (error) {
      if (previewWindow && !previewWindow.closed) {
        previewWindow.close();
      }
      showToast(
        error.response?.data?.detail ||
          error.response?.data?.message ||
          tr('The selected file could not be opened.', 'تعذر فتح الملف المحدد.'),
        'error'
      );
    } finally {
      setPendingKey('');
    }
  };

  return (
    <Box sx={{ direction: isArabic ? 'rtl' : 'ltr' }}>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        justifyContent="space-between"
        alignItems={{ xs: 'flex-start', md: 'center' }}
        spacing={1.5}
        sx={{ mb: 2 }}
      >
        <Stack spacing={1}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <FolderOpen color="primary" />
            <Typography
              fontWeight={650}
              sx={{ fontSize: { xs: '2rem', md: '2.2rem' }, lineHeight: 1.15 }}
            >
              {tr('Script Book', 'كتاب السكربتات')}
            </Typography>
          </Stack>
          <Typography
            color="text.secondary"
            sx={{ display: 'none', fontSize: { xs: '1rem', md: '1.05rem' }, lineHeight: 1.45 }}
          >
            {tr(
              'Browse training folders, videos, PDF documents, PowerPoint files, and Excel sheets.',
              'تصفح مجلدات التدريب والفيديوهات وملفات PDF وعروض PowerPoint وملفات Excel.'
            )}
          </Typography>
        </Stack>

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ width: { xs: '100%', md: 'auto' } }}>
          {isAdmin ? (
            <>
              <Button
                variant="outlined"
                startIcon={<CreateNewFolder />}
                onClick={() =>
                  openDialog({
                    type: 'new-folder',
                    title: tr('Create New Folder', 'إنشاء مجلد جديد'),
                    label: tr('Folder name', 'اسم المجلد'),
                    confirmLabel: tr('Create', 'إنشاء'),
                    value: '',
                  })
                }
                sx={{ display: 'none' }}
              >
                {tr('New Folder', 'مجلد جديد')}
              </Button>
              <Button
                variant="outlined"
                startIcon={pendingKey === 'upload' ? <CircularProgress size={16} color="inherit" /> : <UploadFile />}
                onClick={handleUploadClick}
                disabled={pendingKey === 'upload'}
                sx={{ width: { xs: '100%', sm: 'auto' } }}
              >
                {pendingKey === 'upload' ? tr('Uploading...', 'جارٍ الرفع...') : tr('Upload Files', 'رفع ملفات')}
              </Button>
              <input
                ref={uploadInputRef}
                type="file"
                hidden
                multiple
                onChange={handleUploadFiles}
                accept=".mp4,.mov,.avi,.mkv,.webm,.pdf,.ppt,.pptx,.xls,.xlsx"
              />
            </>
          ) : null}

          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={() => loadLibrary(libraryState.currentPath, true)}
            sx={{ width: { xs: '100%', sm: 'auto' } }}
          >
            {tr('Refresh', 'تحديث')}
          </Button>
        </Stack>
      </Stack>

      {errorMessage ? (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={() => loadLibrary('', true)}>
              {tr('Go to Root', 'العودة للجذر')}
            </Button>
          }
        >
          {errorMessage}
        </Alert>
      ) : null}

      {false && libraryState.message && !errorMessage ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          {libraryState.message}
        </Alert>
      ) : null}

      {libraryState.skippedCount > 0 && !errorMessage ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {tr(
            `${libraryState.skippedCount} unsupported files were skipped in this folder view.`,
            `تم تخطي ${libraryState.skippedCount} ملف غير مدعوم في هذا المجلد.`
          )}
        </Alert>
      ) : null}

      {globalSearchState.error && !errorMessage ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {globalSearchState.error}
        </Alert>
      ) : null}

      {isGlobalSearch && !globalSearchState.error ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          {tr(
            'Search results include matching files from every folder in Materials.',
            'نتائج البحث تعرض الملفات المطابقة من جميع مجلدات المواد التدريبية.'
          )}
        </Alert>
      ) : null}

      <Box
        sx={{
          display: 'none',
          gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
          gap: 2,
          alignItems: 'stretch',
          mb: 2,
        }}
      >
        {false && summaryCards.map((card) => {
          const SummaryIcon = card.Icon;
          return (
            <Card key={card.key} sx={{ minHeight: { xs: 134, md: 142 }, display: 'flex' }}>
              <CardContent sx={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 0.45 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography
                    sx={{
                      fontSize: { xs: '0.9rem', md: '0.96rem' },
                      fontWeight: 600,
                      color: 'text.secondary',
                      lineHeight: 1.25,
                    }}
                  >
                    {card.title}
                  </Typography>
                  <Box
                    sx={{
                      width: 42,
                      height: 42,
                      borderRadius: 2.5,
                      display: 'grid',
                      placeItems: 'center',
                      bgcolor: card.lightColor,
                      color: card.color,
                    }}
                  >
                    <SummaryIcon fontSize="small" />
                  </Box>
                </Stack>
                <Typography
                  sx={{
                    mt: 0.45,
                    fontSize: { xs: '1.8rem', sm: '1.85rem', md: '1.95rem' },
                    fontWeight: 650,
                    lineHeight: 1.05,
                    letterSpacing: '-0.012em',
                    fontVariantNumeric: 'tabular-nums',
                    color: '#0b1f4d',
                  }}
                >
                  {card.value}
                </Typography>
                <Typography
                  sx={{
                    fontSize: { xs: '0.82rem', md: '0.88rem' },
                    color: 'text.secondary',
                    lineHeight: 1.35,
                  }}
                >
                  {card.subtitle}
                </Typography>
              </CardContent>
            </Card>
          );
        })}
      </Box>

      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Stack spacing={1.5}>
            <Stack
              direction={{ xs: 'column', md: 'row' }}
              justifyContent="space-between"
              alignItems={{ xs: 'flex-start', md: 'center' }}
              spacing={1}
            >
              <Stack direction="row" alignItems="center" spacing={1} sx={{ flexWrap: 'wrap' }}>
                {libraryState.currentPath ? (
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={<ArrowBack />}
                    onClick={() => loadLibrary(parentPath, true)}
                  >
                    {tr('Back', 'رجوع')}
                  </Button>
                ) : null}

                <Breadcrumbs
                  separator={<NavigateNext fontSize="small" />}
                  aria-label="breadcrumb"
                  sx={{ wordBreak: 'break-word' }}
                >
                  {displayBreadcrumb.map((crumb, index) => {
                    const isLast = index === displayBreadcrumb.length - 1;
                    const label = crumb.name;
                    if (isLast) {
                      return (
                        <Typography key={`${crumb.path || 'root'}-${index}`} color="text.primary" fontWeight={700}>
                          {label}
                        </Typography>
                      );
                    }
                    return (
                      <Button
                        key={`${crumb.path || 'root'}-${index}`}
                        variant="text"
                        sx={{ minWidth: 'auto', px: 0, py: 0, fontWeight: 700 }}
                        onClick={() => loadLibrary(crumb.path || '', true)}
                      >
                        {label}
                      </Button>
                    );
                  })}
                </Breadcrumbs>
              </Stack>

              <Typography
                variant="body2"
                sx={{
                  color: 'text.secondary',
                  direction: 'ltr',
                  unicodeBidi: 'plaintext',
                  wordBreak: 'break-all',
                }}
              >
                {isGlobalSearch ? materialsRootLabel : displayPathLabel}
              </Typography>
            </Stack>

            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: {
                  xs: '1fr',
                  md: 'minmax(0, 2fr) minmax(220px, 320px)',
                },
                gap: 1.5,
              }}
            >
              <TextField
                fullWidth
                size="small"
                label={tr('Search all material files', 'البحث في جميع ملفات المواد التدريبية')}
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search fontSize="small" />
                    </InputAdornment>
                  ),
                }}
              />

              <TextField
                fullWidth
                select
                size="small"
                label={tr('File type', 'نوع الملف')}
                value={typeFilter}
                onChange={(event) => setTypeFilter(event.target.value)}
              >
                {typeOptions.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
            </Box>

            <Typography variant="body2" color="text.secondary">
              {searchSummary}
            </Typography>
          </Stack>
        </CardContent>
      </Card>

      {loading ? (
        <Card>
          <CardContent
            sx={{
              py: 6,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 1.25,
            }}
          >
            <CircularProgress size={34} />
            <Typography color="text.secondary">
              {tr('Loading training material library...', 'جارٍ تحميل مكتبة المواد التدريبية...')}
            </Typography>
          </CardContent>
        </Card>
      ) : (
        <Stack spacing={2} sx={{ pt: { xs: 1, md: 2 } }}>
          {false && !isGlobalSearch ? (
            <Card sx={{ bgcolor: '#fff', border: '1px solid #e5e7eb', borderRadius: 4, boxShadow: '0 10px 28px rgba(15, 42, 79, 0.06)' }}>
            <CardContent sx={{ p: { xs: 2, md: 2.5 } }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2.25 }}>
                <Typography sx={{ fontSize: { xs: '1.18rem', md: '1.28rem' }, fontWeight: 700 }}>
                  {tr('Folders', 'المجلدات')}
                </Typography>
                <Chip
                  label={`${visibleFolders.length}`}
                  size="small"
                  sx={{ minWidth: 30, bgcolor: '#f3f4f6', color: '#374151', fontWeight: 700, borderRadius: 99 }}
                />
              </Stack>

              {visibleFolders.length ? (
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: {
                      xs: '1fr',
                      sm: 'repeat(2, minmax(0, 1fr))',
                      lg: 'repeat(3, minmax(0, 1fr))',
                      xl: 'repeat(4, minmax(0, 1fr))',
                    },
                    gap: { xs: 2, md: 2.5 },
                  }}
                >
                  {visibleFolders.map((folder) => (
                    <Card
                      key={folder.path}
                      sx={unifiedMaterialCardSx}
                      tabIndex={0}
                      aria-label={tr(`Open folder ${folder.name}`, `فتح المجلد ${folder.name}`)}
                      onClick={() => loadLibrary(folder.path, true)}
                      onKeyDown={(event) => {
                        if (event.currentTarget !== event.target || (event.key !== 'Enter' && event.key !== ' ')) return;
                        event.preventDefault();
                        loadLibrary(folder.path, true);
                      }}
                    >
                      <CardContent sx={materialCardContentSx}>
                        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                          <Box
                            sx={{
                              width: 52,
                              height: 52,
                              borderRadius: '50%',
                              display: 'grid',
                              placeItems: 'center',
                              bgcolor: folderMeta.lightColor,
                              color: folderMeta.color,
                            }}
                          >
                            <Folder fontSize="medium" />
                          </Box>

                          {isAdmin ? (
                            <Box sx={actionClusterSx} onClick={(event) => event.stopPropagation()}>
                              <Tooltip title={tr('Rename Folder', 'إعادة تسمية المجلد')}>
                                <span>
                                  <IconButton
                                    size="small"
                                    onClick={() =>
                                      openDialog({
                                        type: 'rename-folder',
                                        title: tr('Rename Folder', 'إعادة تسمية المجلد'),
                                        label: tr('Folder name', 'اسم المجلد'),
                                        confirmLabel: tr('Save', 'حفظ'),
                                        targetPath: folder.path,
                                        value: folder.name,
                                      })
                                    }
                                  >
                                    <Edit fontSize="small" />
                                  </IconButton>
                                </span>
                              </Tooltip>
                              <Tooltip title={tr('Delete Folder', 'حذف المجلد')}>
                                <span>
                                  <IconButton
                                    size="small"
                                    color="error"
                                    disabled={pendingKey === `delete-folder:${folder.path}`}
                                    onClick={() => handleDeleteFolder(folder.path, folder.name)}
                                  >
                                    {pendingKey === `delete-folder:${folder.path}` ? (
                                      <CircularProgress size={16} color="inherit" />
                                    ) : (
                                      <Delete fontSize="small" />
                                    )}
                                  </IconButton>
                                </span>
                              </Tooltip>
                            </Box>
                          ) : null}
                        </Stack>

                        <Typography
                          sx={{
                            fontWeight: 700,
                            fontSize: '1rem',
                            lineHeight: 1.35,
                            color: '#0b1f4d',
                            wordBreak: 'break-word',
                            textAlign: 'start',
                          }}
                        >
                          {folder.name}
                        </Typography>

                        <Box
                          sx={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                            gap: 1,
                            '& .MuiTypography-caption': metadataLabelSx,
                          }}
                        >
                          <Box>
                            <Typography variant="caption" color="text.secondary">
                              {tr('Items inside', 'العناصر بالداخل')}
                            </Typography>
                            <Typography sx={metadataValueSx}>{folder.item_count}</Typography>
                          </Box>
                          <Box>
                            <Typography variant="caption" color="text.secondary">
                              {tr('Subfolders', 'المجلدات الفرعية')}
                            </Typography>
                            <Typography sx={metadataValueSx}>{folder.folder_count}</Typography>
                          </Box>
                          <Box sx={{ gridColumn: '1 / -1' }}>
                            <Typography variant="caption" color="text.secondary">
                              {tr('Last updated', 'آخر تحديث')}
                            </Typography>
                            <Typography sx={metadataValueSx}>
                              {formatDateTime(folder.last_modified, locale)}
                            </Typography>
                          </Box>
                        </Box>

                        <Box sx={{ mt: 'auto', pt: 0.5 }}>
                          <Button
                            fullWidth
                            variant="contained"
                            startIcon={<FolderOpen />}
                            sx={materialActionButtonSx}
                            onClick={(event) => {
                              event.stopPropagation();
                              loadLibrary(folder.path, true);
                            }}
                          >
                            {tr('Open Folder', 'فتح المجلد')}
                          </Button>
                        </Box>
                      </CardContent>
                    </Card>
                  ))}
                </Box>
              ) : (
                <Typography color="text.secondary">
                  {tr('No folders in the current view.', 'لا توجد مجلدات في العرض الحالي.')}
                </Typography>
              )}
            </CardContent>
            </Card>
          ) : null}

          {visibleFiles.length || (isGlobalSearch && globalSearchState.loading) ? (
          <Card sx={{ bgcolor: 'transparent', border: 'none', borderRadius: 0, boxShadow: 'none' }}>
            <CardContent sx={{ p: 0 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2.25 }}>
                <Typography sx={{ fontSize: { xs: '1.18rem', md: '1.28rem' }, fontWeight: 700 }}>
                  {tr('Files', 'الملفات')}
                </Typography>
                <Chip
                  label={`${visibleFiles.length}`}
                  size="small"
                  sx={{ minWidth: 30, bgcolor: '#f3f4f6', color: '#374151', fontWeight: 700, borderRadius: 99 }}
                />
              </Stack>

              {isGlobalSearch && globalSearchState.loading ? (
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
                  <CircularProgress size={18} />
                  <Typography variant="body2" color="text.secondary">
                    {tr('Searching all material files...', 'جارٍ البحث في كافة ملفات المواد...')}
                  </Typography>
                </Stack>
              ) : null}

              {visibleFiles.length ? (
                <Box
                  sx={libraryCardGridSx}
                >
                  {visibleFiles.map((file) => {
                    const meta = materialTypeMeta[file.file_type] || materialTypeMeta.video;
                    const FileIcon = meta.Icon;
                    const isOpening = file.file_type === 'video' ? false : pendingKey === `open:${file.path}`;
                    const actionLabel = isOpening
                      ? tr('Opening...', 'جارٍ الفتح...')
                      : file.file_type === 'video'
                        ? tr('Play Video', 'تشغيل الفيديو')
                        : isDownloadOnlyMaterialType(file.file_type)
                          ? tr('Download', 'تنزيل')
                          : tr('View', 'عرض');
                    return (
                      <LibraryItemCard
                        key={file.path}
                        Icon={FileIcon}
                        iconColor={meta.color}
                        iconBackground={meta.lightColor}
                        name={file.name}

                        ariaLabel={tr(`Open file ${file.name}`, `فتح الملف ${file.name}`)}
                        actionLabel={actionLabel}
                        ActionIcon={file.file_type === 'video' ? PlayCircleOutline : OpenInNew}
                        onOpen={() =>
                          file.file_type === 'video' ? handleOpenVideoFile(file) : handleOpenFile(file)
                        }
                        openPending={isOpening}
                        isAdmin={isAdmin}
                        editLabel={tr('Rename File', 'إعادة تسمية الملف')}
                        deleteLabel={tr('Delete File', 'حذف الملف')}
                        onEdit={() =>
                          openDialog({
                            type: 'rename-file',
                            title: tr('Rename File', 'إعادة تسمية الملف'),
                            label: tr('File name', 'اسم الملف'),
                            confirmLabel: tr('Save', 'حفظ'),
                            targetPath: file.path,
                            value: file.name,
                          })
                        }
                        onDelete={() => handleDeleteFile(file.path, file.name)}
                        deletePending={pendingKey === `delete-file:${file.path}`}
                      />
                    );
                  })}
                  {false && visibleFiles.map((file) => {
                    const meta = materialTypeMeta[file.file_type] || materialTypeMeta.video;
                    const FileIcon = meta.Icon;
                    const isOpening = file.file_type === 'video' ? false : pendingKey === `open:${file.path}`;

                    return (
                      <Card
                        key={file.path}
                        sx={{ ...unifiedMaterialCardSx, minHeight: 292 }}
                        tabIndex={0}
                        aria-label={tr(`Open file ${file.name}`, `فتح الملف ${file.name}`)}
                        onClick={() =>
                          file.file_type === 'video' ? handleOpenVideoFile(file) : handleOpenFile(file)
                        }
                        onKeyDown={(event) => {
                          if (event.currentTarget !== event.target || (event.key !== 'Enter' && event.key !== ' ')) return;
                          event.preventDefault();
                          file.file_type === 'video' ? handleOpenVideoFile(file) : handleOpenFile(file);
                        }}
                      >
                        <CardContent
                          sx={{
                            display: 'flex',
                            flexDirection: 'column',
                            height: '100%',
                            p: { xs: 2, md: 2.25 },
                            gap: 1.5,
                            '&:last-child': { pb: { xs: 2, md: 2.25 } },
                          }}
                        >
                          <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
                            <Box
                              sx={{
                                flex: '0 0 auto',
                                width: 52,
                                height: 52,
                                borderRadius: '50%',
                                display: 'grid',
                                placeItems: 'center',
                                bgcolor: meta.lightColor,
                                color: meta.color,
                              }}
                            >
                              <FileIcon />
                            </Box>

                            {isAdmin ? (
                              <Box sx={actionClusterSx} onClick={(event) => event.stopPropagation()}>
                                  <Tooltip title={tr('Rename File', 'إعادة تسمية الملف')}>
                                    <span>
                                      <IconButton
                                        size="small"
                                        onClick={() =>
                                          openDialog({
                                            type: 'rename-file',
                                            title: tr('Rename File', 'إعادة تسمية الملف'),
                                            label: tr('File name', 'اسم الملف'),
                                            confirmLabel: tr('Save', 'حفظ'),
                                            targetPath: file.path,
                                            value: file.name,
                                          })
                                        }
                                      >
                                        <Edit fontSize="small" />
                                      </IconButton>
                                    </span>
                                  </Tooltip>
                                  <Tooltip title={tr('Delete File', 'حذف الملف')}>
                                    <span>
                                      <IconButton
                                        size="small"
                                        color="error"
                                        disabled={pendingKey === `delete-file:${file.path}`}
                                        onClick={() => handleDeleteFile(file.path, file.name)}
                                      >
                                        {pendingKey === `delete-file:${file.path}` ? (
                                          <CircularProgress size={16} color="inherit" />
                                        ) : (
                                          <Delete fontSize="small" />
                                        )}
                                      </IconButton>
                                    </span>
                                  </Tooltip>
                              </Box>
                            ) : null}
                          </Stack>

                          <Tooltip title={file.name} placement="top-start">
                            <Typography
                            sx={{
                              fontWeight: 700,
                              fontSize: { xs: '0.98rem', md: '1.04rem' },
                              lineHeight: 1.42,
                              color: '#0b1f4d',
                              wordBreak: 'break-word',
                              textAlign: 'start',
                              display: '-webkit-box',
                              WebkitBoxOrient: 'vertical',
                              WebkitLineClamp: 2,
                              overflow: 'hidden',
                            }}
                          >
                            {file.name}
                          </Typography>
                          </Tooltip>

                          <Typography
                            variant="caption"
                            sx={{
                              display: 'none',
                              color: 'text.secondary',
                              direction: 'ltr',
                              unicodeBidi: 'plaintext',
                              wordBreak: 'break-all',
                            }}
                          >
                            {`${materialsRootLabel}${getFileFolderPath(file.path) ? ` / ${getFileFolderPath(file.path)}` : ''}`}
                          </Typography>

                          <Box
                            sx={{
                              display: 'grid',
                              gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                              gap: 1.5,
                              '& .MuiTypography-caption': metadataLabelSx,
                            }}
                          >
                            <Box>
                              <Typography variant="caption" color="text.secondary">
                                {tr('Type', 'النوع')}
                              </Typography>
                              <Chip
                                label={getMaterialTypeLabel(file.file_type, tr)}
                                size="small"
                                sx={{
                                  mt: 0.25,
                                  height: 24,
                                  width: 'fit-content',
                                  bgcolor: meta.lightColor,
                                  color: meta.color,
                                  fontWeight: 700,
                                  fontSize: '0.72rem',
                                }}
                              />
                            </Box>
                            <Box sx={{ gridColumn: '1 / -1' }}>
                              <Typography variant="caption" color="text.secondary">
                                {tr('Last updated', 'آخر تحديث')}
                              </Typography>
                              <Typography sx={metadataValueSx}>
                                {formatDateTime(file.last_modified, locale)}
                              </Typography>
                            </Box>
                          </Box>

                          <Box sx={{ mt: 'auto', pt: 0.5 }}>
                            <Button
                              fullWidth
                              variant="contained"
                              sx={materialActionButtonSx}
                              startIcon={
                                isOpening ? (
                                  <CircularProgress size={16} color="inherit" />
                                ) : file.file_type === 'video' ? (
                                  <PlayCircleOutline />
                                ) : (
                                  <OpenInNew />
                                )
                              }
                              onClick={(event) => {
                                event.stopPropagation();
                                file.file_type === 'video' ? handleOpenVideoFile(file) : handleOpenFile(file);
                              }}
                              disabled={isOpening}
                            >
                              {isOpening
                                ? tr('Opening...', 'جارٍ الفتح...')
                                : file.file_type === 'video'
                                  ? tr('Play Video', 'تشغيل الفيديو')
                                : isDownloadOnlyMaterialType(file.file_type)
                                  ? tr('Download', 'تنزيل')
                                  : tr('View', 'عرض')}
                            </Button>
                          </Box>
                        </CardContent>
                      </Card>
                    );
                  })}
                </Box>
              ) : (
                <Typography color="text.secondary">
                  {tr('No supported files in the current view.', 'لا توجد ملفات مدعومة في العرض الحالي.')}
                </Typography>
              )}
            </CardContent>
          </Card>
          ) : null}

          {false && !totalVisibleItems ? (
            <Card>
              <CardContent
                sx={{
                  py: 6,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  textAlign: 'center',
                  gap: 1,
                }}
              >
                <FolderOpen sx={{ fontSize: 42, color: 'text.secondary', opacity: 0.7 }} />
                <Typography sx={{ fontWeight: 700, fontSize: '1.08rem', color: '#0b1f4d' }}>
                  {totalCurrentItems
                    ? tr('No folders or files match the current search or filter.', 'لا توجد مجلدات أو ملفات تطابق البحث أو التصفية الحالية.')
                    : tr('This folder is empty.', 'هذا المجلد فارغ.')}
                </Typography>
                <Typography color="text.secondary" sx={{ maxWidth: 540 }}>
                  {totalCurrentItems
                    ? tr(
                        'Try another search term or reset the file type filter.',
                        'جرّب كلمة بحث مختلفة أو أعد ضبط نوع الملف.'
                      )
                    : tr(
                        'Add subfolders or upload supported files to populate this location.',
                        'أضف مجلدات فرعية أو ارفع ملفات مدعومة لملء هذا الموقع.'
                      )}
                </Typography>
              </CardContent>
            </Card>
          ) : null}
        </Stack>
      )}

      <Dialog open={Boolean(dialogState.type)} onClose={closeDialog} maxWidth="xs" fullWidth>
        <DialogTitle>{dialogState.title}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            margin="normal"
            label={dialogState.label}
            value={dialogState.value}
            onChange={(event) =>
              setDialogState((previousState) => ({
                ...previousState,
                value: event.target.value,
              }))
            }
            disabled={dialogLoading}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog} disabled={dialogLoading}>
            {tr('Cancel', 'إلغاء')}
          </Button>
          <Button onClick={handleDialogConfirm} variant="contained" disabled={dialogLoading}>
            {dialogLoading ? tr('Saving...', 'جارٍ الحفظ...') : dialogState.confirmLabel}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={toast.open}
        autoHideDuration={3500}
        onClose={() => setToast((previousState) => ({ ...previousState, open: false }))}
        anchorOrigin={{ vertical: 'top', horizontal: isArabic ? 'left' : 'right' }}
      >
        <Alert
          onClose={() => setToast((previousState) => ({ ...previousState, open: false }))}
          severity={toast.severity}
          sx={{ width: '100%' }}
        >
          {toast.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default DailyBriefManagement;


