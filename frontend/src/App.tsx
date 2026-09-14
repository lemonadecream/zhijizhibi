import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import { AiConfigProvider } from "./context/AiConfigContext";
import LoadingState from "./components/ui/LoadingState";
import AppShell from "./layouts/AppShell";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ProfilePage from "./pages/Profile";
import ExplorePage from "./pages/Explore";
import TargetJobPage from "./pages/TargetJob";
import PreparePage from "./pages/Prepare";
import TrackingPage from "./pages/Tracking";
import OfferPage from "./pages/Offer";
import OnboardingPage from "./pages/Onboarding";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token, loading } = useAuth();
  if (loading) return <LoadingState label="加载中…" />;
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

// Onboarding is full-screen and immersive -- it deliberately does NOT use the
// AppShell (no 6-workspace nav) until the career profile is finalized.
function RequireAuthPlain({ children }: { children: React.ReactNode }) {
  const { token, loading } = useAuth();
  if (loading) return <LoadingState label="加载中…" />;
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  const { token } = useAuth();

  return (
    <AiConfigProvider>
      <Routes>
        <Route path="/login" element={token ? <Navigate to="/onboarding" replace /> : <Login />} />
        <Route path="/register" element={token ? <Navigate to="/onboarding" replace /> : <Register />} />

      {/* Immersive onboarding (no workspace sidebar) */}
      <Route
        path="/onboarding"
        element={
          <RequireAuthPlain>
            <OnboardingPage />
          </RequireAuthPlain>
        }
      />

      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Navigate to="/profile" replace />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/explore" element={<ExplorePage />} />
        <Route path="/target-job" element={<TargetJobPage />} />
        <Route path="/prepare" element={<PreparePage />} />
        <Route path="/tracking" element={<TrackingPage />} />
        <Route path="/offer" element={<OfferPage />} />
      </Route>

      <Route path="*" element={<Navigate to={token ? "/onboarding" : "/login"} replace />} />
      </Routes>
    </AiConfigProvider>
  );
}
