import React, { createContext, useContext, useState, useEffect } from "react";
import {
  fetchCurrentUser,
  loginWithPassword,
  logoutCurrentSession,
  registerAccount,
} from "../features/auth/authApi";

const AuthContext = createContext(null);

const readSavedUser = () => {
  const saved = localStorage.getItem("user");
  if (!saved) {
    return null;
  }

  try {
    return JSON.parse(saved);
  } catch {
    localStorage.removeItem("user");
    return null;
  }
};

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [refreshToken, setRefreshToken] = useState(localStorage.getItem("refresh_token"));
  const [user, setUser] = useState(readSavedUser);
  const [loading, setLoading] = useState(() => Boolean(localStorage.getItem("token")));

  const isAuthenticated = !!token;
  const isAdmin = user?.role === "admin";

  const clearAuthState = () => {
    setToken(null);
    setRefreshToken(null);
    setUser(null);
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("user");
  };

  const applyAuthPayload = ({ access_token, refresh_token, user: authUser }) => {
    setToken(access_token);
    localStorage.setItem("token", access_token);

    if (refresh_token) {
      setRefreshToken(refresh_token);
      localStorage.setItem("refresh_token", refresh_token);
    }

    if (authUser) {
      setUser(authUser);
      localStorage.setItem("user", JSON.stringify(authUser));
    }

    return authUser;
  };

  const logout = async (notifyServer = true) => {
    const hasToken = Boolean(localStorage.getItem("token"));
    if (notifyServer && hasToken) {
      try {
        await logoutCurrentSession();
      } catch (error) {
        console.warn("退出登录通知失败，已清理本地登录态:", error);
      }
    }

    clearAuthState();
  };

  const fetchUserInfo = async () => {
    try {
      const response = await fetchCurrentUser();
      setUser(response.data);
      setToken(localStorage.getItem("token"));
      setRefreshToken(localStorage.getItem("refresh_token"));
      localStorage.setItem("user", JSON.stringify(response.data));
      return response.data;
    } catch (error) {
      console.error("获取用户信息失败:", error);
      await logout(false);
      return null;
    }
  };

  const register = async (username, email, password) => {
    try {
      setLoading(true);
      const response = await registerAccount(username, email, password);

      if (response.data) {
        await login(username, password);
      }
      return { success: true };
    } catch (error) {
      console.error("注册失败:", error);
      let errorMessage = "注册失败，请重试";

      if (error.response?.data?.detail) {
        if (typeof error.response.data.detail === "string") {
          errorMessage = error.response.data.detail;
        } else if (Array.isArray(error.response.data.detail)) {
          errorMessage = error.response.data.detail
            .map((e) => e.msg)
            .join(", ");
        } else if (typeof error.response.data.detail === "object") {
             errorMessage = error.response.data.detail.msg || JSON.stringify(error.response.data.detail);
        }
      }

      return { success: false, message: errorMessage };
    } finally {
      setLoading(false);
    }
  };

  const login = async (username, password) => {
    try {
      setLoading(true);
      const response = await loginWithPassword(username, password);

      const authUser = applyAuthPayload(response.data);
      if (!authUser) {
        await fetchUserInfo();
      }
      return { success: true };
    } catch (error) {
      console.error("登录失败:", error);
      let errorMessage = "登录失败，请检查用户名和密码";

      if (error.response?.data?.detail) {
        if (typeof error.response.data.detail === "string") {
          errorMessage = error.response.data.detail;
        } else if (Array.isArray(error.response.data.detail)) {
          errorMessage = error.response.data.detail
            .map((e) => e.msg)
            .join(", ");
        } else if (typeof error.response.data.detail === "object") {
             // Handle case where detail might be a single object (though less common for 422)
             errorMessage = error.response.data.detail.msg || JSON.stringify(error.response.data.detail);
        }
      }

      return {
        success: false,
        message: errorMessage,
      };
    } finally {
      setLoading(false);
    }
  };

  // 🆕 刷新用户信息（用于更新头像等）
  const refreshUser = async () => {
    await fetchUserInfo();
  };

  useEffect(() => {
    let active = true;

    const initAuth = async () => {
      if (!localStorage.getItem("token")) {
        if (active) {
          setLoading(false);
        }
        return;
      }

      await fetchUserInfo();
      if (active) {
        setLoading(false);
      }
    };

    initAuth();

    return () => {
      active = false;
    };
  }, []);

  return (
    <AuthContext.Provider
      value={{
        token,
        refreshToken,
        user,
        loading,
        isAuthenticated,
        isAdmin,
        register,
        login,
        logout,
        fetchUserInfo,
        refreshUser,  // 🆕 导出 refreshUser
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
};

export const useOptionalAuth = () => useContext(AuthContext) || {
  isAdmin: false,
  isAuthenticated: false,
  user: null,
};
