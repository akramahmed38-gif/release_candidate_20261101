import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';
import { theme } from './utils/theme';
import ProtectedRoute from './utils/ProtectedRoute';
import Layout from './components/Layout/Layout.js';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import UserManagement from './components/Admin/UserManagement';
import AuditTrail from './components/Admin/AuditTrail';
import ResignedUsers from './components/Admin/ResignedUsers.jsx';
import MaterialManagement from './components/HR/MaterialManagement';
import VideoPlayer from './components/HR/VideoPlayer';
import DailyBriefManagement from './components/HR/DailyBriefManagement';
import DailyBriefVideoPlayer from './components/HR/DailyBriefVideoPlayer';
import DailyBriefPage from './pages/DailyBriefPage';
import DailyBriefBuilder from './dailyBrief/DailyBriefBuilder';
import DailyBriefAudience from './dailyBrief/DailyBriefAudience';
import DailyBriefPreviewPage from './dailyBrief/DailyBriefPreviewPage';
import BusinessVocabulary from './pages/BusinessVocabulary';
import ExamManagement from './components/HR/ExamManagement';
import QuestionBank from './components/HR/QuestionBank';
import EmployeePerformance from './components/HR/EmployeePerformance';
import CreateExam from './components/HR/CreateExam';
import EditExam from './components/HR/EditExam';
import ExamList from './components/Student/ExamList.jsx';
import ExamDetails from './components/Student/ExamDetails.jsx';
import ChangePassword from './pages/ChangePassword';
import ContactUs from './pages/ContactUs';
import { LanguageProvider } from './context/LanguageContext';

const employeeRoles = ['retail', 'employee'];
const materialViewerRoles = ['admin', 'auditor', 'hr', 'manager', 'retail', 'employee'];

function App() {
  const basename = import.meta.env.VITE_BASENAME || '/training';

  return (
    <LanguageProvider>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <BrowserRouter basename={basename}>
          <Routes>
            <Route path="/login" element={<Login />} />
            
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute allowedRoles={['admin', 'auditor', 'hr', 'manager']}>
                  <Layout>
                    <Dashboard />
                  </Layout>
                </ProtectedRoute>
              }
            />

          <Route
            path="/change-password"
            element={
              <ProtectedRoute>
                <Layout>
                  <ChangePassword />
                </Layout>
              </ProtectedRoute>
            }
          />

          {/* Admin Routes */}
          <Route
            path="/admin/users"
            element={
              <ProtectedRoute allowedRoles={['admin', 'auditor', 'hr']}>
                <Layout>
                  <UserManagement />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/audit"
            element={
              <ProtectedRoute allowedRoles={['admin']}>
                <Layout>
                  <AuditTrail />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/resigned-users"
            element={
              <ProtectedRoute allowedRoles={['admin', 'auditor']}>
                <Layout>
                  <ResignedUsers />
                </Layout>
              </ProtectedRoute>
            }
          />

          {/* HR Routes */}
          <Route
            path="/materials"
            element={
              <ProtectedRoute allowedRoles={materialViewerRoles}>
                <Layout>
                  <MaterialManagement />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/hr/materials"
            element={
              <ProtectedRoute allowedRoles={materialViewerRoles}>
                <Layout>
                  <MaterialManagement />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/daily-brief"
            element={
              <ProtectedRoute allowedRoles={materialViewerRoles}>
                <Layout>
                  <DailyBriefPage />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/business-vocabulary"
            element={
              <ProtectedRoute allowedRoles={materialViewerRoles}>
                <Layout><BusinessVocabulary /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/daily-brief/audience"
            element={<ProtectedRoute allowedRoles={['admin', 'auditor', 'hr']}><Layout><DailyBriefAudience /></Layout></ProtectedRoute>}
          />
          <Route
            path="/daily-brief/new"
            element={
              <ProtectedRoute allowedRoles={['admin', 'auditor', 'hr']}>
                <Layout><DailyBriefBuilder /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/daily-brief/preview"
            element={<ProtectedRoute allowedRoles={['admin', 'auditor', 'hr']}><Layout><DailyBriefPreviewPage /></Layout></ProtectedRoute>}
          />
          <Route
            path="/daily-brief/:briefId/edit"
            element={
              <ProtectedRoute allowedRoles={['admin', 'auditor', 'hr']}>
                <Layout><DailyBriefBuilder /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/daily-brief/:briefId/preview"
            element={
              <ProtectedRoute allowedRoles={['admin', 'auditor', 'hr']}>
                <Layout><DailyBriefPreviewPage /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/script-book"
            element={
              <ProtectedRoute allowedRoles={materialViewerRoles}>
                <Layout><DailyBriefManagement /></Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/materials/player"
            element={
              <ProtectedRoute allowedRoles={materialViewerRoles}>
                <Layout>
                  <VideoPlayer />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/hr/materials/player"
            element={
              <ProtectedRoute allowedRoles={materialViewerRoles}>
                <Layout>
                  <VideoPlayer />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/script-book/player"
            element={
              <ProtectedRoute allowedRoles={materialViewerRoles}>
                <Layout>
                  <DailyBriefVideoPlayer />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/hr/exams"
            element={
              <ProtectedRoute allowedRoles={['admin', 'auditor', 'hr']}>
                <Layout>
                  <ExamManagement />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/hr/question-bank"
            element={<ProtectedRoute allowedRoles={['admin', 'auditor', 'hr']}><Layout><QuestionBank /></Layout></ProtectedRoute>}
          />
          <Route
            path="/hr/employee-performance"
            element={
              <ProtectedRoute allowedRoles={['admin', 'auditor', 'hr']}>
                <Layout>
                  <EmployeePerformance />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/hr/exams/create"
            element={
              <ProtectedRoute allowedRoles={['admin', 'auditor', 'hr']}>
                <Layout>
                  <CreateExam />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/hr/exams/:examId"
            element={
              <ProtectedRoute allowedRoles={['admin', 'auditor', 'hr']}>
                <Layout>
                  <ExamDetails />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/hr/exams/edit/:examId"
            element={
              <ProtectedRoute allowedRoles={['admin', 'auditor', 'hr']}>
                <Layout>
                  <EditExam />
                </Layout>
              </ProtectedRoute>
            }
          />

          {/* Employee Routes */}
          <Route
            path="/employee/exams"
            element={
              <ProtectedRoute allowedRoles={employeeRoles}>
                <Layout>
                  <ExamList />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/employee/exams/:examId"
            element={
              <ProtectedRoute allowedRoles={employeeRoles}>
                <Layout>
                  <ExamDetails />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/employee/contact"
            element={
              <ProtectedRoute allowedRoles={employeeRoles}>
                <Layout>
                  <ContactUs />
                </Layout>
              </ProtectedRoute>
            }
          />

            <Route path="/" element={<Navigate to="/login" replace />} />
          </Routes>
        </BrowserRouter>
      </ThemeProvider>
    </LanguageProvider>
  );
}

export default App;
