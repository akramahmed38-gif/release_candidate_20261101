import api from './api';
import { createDailyBriefSummaryCache } from './dailyBriefSummaryCache';
import { encodeDailyBriefEnvelope, encodeBriefPayload, requireBriefSaveResponse, requireBriefActionResponse } from './dailyBriefTransport';
import {
  clearAuthStorage,
  getCurrentStoredUser,
  getStoredAccessToken,
  hasValidSession,
  storeAuthSession,
} from './sessionAuth';

// Authentication Service
export const authService = {
  requestOtp: async (email) => {
    return await api.post('/api/v1/users/login/request-otp', { email });
  },
  login: async (email, password) => {
    const response = await api.post('/api/v1/users/login', { email, password });
    if (response.data.access_token) {
      const userData = response.data.data || {};
      const resolvedDepartment = userData.department || userData.role || userData.websiteRole || '';
      const normalizedUser = {
        ...userData,
        department: resolvedDepartment,
        role: resolvedDepartment,
        hrid: userData.hr_id ?? userData.hrid ?? '',
      };
      storeAuthSession({
        accessToken: response.data.access_token,
        refreshToken: response.data.refresh_token,
        user: normalizedUser,
      });
    }
    return response;
  },

  logout: () => {
    clearAuthStorage();
  },

  getCurrentUser: () => {
    return getCurrentStoredUser();
  },

  getToken: () => {
    return getStoredAccessToken();
  },

  hasValidSession: () => {
    return hasValidSession();
  },

  changePassword: async (oldPassword, newPassword) => {
    return await api.put('/api/v1/users/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    });
  },
};

// User Management Service
export const userService = {
  getAllUsers: async (params = {}) => {
    return await api.get('/api/v1/users/users', { params });
  },
  getUserFilterOptions: async (params = {}) => {
    return await api.get('/api/v1/users/users/filter-options', { params });
  },
  getBranches: async () => {
    return await api.get('/api/v1/users/branches');
  },
  createUser: async (userData) => {
    return await api.post('/api/v1/users/users', userData);
  },
  createBranch: async (branchData) => {
    return await api.post('/api/v1/users/branches', branchData);
  },
  updateUser: async (email, userData) => {
    const response = await api.post('/api/v1/users/users/manage', {
      action: 'update',
      email,
      data: userData,
    });
    if (response.data?.signal !== 'success') {
      throw new Error(response.data?.message || 'The server did not confirm the user update.');
    }
    return response;
  },
  deleteUser: async (email) => {
    return await api.delete(`/api/v1/users/users/${email}`);
  },
  bulkUploadUsers: async (file) => {
    const formData = new FormData();
    formData.append('excel_file', file);
    return await api.post('/api/v1/users/bulkusers', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },
  bulkDeleteUsers: async (file) => {
    const formData = new FormData();
    formData.append('excel_file', file);
    return await api.delete('/api/v1/users/bulkusers', {
      data: formData,
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },
  exportUsersExcel: async () => {
    return await api.get('/api/v1/users/users/export', {
      responseType: 'blob',
    });
  },
  getUserByHrId: async (hrId) => {
    return await api.get(`/api/v1/users/user/${hrId}`);
  },
  getAudienceHierarchy: async (params = {}) => {
    const searchParams = new URLSearchParams();
    if (Array.isArray(params.regions)) {
      params.regions.forEach((region) => searchParams.append('regions', region));
    }
    if (Array.isArray(params.areas)) {
      params.areas.forEach((area) => searchParams.append('areas', area));
    }
    const query = searchParams.toString();
    const url = query ? `/api/v1/users/users/audience/hierarchy?${query}` : '/api/v1/users/users/audience/hierarchy';
    return await api.get(url);
  },
  resolveAudience: async (audiencePayload) => {
    return await api.post('/api/v1/users/users/audience/resolve', audiencePayload);
  },
  exportResolvedAudienceExcel: async (audiencePayload) => {
    return await api.post('/api/v1/users/users/audience/resolve/export', audiencePayload, {
      responseType: 'blob',
    });
  },
  bulkValidateAudience: async (file) => {
    const formData = new FormData();
    formData.append('upload_file', file);
    return await api.post('/api/v1/users/audience/bulk-upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },
  bulkUploadBranches: async (file) => {
    const formData = new FormData();
    formData.append('excel_file', file);
    return await api.post('/api/v1/users/branches/bulk', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },
};

export const resignedUsersService = {
  list: async (params = {}) => {
    return await api.get('/api/v1/admin/resigned-users', { params });
  },
  export: async (params = {}) => {
    return await api.get('/api/v1/admin/resigned-users/export', {
      params,
      responseType: 'blob',
    });
  },
  reactivate: async (employeeId, reason) => {
    return await api.post(`/api/v1/admin/users/${employeeId}/reactivate`, { reason });
  },
  reactivateAll: async (payload = {}) => {
    return await api.post('/api/v1/admin/resigned-users/reactivate-all', payload);
  },
  runInactivityCheck: async (dryRun = true) => {
    return await api.post('/api/v1/admin/resigned-users/run-inactivity-check', null, {
      params: { dry_run: dryRun },
    });
  },
  backfillLoginHistory: async (dryRun = true) => {
    return await api.post('/api/v1/admin/resigned-users/backfill-login-history', null, {
      params: { dry_run: dryRun },
    });
  },
};

// Material Management Service
export const materialService = {
  getLibraryMaterials: async (path = '') => {
    return await api.get('/api/v1/materials', {
      params: { path },
    });
  },

  openLibraryMaterial: async (path) => {
    return await api.get('/api/v1/materials/open', {
      params: { path },
      responseType: 'blob',
    });
  },

  createLibraryFolder: async (path, name) => {
    return await api.post('/api/v1/materials/folder', { path, name });
  },

  renameLibraryFolder: async (path, newName) => {
    return await api.put('/api/v1/materials/folder', { path, new_name: newName });
  },

  deleteLibraryFolder: async (path) => {
    return await api.delete('/api/v1/materials/folder', {
      data: { path },
    });
  },

  uploadLibraryFiles: async (path, files) => {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });
    return await api.post('/api/v1/materials/upload', formData, {
      params: { path },
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },

  renameLibraryFile: async (path, newName) => {
    return await api.put('/api/v1/materials/file', { path, new_name: newName });
  },

  deleteLibraryFile: async (path) => {
    return await api.delete('/api/v1/materials/file', {
      data: { path },
    });
  },

  searchLibraryMaterials: async (query, fileType = 'all') => {
    return await api.get('/api/v1/materials/search', {
      params: {
        query,
        file_type: fileType,
      },
    });
  },

  getAllMaterials: async () => {
    return await api.get('/api/v1/materials/all');
  },
  
  uploadMaterial: async (groupName, trainingType, formData) => {
    // formData here should be a FormData object with files
    return await api.post(
      `/api/v1/materials/upload?group_name=${encodeURIComponent(groupName)}&training_type=${encodeURIComponent(trainingType)}`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
  },
  
  deleteMaterial: async (materialId) => {
    return await api.delete(`/api/v1/materials/softdelete/${materialId}`);
  },

  restoreMaterial: async (materialId) => {
    return await api.post(`/api/v1/materials/restore/${materialId}`);
  },

  viewMaterial: async (materialId) => {
    return await api.get(`/api/v1/materials/view/${materialId}`, {
      responseType: 'blob',
    });
  },

  downloadMaterial: async (materialId) => {
    return await api.get(`/api/v1/materials/download/${materialId}`, {
      responseType: 'blob',
    });
  },
};

const dailyBriefSummary = createDailyBriefSummaryCache(
  () => api.get('/api/v1/daily-briefs/summary'), getStoredAccessToken
);
const briefMutation = async (operation) => {
  try { return await operation(); }
  finally { dailyBriefSummary.invalidate(); }
};

function checkedAudience(response) {
  if (!Array.isArray(response?.data?.recipients) || !Number.isInteger(response?.data?.revision)) {
    throw new Error('Audience response was not confirmed');
  }
  return response;
}

export const dailyBriefService = {
  getActions: (briefId) => api.get(`/api/v1/daily-briefs/${encodeURIComponent(briefId)}/actions`),
  getEmailDeliveryHistory: (briefId) => api.get(`/api/v1/daily-briefs/${encodeURIComponent(briefId)}/email-delivery-history`),
  getAudience: async () => checkedAudience(await api.get('/api/v1/daily-briefs/audience')),
  saveAudience: async (payload) => checkedAudience(await api.post('/api/v1/daily-briefs/audience/save', encodeDailyBriefEnvelope(payload))),
  getSummary: () => dailyBriefSummary.get(),
  peekSummary: () => dailyBriefSummary.peek(),
  listBriefs: async (params = {}) => api.get('/api/v1/daily-briefs', { params }),
  getBrief: async (briefId) => api.get(`/api/v1/daily-briefs/${briefId}`),
  createBrief: async (payload) => briefMutation(async () => requireBriefSaveResponse(await api.post('/api/v1/daily-briefs', encodeBriefPayload(payload)))),
  updateBrief: async (briefId, payload) => briefMutation(async () => requireBriefSaveResponse(await api.post(`/api/v1/daily-briefs/${encodeURIComponent(briefId)}/save`, encodeBriefPayload(payload)), briefId)),
  deleteBrief: async (briefId) => briefMutation(async () => api.delete(`/api/v1/daily-briefs/${briefId}`)),
  duplicateBrief: async (briefId) => briefMutation(async () => api.post(`/api/v1/daily-briefs/${briefId}/duplicate`)),
  publishBrief: async (briefId) => briefMutation(async () => requireBriefActionResponse(await api.post(`/api/v1/daily-briefs/${encodeURIComponent(briefId)}/publish`, {}), 'Daily Brief published')),
  archiveBrief: async (briefId) => briefMutation(async () => api.post(`/api/v1/daily-briefs/${briefId}/archive`)),
  restoreLiveBrief: async (briefId) => briefMutation(async () => requireBriefActionResponse(await api.post(`/api/v1/daily-briefs/${encodeURIComponent(briefId)}/restore-live`, {}), 'Daily Brief restored as live')),
  notifyRetail: async (briefId) => api.post(`/api/v1/daily-briefs/${briefId}/notify-retail`),
  getAnalytics: async (briefId) => api.get(`/api/v1/daily-briefs/${briefId}/analytics`),
  exportAnalytics: async (briefId) => api.get(`/api/v1/daily-briefs/${briefId}/analytics/export`, { responseType: 'blob' }),
  getCurrent: async () => api.get('/api/v1/daily-briefs/current'),
  getHistory: async () => api.get('/api/v1/daily-briefs/history'),
  getPublicBrief: async (briefId) => api.get(`/api/v1/daily-briefs/history/${briefId}`),
  markRead: async (briefId) => api.post(`/api/v1/daily-briefs/${briefId}/read`),
  saveFeedback: async (briefId, payload) => api.post(`/api/v1/daily-briefs/${briefId}/feedback`, payload),
  uploadImage: async (image) => {
    const formData = new FormData();
    formData.append('image', image);
    return api.post('/api/v1/daily-briefs/images', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
};

function vocabularyEnvelope(payload) {
  const wire = encodeDailyBriefEnvelope(payload);
  if (wire.payload_b64.length > 64 * 1024) throw new Error('Vocabulary request is too large');
  return wire;
}
function confirmedVocabulary(response, expectedId) {
  const id = response?.data?.item?.id || response?.data?.id;
  if (typeof id !== 'string' || !id || (expectedId && id !== expectedId)) throw new Error('Vocabulary save was not confirmed');
  return response;
}
export const businessVocabularyService = {
  getCategories: async () => api.get('/api/v1/business-vocabulary/categories'),
  getManagedCategories: async () => api.get('/api/v1/business-vocabulary/categories', { params: { include_inactive: true } }),
  createCategory: async (payload) => confirmedVocabulary(await api.post('/api/v1/business-vocabulary/categories', vocabularyEnvelope(payload))),
  updateCategory: async (categoryId, payload) => confirmedVocabulary(await api.post(`/api/v1/business-vocabulary/categories/${encodeURIComponent(categoryId)}/save`, vocabularyEnvelope(payload)), categoryId),
  deleteCategory: async (categoryId, cascade = false) => api.delete(`/api/v1/business-vocabulary/categories/${categoryId}`, { params: { cascade } }),
  getItems: async (params = {}) => api.get('/api/v1/business-vocabulary/items', { params }),
  createItem: async (payload) => confirmedVocabulary(await api.post('/api/v1/business-vocabulary/items', vocabularyEnvelope(payload))),
  updateItem: async (vocabularyId, payload) => confirmedVocabulary(await api.post(`/api/v1/business-vocabulary/items/${encodeURIComponent(vocabularyId)}/save`, vocabularyEnvelope(payload)), vocabularyId),
  deleteItem: async (vocabularyId) => api.delete(`/api/v1/business-vocabulary/items/${vocabularyId}`),
};

// Script Book retains the existing isolated file library and its original storage/API contract.
export const dailyBriefLibraryService = {
  getLibraryMaterials: async (path = '') => api.get('/api/v1/daily-brief', { params: { path } }),
  openLibraryMaterial: async (path) => api.get('/api/v1/daily-brief/open', { params: { path }, responseType: 'blob' }),
  createLibraryFolder: async (path, name) => api.post('/api/v1/daily-brief/folder', { path, name }),
  renameLibraryFolder: async (path, newName) => api.put('/api/v1/daily-brief/folder', { path, new_name: newName }),
  deleteLibraryFolder: async (path) => api.delete('/api/v1/daily-brief/folder', { data: { path } }),
  uploadLibraryFiles: async (path, files) => {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    return api.post('/api/v1/daily-brief/upload', formData, { params: { path }, headers: { 'Content-Type': 'multipart/form-data' } });
  },
  renameLibraryFile: async (path, newName) => api.put('/api/v1/daily-brief/file', { path, new_name: newName }),
  deleteLibraryFile: async (path) => api.delete('/api/v1/daily-brief/file', { data: { path } }),
  searchLibraryMaterials: async (query, fileType = 'all') => api.get('/api/v1/daily-brief/search', { params: { query, file_type: fileType } }),
};


// Exam Management Service
export const examService = {
  getAllExams: async () => {
    return await api.get('/api/v1/exams/all');
  },

  getExamById: async (examId, config = {}) => {
    return await api.get(`/api/v1/exams/${examId}`, config);
  },

  getExamResultsDetails: async (examId, config = {}) => {
    return await api.get(`/api/v1/exams/${examId}/results_details`, config);
  },

  downloadExamResultsExcel: async (examId) => {
    return await api.get(`/api/v1/exams/${examId}/results_details`, {
      params: { format: 'excel' },
      responseType: 'blob',
    });
  },

  createExam: async (examData) => {
    return await api.post('/api/v1/exams/create', examData);
  },

  updateExam: async (examId, examData) => {
    return await api.put(`/api/v1/exams/${examId}`, examData);
  },

  updateExamLevel: async (examId, payload) => {
    return await api.put(`/api/v1/exams/${examId}/level`, payload);
  },

  getQuestionBank: async (params = {}) => {
    return await api.get('/api/v1/exams/question-bank', { params });
  },
  getQuestionBankGroups: async () => api.get('/api/v1/exams/question-bank/groups'),
  createQuestionBankGroup: async (payload) => api.post('/api/v1/exams/question-bank/groups', payload),
  updateQuestionBankGroup: async (id, payload) => api.put(`/api/v1/exams/question-bank/groups/${encodeURIComponent(id)}`, payload),
  deleteQuestionBankGroup: async (id) => api.delete(`/api/v1/exams/question-bank/groups/${encodeURIComponent(id)}`),
  getQuestionBankGroupQuestions: async (id) => api.get(`/api/v1/exams/question-bank/groups/${encodeURIComponent(id)}/questions`),
  moveQuestionBankItems: async (questionIds, groupId) => api.post('/api/v1/exams/question-bank/groups/move', { question_ids: questionIds, group_id: groupId }),
  selectQuestionBankGroups: async (payload) => api.post('/api/v1/exams/question-bank/groups/select', payload),

  createQuestionBankItem: async (questionData) => {
    return await api.post('/api/v1/exams/question-bank', questionData);
  },

  updateQuestionBankItem: async (bankQuestionId, questionData) => {
    return await api.put(`/api/v1/exams/question-bank/${bankQuestionId}`, questionData);
  },

  deleteQuestionBankItem: async (bankQuestionId) => {
    return await api.delete(`/api/v1/exams/question-bank/${bankQuestionId}`);
  },

  sendExamMail: async (examId) => {
    return await api.post(`/api/v1/exams/${examId}/send-mail`);
  },

  regenerateExam: async (examId) => {
    return await api.post(`/api/v1/exams/${examId}/regenerate`);
  },

  deleteExam: async (examId) => {
    return await api.delete(`/api/v1/exams/harddelete/${examId}`);
  },

  getStudentExams: async () => {
    return await api.get('/api/v1/exams/student');
  },

  startExam: async (examId) => {
    return await api.post(`/api/v1/exams/${examId}/start`);
  },

  submitExam: async (examId, answers) => {
    return await api.post(`/api/v1/exams/${examId}/submit`, { answers });
  },

  getEmployeePerformance: async (payload) => {
    return await api.post('/api/v1/exams/performance', payload);
  },

  downloadEmployeePerformance: async (payload) => {
    return await api.post('/api/v1/exams/performance/export', payload, {
      responseType: 'blob',
    });
  },

  getEmployeePerformanceHistory: async (employeeId) => {
    return await api.get(`/api/v1/exams/performance/${employeeId}/history`);
  },
};

// Dashboard Analytics Service
export const analyticsService = {
  getManagementKpis: async (params = {}, config = {}) => {
    const { signal, ...requestConfig } = config || {};
    return await api.get('/api/v1/exams/dashboard/management-kpis', {
      params,
      signal,
      ...requestConfig,
    });
  },
  getDashboardKpis: async (params = {}) => {
    return await api.get('/api/v1/exams/dashboard/kpis', { params });
  },
  getManagementSummary: async (params = {}, config = {}) => {
    const cleanParams = Object.fromEntries(
      Object.entries(params || {}).filter(([, value]) => value !== undefined && value !== null && value !== '')
    );
    return await api.get('/api/v1/exams/dashboard/management-summary', {
      params: cleanParams,
      signal: config.signal,
    });
  },
  getManagementAttention: async (kind, params = {}, config = {}) => {
    const cleanParams = Object.fromEntries(
      Object.entries({ kind, ...(params || {}) }).filter(
        ([, value]) => value !== undefined && value !== null && value !== ''
      )
    );
    return await api.get('/api/v1/exams/dashboard/management-attention', {
      params: cleanParams,
      signal: config.signal,
    });
  },
  exportNoAttemptUsers: async () => {
    return await api.get('/api/v1/exams/dashboard/export/no-attempts', {
      responseType: 'blob',
    });
  },
  exportNoLoginUsers: async (mode = 'login') => {
    return await api.get('/api/v1/exams/dashboard/export/no-login', {
      params: { mode },
      responseType: 'blob',
    });
  },
  getUserAnalytics: async () => {
    return await api.get('/api/v1/users/users/analyze');
  },

  getExamAnalytics: async () => {
    return await api.get('/api/v1/exams/analyze');
  },

  getMaterialAnalytics: async () => {
    return await api.get('/api/v1/materials/analyze');
  },
};

export const auditService = {
  getLogs: async (params = {}) => {
    return await api.get('/api/v1/audit/logs', { params });
  },
  exportLogs: async (params = {}) => {
    return await api.get('/api/v1/audit/logs/export', {
      params,
      responseType: 'blob',
    });
  },
  purgeLogs: async (beforeTs = null) => {
    const params = beforeTs ? { before_ts: beforeTs } : {};
    return await api.delete('/api/v1/audit/logs/purge', { params });
  },
};
