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


import axios from 'axios';
import {
  clearAuthStorage,
  getStoredAccessToken,
  hasValidSession,
  isTokenExpired,
  normalizedBasePath,
  redirectToLogin,
  refreshAccessToken,
} from './sessionAuth';

const runtimeBaseURL =
  typeof window !== 'undefined' ? window.__TRAINING_API_BASE_URL : '';
const defaultBaseURL =
  typeof window !== 'undefined'
    ? `${window.location.origin}${normalizedBasePath}`
    : 'http://127.0.0.1:3000/training';

const api = axios.create({
  baseURL: runtimeBaseURL || defaultBaseURL,
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
    const requestUrl = config.url || '';
    if (isAuthRequestUrl(requestUrl)) {
      return config;
    }

    let token = getStoredAccessToken();
    try {
      if (token && isTokenExpired(token)) {
        token = await refreshAccessToken();
      } else if (!token && hasValidSession()) {
        token = await refreshAccessToken();
      }
    } catch (refreshError) {
      clearAuthStorage();
      redirectToLogin();
      return Promise.reject(refreshError);
    }

    if (token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
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
