import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Grid,
  Typography,
} from '@mui/material';
import { Email, Phone } from '@mui/icons-material';
import { useLanguage } from '../context/LanguageContext';

const ContactUs = () => {
  const { t, isArabic } = useLanguage();
  const tr = (en, ar) => t(en, ar);
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
        direction: isArabic ? 'rtl' : 'ltr',
        textAlign: isArabic ? 'right' : 'left',
      }}
    >
      <Typography variant="h4" fontWeight="bold" gutterBottom>
        {tr('Contact Us', 'تواصل معنا')}
      </Typography>


      <Grid container spacing={4}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>
                {tr('Get in touch', 'ابقَ على تواصل')}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                {tr(
                  'Our HR coordinators are here to help with exam access, materials, and general questions.',
                  'منسقو الموارد البشرية هنا لمساعدتك في الوصول للاختبارات والمواد والأسئلة العامة.'
                )}
              </Typography>

              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2, flexDirection: isArabic ? 'row-reverse' : 'row' }}>
                <Email color="primary" />
                <Box>
                  <Typography fontWeight={600} dir="ltr">Mahenar.Gamal@Fawry.com, Haidy.Nagiub@Fawry.com</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {tr('Preferred contact method', 'طريقة التواصل المفضلة')}
                  </Typography>
                </Box>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexDirection: isArabic ? 'row-reverse' : 'row' }}>
                <Phone color="primary" />
                <Box>
                  <Typography fontWeight={600} dir="ltr">01026367493</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {tr('Sunday to Thursday, 9:00 AM - 5:00 PM', 'من الأحد إلى الخميس، 9:00 ص - 5:00 م')}
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
