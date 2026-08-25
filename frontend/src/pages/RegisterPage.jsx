import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { User, Mail, Lock } from "lucide-react";

const RegisterPage = ({ styles, isDark }) => {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("两次输入的密码不一致");
      return;
    }

    if (password.length < 6) {
      setError("密码长度至少为6个字符");
      return;
    }

    const result = await register(username, email, password);
    if (result.success) {
      navigate("/");
    } else {
      setError(result.message);
    }
  };

  return (
    <div
      className={`min-h-screen flex items-center justify-center py-12 px-4 ${styles.bgSecondary} transition-colors duration-1000 animate-fade-in`}
    >
      <div
        className={`max-w-md w-full ${styles.bg} rounded-2xl shadow-xl p-5 sm:p-8 border ${styles.border}`}
      >
        <div className="text-center mb-8">
          <h1 className={`text-3xl font-bold ${styles.text} mb-2`}>创建账户</h1>
          <p className={`text-sm ${styles.textMuted}`}>
            创建你的 Elysium 账号
          </p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg" role="alert">
            <p className="text-red-600 text-sm">{error}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label htmlFor="register-username" className={`mb-2 flex items-center gap-2 text-sm font-medium ${styles.text}`}>
              <User size={16} aria-hidden="true" />
              用户名
            </label>
            <input
              id="register-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className={`w-full px-4 py-3 border ${styles.border} rounded-lg ${
                styles.bgSecondary
              } ${styles.text} focus:outline-none focus:ring-2 ${
                isDark ? "focus:ring-orange-500" : "focus:ring-[#189BCC]"
              }`}
              placeholder="输入用户名"
              required
            />
          </div>

          <div>
            <label htmlFor="register-email" className={`mb-2 flex items-center gap-2 text-sm font-medium ${styles.text}`}>
              <Mail size={16} aria-hidden="true" />
              邮箱
            </label>
            <input
              id="register-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={`w-full px-4 py-3 border ${styles.border} rounded-lg ${
                styles.bgSecondary
              } ${styles.text} focus:outline-none focus:ring-2 ${
                isDark ? "focus:ring-orange-500" : "focus:ring-[#189BCC]"
              }`}
              placeholder="输入邮箱"
              required
            />
          </div>

          <div>
            <label htmlFor="register-password" className={`mb-2 flex items-center gap-2 text-sm font-medium ${styles.text}`}>
              <Lock size={16} aria-hidden="true" />
              密码
            </label>
            <input
              id="register-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={`w-full px-4 py-3 border ${styles.border} rounded-lg ${
                styles.bgSecondary
              } ${styles.text} focus:outline-none focus:ring-2 ${
                isDark ? "focus:ring-orange-500" : "focus:ring-[#189BCC]"
              }`}
              placeholder="输入密码（至少6个字符）"
              required
            />
          </div>

          <div>
            <label htmlFor="register-password-confirmation" className={`mb-2 flex items-center gap-2 text-sm font-medium ${styles.text}`}>
              <Lock size={16} aria-hidden="true" />
              确认密码
            </label>
            <input
              id="register-password-confirmation"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={`w-full px-4 py-3 border ${styles.border} rounded-lg ${
                styles.bgSecondary
              } ${styles.text} focus:outline-none focus:ring-2 ${
                isDark ? "focus:ring-orange-500" : "focus:ring-[#189BCC]"
              }`}
              placeholder="再次输入密码"
              required
            />
          </div>

          <button
            type="submit"
            className={`w-full py-3 text-white rounded-lg font-medium transition-colors ${
              isDark
                ? "bg-orange-600 hover:bg-orange-500"
                : "bg-[#189BCC] hover:bg-[#1589b5]"
            }`}
          >
            注册
          </button>
        </form>

        <div className="mt-6 text-center">
          <p className={`text-sm ${styles.textMuted}`}>
            已有账号？{" "}
            <Link
              to="/login"
              className={`${styles.accentClass} hover:underline font-medium`}
            >
              立即登录
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default RegisterPage;
