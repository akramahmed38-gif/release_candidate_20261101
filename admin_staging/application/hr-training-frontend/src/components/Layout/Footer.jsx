import React from 'react';
import { Box, Typography } from '@mui/material';

const Footer = () => (
  <Box
    component="footer"
    sx={{
      width: '100%',
      borderTop: '1px solid rgba(11,79,168,0.14)',
      background: 'rgba(255,255,255,0.9)',
      py: 1.2,
      px: 2,
      textAlign: 'center',
    }}
  >
    <Typography
      sx={{
        fontSize: { xs: 12, md: 13 },
        color: '#4f6586',
        fontWeight: 600,
      }}
    >
      Developed and Powered by FP Automation Team
    </Typography>
  </Box>
);

export default Footer;
