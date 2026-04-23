import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';

export default function ProtectedRoute({ children, roles }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading || user === null) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-brand-500 font-display text-lg animate-pulse" data-testid="auth-loader">Cargando…</div>
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  if (roles && roles.length && !roles.includes(user.role)) {
    // redirect to appropriate home
    const fallback = user.role === 'super_admin' ? '/master' : '/app/dashboard';
    return <Navigate to={fallback} replace />;
  }
  return children;
}
