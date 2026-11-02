import { Navigate } from 'react-router-dom';
import { authService } from '../services/auth';

const ProtectedRoute = ({ children, allowedRoles }) => {
  const hasSession = authService.hasValidSession();
  const user = authService.getCurrentUser();
  const rawRole = (user?.role || user?.department || '').toLowerCase();
  const normalizedRole = rawRole === 'employee' ? 'retail' : rawRole;

  if (!hasSession || !user) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles) {
    const allowed = allowedRoles.map((role) => role.toLowerCase());
    if (!normalizedRole || !allowed.includes(normalizedRole)) {
      const fallbackPath = normalizedRole === 'retail' ? '/employee/exams' : '/dashboard';
      return <Navigate to={fallbackPath} replace />;
    }
  }

  return children;
};

export default ProtectedRoute;
