// import axios from 'axios';

// const defaultBaseURL =
//   typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:3000';

// const api = axios.create({
//   baseURL: process.env.REACT_APP_API_BASE_URL || defaultBaseURL,
//   headers: {
//     'Content-Type': 'application/json',
//   },
// });

// // Add token to requests
// api.interceptors.request.use(
//   (config) => {
//     const token = localStorage.getItem('token');
//     if (token) {
//       config.headers.Authorization = `Bearer ${token}`;
//     }
//     return config;
//   },
//   (error) => {
//     return Promise.reject(error);
//   }
// );

// // Handle responses
// api.interceptors.response.use(
//   (response) => response,
//   (error) => {
//     if (error.response?.status === 401) {
//       localStorage.removeItem('token');
//       localStorage.removeItem('user');
//       window.location.href = '/login';
//     }
//     return Promise.reject(error);
//   }
// );

// export default api;


import axios from 'axios/dist/browser/axios.cjs';
import {
  clearAuthStorage,
  getStoredAccessToken,
  hasValidSession,
  isTokenExpired,
  redirectToLogin,
  refreshAccessToken,
  resolveApiBaseURL,
} from './sessionAuth';

const api = axios.create({
  // Keep requests mounted beneath /training on both VPN and public hosts.
  baseURL: resolveApiBaseURL(),
  headers: {
    'Content-Type': 'application/json',
  },
});

const isAuthRequestUrl = (requestUrl = '') =>
  requestUrl.includes('/api/v1/users/login') ||
  requestUrl.includes('/api/v1/users/login/request-otp') ||
  requestUrl.includes('/api/v1/users/refresh');

// Add token to requests
api.interceptors.request.use(
  async (config) => {
    try {
      // Preserve the centralized base path in error.config as well as the
      // dispatched request, which makes browser diagnostics trustworthy.
      config.baseURL = config.baseURL || resolveApiBaseURL();
      const requestUrl = config.url || '';
      if (isAuthRequestUrl(requestUrl)) {
        console.log('[AXIOS REQUEST]', {
          method: config.method,
          baseURL: config.baseURL,
          url: config.url,
          hasAuthorization: Boolean(config.headers?.Authorization),
          signalAborted: Boolean(config.signal?.aborted),
        });
        return config;
      }

      let token = getStoredAccessToken();
      if (token && isTokenExpired(token)) {
        token = await refreshAccessToken();
      } else if (!token && hasValidSession()) {
        token = await refreshAccessToken();
      }

      if (token) {
        config.headers = config.headers || {};
        config.headers.Authorization = `Bearer ${token}`;
      }
      console.log('[AXIOS REQUEST]', {
        method: config.method,
        baseURL: config.baseURL,
        url: config.url,
        hasAuthorization: Boolean(config.headers?.Authorization),
        signalAborted: Boolean(config.signal?.aborted),
      });
      return config;
    } catch (interceptorError) {
      console.error('[AXIOS REQUEST ERROR]', {
        name: interceptorError?.name ?? null,
        message: interceptorError?.message ?? null,
        code: interceptorError?.code ?? null,
        isAxiosError: Boolean(interceptorError?.isAxiosError),
      });
      clearAuthStorage();
      redirectToLogin();
      return Promise.reject(interceptorError);
    }
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Handle responses
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const requestUrl = error.config?.url || '';
    const isAuthRequest = isAuthRequestUrl(requestUrl);
    if (error.response?.status === 403 && error.response?.data?.signal === 'inactive_user') {
      clearAuthStorage();
      redirectToLogin();
      return Promise.reject(error);
    }
    if (error.response?.status === 401 && !isAuthRequest && !error.config?._retry) {
      try {
        error.config._retry = true;
        const nextAccessToken = await refreshAccessToken();
        error.config.headers = error.config.headers || {};
        error.config.headers.Authorization = `Bearer ${nextAccessToken}`;
        return api.request(error.config);
      } catch (refreshError) {
        // Fall through to the shared logout path below.
      }
    }
    if (error.response?.status === 401 && !isAuthRequest) {
      clearAuthStorage();
      redirectToLogin();
    }
    return Promise.reject(error);
  }
);

export default api;
