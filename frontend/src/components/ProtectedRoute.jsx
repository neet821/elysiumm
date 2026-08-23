import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { buildLoginRedirect, saveAuthRedirect } from "../utils/authRedirect";
import AccessDeniedPage from "../pages/AccessDeniedPage";

const ProtectedRoute = ({ children, requireAdmin = false }) => {
  const { isAuthenticated, isAdmin, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center gap-3" role="status" aria-label="正在确认登录状态">
        <div className="animate-spin w-8 h-8 border-4 border-gray-300 border-t-blue-500 rounded-full"></div>
        <span>正在确认登录状态…</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    saveAuthRedirect(location);
    return <Navigate to={buildLoginRedirect(location)} replace />;
  }

  if (requireAdmin && !isAdmin) {
    return <AccessDeniedPage />;
  }

  return children;
};

export default ProtectedRoute;
