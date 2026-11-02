import api from './api';
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
  getAllUsers: async () => {
    return await api.get('/api/v1/users/users');
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
    return await api.post('/api/v1/users/users/manage', {
      action: 'delete',
      email,
    });
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
    return await api.post('/api/v1/users/bulkusers/delete', formData, {
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

// Material Management Service
export const materialService = {
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


// Exam Management Service
export const examService = {
  getAllExams: async () => {
    return await api.get('/api/v1/exams/all');
  },

  getExamById: async (examId) => {
    return await api.get(`/api/v1/exams/${examId}`);
  },

  getExamResultsDetails: async (examId) => {
    return await api.get(`/api/v1/exams/${examId}/results_details`);
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

  sendExamMail: async (examId) => {
    return await api.post(`/api/v1/exams/${examId}/send-mail`);
  },

  deleteExam: async (examId) => {
    return await api.delete(`/api/v1/exams/harddelete/${examId}`);
  },

  getStudentExams: async () => {
    return await api.get('/api/v1/exams/student');
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
  getDashboardKpis: async (params = {}) => {
    return await api.get('/api/v1/exams/dashboard/kpis', { params });
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
