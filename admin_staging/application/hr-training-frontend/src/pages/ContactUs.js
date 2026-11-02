import React, { useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  Grid,
  TextField,
  Typography,
  Button,
} from '@mui/material';
import { Email, Phone } from '@mui/icons-material';

const ContactUs = () => {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    message: '',
  });
  const [submitted, setSubmitted] = useState(false);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    setSubmitted(true);
    setFormData({ name: '', email: '', message: '' });
  };

  return (
    <Box
      sx={{
        maxWidth: 1100,
        mx: 'auto',
        px: { xs: 2, sm: 3 },
        py: { xs: 2, sm: 3 },
      }}
    >
      <Typography variant="h4" fontWeight="bold" gutterBottom>
        Contact Us
      </Typography>


      <Grid container spacing={4}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>
                Get in touch
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Our HR coordinators are here to help with exam access, materials, and general questions.
              </Typography>

              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                <Email color="primary" />
                <Box>
                  <Typography fontWeight={600}>Mahenar.Gamal@Fawry.com, Haidy.Nagiub@Fawry.com</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Preferred contact method
                  </Typography>
                </Box>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Phone color="primary" />
                <Box>
                  <Typography fontWeight={600}>+201111111111</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Sunday to Thursday, 9:00 AM - 5:00 PM
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>


      </Grid>
    </Box>
  );
};

export default ContactUs;
