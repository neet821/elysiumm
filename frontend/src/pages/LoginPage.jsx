import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { consumeAuthRedirect, getLocationTarget, getPostLoginTarget } from "../utils/authRedirect";
import LoginCard from "../components/auth/LoginCard.jsx";

const LoginPage = ({ styles, isDark }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  const handleSuccess = () => {
    const storedTarget = consumeAuthRedirect();
    const stateTarget = location.state?.from
      ? getLocationTarget(location.state.from)
      : "";
    const redirectTarget = getPostLoginTarget(
      searchParams.get("redirect") || stateTarget || storedTarget,
    );
    navigate(redirectTarget, { replace: true });
  };

  return (
    <div
      className={`auth-page min-h-screen flex items-center justify-center py-12 px-4 ${styles.bgSecondary} transition-colors duration-1000 animate-fade-in`}
    >
      <LoginCard isDark={isDark} onSuccess={handleSuccess} styles={styles} />
    </div>
  );
};

export default LoginPage;
