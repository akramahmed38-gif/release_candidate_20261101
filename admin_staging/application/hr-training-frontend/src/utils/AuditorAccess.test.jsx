import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Navbar from '../components/Layout/Navbar.jsx';
import ProtectedRoute from './ProtectedRoute';

let mockRole = 'auditor';
vi.mock('../services/auth', () => ({ authService: {
  getCurrentUser: () => ({ role: mockRole, email: 'viewer@example.com' }),
  hasValidSession: () => true,
} }));
vi.mock('../context/LanguageContext', () => ({ useLanguage: () => ({ t: (en) => en, isArabic: false }) }));
vi.mock('../components/Common/LanguageToggle', () => ({ default: () => null }));
vi.mock('@mui/material/useMediaQuery', () => ({ default: () => false }));

describe('Auditor access', () => {
  afterEach(() => vi.clearAllMocks());
  it.each(['admin', 'auditor'])('%s has management links with audit reserved for admin', (role) => {
    mockRole = role;
    render(<MemoryRouter><Navbar /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: 'Management' }));
    expect(screen.getByRole('menuitem', { name: 'User Management' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Employee Performance' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Resigned Users' })).toBeInTheDocument();
    if (role === 'admin') expect(screen.getByRole('menuitem', { name: 'Audit Trail' })).toBeInTheDocument();
    else expect(screen.queryByRole('menuitem', { name: 'Audit Trail' })).not.toBeInTheDocument();
  });
  it('redirects Auditor from an admin-only audit route', () => {
    mockRole = 'auditor';
    render(<MemoryRouter initialEntries={['/admin/audit']}><Routes>
      <Route path="/admin/audit" element={<ProtectedRoute allowedRoles={['admin']}><div>Audit content</div></ProtectedRoute>} />
      <Route path="/dashboard" element={<div>Dashboard fallback</div>} />
    </Routes></MemoryRouter>);
    expect(screen.getByText('Dashboard fallback')).toBeInTheDocument();
    expect(screen.queryByText('Audit content')).not.toBeInTheDocument();
  });
});
