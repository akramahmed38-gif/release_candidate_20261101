import axios from 'axios/dist/browser/axios.cjs';

const basePath = import.meta.env.VITE_BASENAME || '/training';
const normalizedBasePath = basePath.startsWith('/') ? basePath : `/${basePath}`;
const normalizeApiBaseURL = (value) => {
  const normalized = String(value || '').trim().replace(/\/+$/, '');
  // A root override would drop the application mount path. Use the mounted
  // path unless an explicit non-root API origin/path was configured.
  return normalized && normalized !== '/' ? normalized : normalizedBasePath;
};

export const resolveApiBaseURL = () => {
  const runtimeBaseURL =
    typeof window !== 'undefined' ? window.__TRAINING_API_BASE_URL : '';
  const configuredBaseURL = runtimeBaseURL || import.meta.env.VITE_API_BASE_URL;
  return normalizeApiBaseURL(configuredBaseURL);
};

export const resolveApiRequestURL = (path) => {
  const requestPath = String(path || '');
  if (/^https?:\/\//i.test(requestPath)) {
    return requestPath;
  }
  return `${resolveApiBaseURL()}/${requestPath.replace(/^\/+/, '')}`;
};

const ACCESS_TOKEN_STORAGE_KEY = 'token';
const REFRESH_TOKEN_STORAGE_KEY = 'refresh_token';
const USER_STORAGE_KEY = 'user';

const setCookieValue = (name, value, maxAgeSeconds) => {
  if (typeof document === 'undefined') {
    return;
  }

  const parts = [`${name}=${encodeURIComponent(value)}`, `Path=${normalizedBasePath}`, 'SameSite=Lax'];
  if (typeof maxAgeSeconds === 'number' && Number.isFinite(maxAgeSeconds)) {
    parts.push(`Max-Age=${Math.max(0, Math.floor(maxAgeSeconds))}`);
  }
  document.cookie = parts.join('; ');
};

const clearCookieValue = (name) => {
  if (typeof document === 'undefined') {
    return;
  }
  document.cookie = `${name}=; Path=${normalizedBasePath}; Max-Age=0; SameSite=Lax`;
};

export const parseJwt = (token) => {
  try {
    const payload = token.split('.')[1];
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const decoded = atob(base64);
    return JSON.parse(decoded);
  } catch (error) {
    return null;
  }
};

export const isTokenExpired = (token) => {
  const payload = parseJwt(token);
  if (!payload?.exp) {
    return true;
  }
  const nowSeconds = Math.floor(Date.now() / 1000);
  return nowSeconds >= Number(payload.exp);
};

const getTokenMaxAge = (token) => {
  const payload = parseJwt(token);
  if (!payload?.exp) {
    return undefined;
  }
  const nowSeconds = Math.floor(Date.now() / 1000);
  return Math.max(Number(payload.exp) - nowSeconds, 0);
};

export const clearAuthStorage = () => {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
    window.localStorage.removeItem(USER_STORAGE_KEY);
  }
  clearCookieValue('training_access_token');
  clearCookieValue('training_refresh_token');
  clearCookieValue('access_token');
  clearCookieValue('refresh_token');
};

export const storeAuthSession = ({ accessToken, refreshToken, user }) => {
  if (typeof window !== 'undefined') {
    if (accessToken) {
      window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, accessToken);
    }
    if (refreshToken) {
      window.localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, refreshToken);
    }
    if (user !== undefined) {
      if (user) {
        window.localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
      } else {
        window.localStorage.removeItem(USER_STORAGE_KEY);
      }
    }
  }

  if (accessToken) {
    setCookieValue('training_access_token', accessToken, getTokenMaxAge(accessToken));
  }
  if (refreshToken) {
    setCookieValue('training_refresh_token', refreshToken, getTokenMaxAge(refreshToken));
  }
};

export const getStoredAccessToken = () => {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
};

export const getStoredRefreshToken = () => {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
};

export const getStoredUser = () => {
  if (typeof window === 'undefined') {
    return null;
  }
  const userStr = window.localStorage.getItem(USER_STORAGE_KEY);
  if (!userStr) {
    return null;
  }
  try {
    return JSON.parse(userStr);
  } catch (error) {
    window.localStorage.removeItem(USER_STORAGE_KEY);
    return null;
  }
};

export const hasValidAccessToken = () => {
  const token = getStoredAccessToken();
  return Boolean(token) && !isTokenExpired(token);
};

export const hasValidRefreshToken = () => {
  const token = getStoredRefreshToken();
  return Boolean(token) && !isTokenExpired(token);
};

export const hasValidSession = () => {
  return hasValidAccessToken() || hasValidRefreshToken();
};

export const getCurrentStoredUser = () => {
  const user = getStoredUser();
  if (!user) {
    return null;
  }
  if (hasValidSession()) {
    return user;
  }
  clearAuthStorage();
  return null;
};

export const redirectToLogin = () => {
  if (typeof window === 'undefined') {
    return;
  }
  const loginPath = `${normalizedBasePath}/login`;
  if (window.location.pathname !== loginPath) {
    window.location.href = loginPath;
  }
};

let refreshPromise = null;

export const refreshAccessToken = async () => {
  if (refreshPromise) {
    return refreshPromise;
  }

  const refreshToken = getStoredRefreshToken();
  if (!refreshToken || isTokenExpired(refreshToken)) {
    clearAuthStorage();
    throw new Error('Refresh token is missing or expired');
  }

  refreshPromise = axios
    .post(
      resolveApiRequestURL('/api/v1/users/refresh'),
      { refresh_token: refreshToken },
      {
        headers: {
          'Content-Type': 'application/json',
        },
      }
    )
    .then((response) => {
      const nextAccessToken = response.data?.access_token;
      const nextRefreshToken = response.data?.refresh_token || refreshToken;
      if (!nextAccessToken) {
        throw new Error('Refresh response did not include an access token');
      }
      storeAuthSession({
        accessToken: nextAccessToken,
        refreshToken: nextRefreshToken,
        user: getStoredUser(),
      });
      return nextAccessToken;
    })
    .catch((error) => {
      clearAuthStorage();
      throw error;
    })
    .finally(() => {
      refreshPromise = null;
    });

  return refreshPromise;
};

export { normalizedBasePath };
