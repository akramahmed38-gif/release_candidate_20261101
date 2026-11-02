import React from 'react';
import { Box, Typography } from '@mui/material';

const Footer = () => (
  <Box
    component="footer"
    sx={{
      width: '100%',
      borderTop: '1px solid rgba(31,53,88,0.12)',
      background: 'linear-gradient(180deg, rgba(255,255,255,0.92), rgba(255,249,231,0.82))',
      backdropFilter: 'blur(10px)',
      mt: { xs: 2, md: 3 },
      py: { xs: 2, md: 2.5 },
      px: 2,
      textAlign: 'center',
    }}
  >
    <Typography
      sx={{
        fontSize: { xs: 12, md: 13 },
        color: '#667085',
        fontWeight: 700,
        letterSpacing: '0.01em',
      }}
    >
      Developed and Powered by FP Automation Team
    </Typography>
  </Box>
);

export default Footer;
