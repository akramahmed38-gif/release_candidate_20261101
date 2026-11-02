export const getRoleHomeRoute = (role) => {
  const normalizedRole = role?.toLowerCase();

  switch (normalizedRole) {
    case 'retail':
    case 'employee':
      return '/employee/exams';
    case 'admin':
    case 'hr':
    default:
      return '/dashboard';
  }
};
