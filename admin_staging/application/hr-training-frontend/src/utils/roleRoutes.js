export const getRoleHomeRoute = (role) => {
  const normalizedRole = role?.toLowerCase();

  switch (normalizedRole) {
    case 'retail':
    case 'employee':
      return '/daily-brief';
    case 'admin':
    case 'hr':
    default:
      return '/dashboard';
  }
};
