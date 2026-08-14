import { BrowserRouter as Router } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import { THEME } from "./theme";
import { useTheme } from "./theme/useTheme";

import { AppShell } from "./components/layout/AppShell";
import ErrorBoundary from "./components/ErrorBoundary";
import AppRoutes from "./routes";

function App() {
  const { isDark, toggleTheme } = useTheme();
  const styles = isDark ? THEME.dark : THEME.light;

  return (
    <AuthProvider>
      <Router future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <AppShell isDark={isDark} toggleTheme={toggleTheme}>
            <ErrorBoundary>
              <AppRoutes styles={styles} isDark={isDark} toggleTheme={toggleTheme} />
            </ErrorBoundary>
        </AppShell>
      </Router>
    </AuthProvider>
  );
}

export default App;
