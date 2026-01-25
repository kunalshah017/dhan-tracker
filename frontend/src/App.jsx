import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuthStore } from './AuthContext';
import { Login } from './components/Login';
import { Portfolio } from './pages/Portfolio';
import { ETF } from './pages/ETF';
import { useEffect, useState } from 'react';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function ProtectedRoute({ children }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const password = useAuthStore((state) => state.password);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (password && !isAuthenticated) {
      // Revalidate stored password
      fetch('/health', { headers: { 'X-Password': password } })
        .then(res => {
          if (res.ok) {
            useAuthStore.setState({ isAuthenticated: true });
          } else {
            useAuthStore.getState().logout();
          }
        })
        .catch(() => useAuthStore.getState().logout())
        .finally(() => setChecking(false));
    } else {
      setChecking(false);
    }
  }, [password, isAuthenticated]);

  if (checking && password) {
    return <div className="loading">Checking authentication...</div>;
  }

  if (!isAuthenticated) {
    return <Login />;
  }

  return children;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={
            <ProtectedRoute>
              <Portfolio />
            </ProtectedRoute>
          } />
          <Route path="/etf" element={
            <ProtectedRoute>
              <ETF />
            </ProtectedRoute>
          } />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
