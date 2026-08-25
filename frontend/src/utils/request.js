import axios from "axios";
import { API_BASE_URL, API_ENDPOINTS } from "../config";
import { buildLoginRedirect, shouldBypassAuthRedirect, saveAuthRedirect } from "./authRedirect";

let refreshPromise = null;

const clearAuthStorage = () => {
  localStorage.removeItem("token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("user");
};

const redirectToLogin = () => {
  if (!shouldBypassAuthRedirect(window.location.pathname)) {
    saveAuthRedirect(window.location);
    window.location.href = buildLoginRedirect(window.location);
  }
};

const refreshAccessToken = async () => {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) {
    return null;
  }

  if (!refreshPromise) {
    refreshPromise = axios
      .post(API_ENDPOINTS.REFRESH, { refresh_token: refreshToken })
      .then((response) => {
        const { access_token, refresh_token, user } = response.data;
        localStorage.setItem("token", access_token);
        if (refresh_token) {
          localStorage.setItem("refresh_token", refresh_token);
        }
        if (user) {
          localStorage.setItem("user", JSON.stringify(user));
        }
        return access_token;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
};

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 增加到30秒
  withXSRFToken: false,
  // headers: {
  //   "Content-Type": "application/json",
  // },
});

// 请求拦截器 - 添加认证token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // 添加请求开始时间,用于日志
    config.metadata = { startTime: new Date() };

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器 - 处理错误和重试
apiClient.interceptors.response.use(
  (response) => {
    // 记录请求耗时
    const endTime = new Date();
    const duration = endTime - response.config.metadata.startTime;

    if (duration > 5000) {
      console.warn(`慢请求警告: ${response.config.url} 耗时 ${duration}ms`);
    }

    return response;
  },
  async (error) => {
    const originalRequest = error.config;
    const skipAuthRedirect = originalRequest?.skipAuthRedirect === true;

    const isAuthRequest = [API_ENDPOINTS.LOGIN, API_ENDPOINTS.REFRESH].includes(
      originalRequest?.url,
    );

    // 401错误优先尝试刷新登录态，再平滑退出
    if (error.response?.status === 401) {
      if (skipAuthRedirect) {
        return Promise.reject(error);
      }

      if (!originalRequest?._retry && !isAuthRequest) {
        originalRequest._retry = true;
        try {
          const newAccessToken = await refreshAccessToken();
          if (newAccessToken) {
            originalRequest.headers = originalRequest.headers || {};
            originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
            return apiClient(originalRequest);
          }
        } catch (refreshError) {
          console.error("刷新登录态失败:", refreshError);
        }
      }

      clearAuthStorage();
      redirectToLogin();
      return Promise.reject(error);
    }

    // 处理超时错误 - 自动重试一次(仅针对GET请求)
    if (error.code === "ECONNABORTED" && error.message.includes("timeout")) {
      if (!originalRequest._retry && originalRequest.method === "get") {
        originalRequest._retry = true;
        console.log(`请求超时,正在重试: ${originalRequest.url}`);

        // 增加超时时间后重试
        originalRequest.timeout = 60000; // 60秒

        try {
          return await apiClient(originalRequest);
        } catch (retryError) {
          console.error(`重试失败: ${originalRequest.url}`, retryError);
          return Promise.reject(retryError);
        }
      }
    }

    // 处理网络错误
    if (!error.response) {
      console.error("网络错误:", error.message);
      error.message = "无法连接到服务器,请检查网络连接或后端服务是否正常运行";
    }

    return Promise.reject(error);
  }
);

export default apiClient;
