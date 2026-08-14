import { BrowserRouter as Router } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";

import { AppShell } from "./components/layout/AppShell";
import ErrorBoundary from "./components/ErrorBoundary";
import AppRoutes from "./routes";

function App() {
  return (
    <AuthProvider>
      <Router future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <AppShell>
          <ErrorBoundary>
            <AppRoutes />
          </ErrorBoundary>
        </AppShell>
      </Router>
    </AuthProvider>
  );
}

export default App;
