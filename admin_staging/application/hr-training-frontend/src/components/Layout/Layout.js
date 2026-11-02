import React from 'react';
import { Box } from '@mui/material';
import Navbar from './Navbar';
import Footer from './Footer';
import ChatbotWidget from '../Chatbot/ChatbotWidgetModern.jsx';
import { useLanguage } from '../../context/LanguageContext';

import { authService } from '../../services/auth';

const Layout = ({ children }) => {
  const { isArabic } = useLanguage();
  const user = authService.getCurrentUser();
  const chatbotWidgetEnabled = user?.chatbot_test_access === true && user?.department === 'admin';

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />

      <Box
        component="main"
        sx={{
          flex: 1,
          position: 'relative',
          overflow: 'hidden',
          pt: { xs: 2.5, md: 3.5 },
          px: { xs: 1.5, sm: 2.5, md: 3.5 },
          pb: { xs: 3, md: 5 },
          background:
            'radial-gradient(circle at top left, rgba(255,210,0,0.16) 0%, rgba(255,249,231,0.86) 22%, rgba(255,255,255,0.96) 58%, rgba(247,242,233,0.92) 100%)',
          direction: isArabic ? 'rtl' : 'ltr',
        }}
      >
        <Box
          sx={{
            width: '100%',
            maxWidth: 1480,
            mx: 'auto',
            position: 'relative',
            zIndex: 1,
          }}
        >
          {children}
        </Box>
      </Box>

      <Footer />
      {chatbotWidgetEnabled ? <ChatbotWidget key={user?.employee_id || user?.hr_id || user?.email} /> : null}
    </Box>
  );
};

export default Layout;
