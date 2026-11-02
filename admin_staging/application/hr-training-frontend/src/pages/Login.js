import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Alert,
  Container,
  Stack,
} from '@mui/material';
import { authService } from '../services/auth';
import { useLanguage } from '../context/LanguageContext';
import LanguageToggle from '../components/Common/LanguageToggle';
import Footer from '../components/Layout/Footer';

const Login = () => {
  const navigate = useNavigate();
  const { t, isArabic } = useLanguage();
  const tr = (en, ar) => t(en, ar);
  const managerEmail = 'management';

  const [email, setEmail] = useState('');
  const [secret, setSecret] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [requestingOtp, setRequestingOtp] = useState(false);
  const [otpRequested, setOtpRequested] = useState(false);

  const normalizedEmail = email.trim();
  const usesPasswordLogin = ['training.admin', managerEmail].includes(normalizedEmail.toLowerCase());

  const resetOtpFlow = () => {
    setSecret('');
    setOtpRequested(false);
    setInfo('');
  };

  const handleEmailChange = (value) => {
    const nextNormalized = (value || '').trim();
    const nextUsesPasswordLogin = ['training.admin', managerEmail].includes(nextNormalized.toLowerCase());
    setEmail(value);
    setError('');
    if (!nextUsesPasswordLogin) {
      resetOtpFlow();
    } else {
      setSecret('');
      setInfo('');
    }
  };

  const handleRequestOtp = async () => {
    setError('');
    setInfo('');

    if (!normalizedEmail) {
      setError(tr('Email is required.', 'البريد الإلكتروني مطلوب.'));
      return;
    }

    if (usesPasswordLogin) {
      setError(tr('This account uses password login only.', 'دخول الأدمن بكلمة المرور فقط.'));
      return;
    }

    setRequestingOtp(true);
    try {
      const response = await authService.requestOtp(normalizedEmail);
      setOtpRequested(true);
      setInfo(response?.data?.message || tr('OTP sent successfully', 'تم إرسال رمز التحقق بنجاح'));
    } catch (err) {
      setError(
        err.response?.data?.message ||
          err.response?.data?.detail ||
          err.message ||
          tr('Failed to send OTP. Please try again.', 'فشل إرسال رمز التحقق. حاول مرة أخرى.')
      );
    } finally {
      setRequestingOtp(false);
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    setInfo('');

    if (!normalizedEmail) {
      setError(tr('Email is required.', 'البريد الإلكتروني مطلوب.'));
      return;
    }

    if (usesPasswordLogin) {
      if (!secret.trim()) {
        setError(tr('Password is required for this login.', 'كلمة المرور مطلوبة لدخول الأدمن.'));
        return;
      }
    } else {
      if (!otpRequested) {
        setError(tr('Please request OTP first.', 'يرجى طلب رمز التحقق أولاً.'));
        return;
      }
      if (!secret.trim()) {
        setError(tr('OTP is required.', 'رمز التحقق مطلوب.'));
        return;
      }
    }

    setLoading(true);
    try {
      const loginEmail = normalizedEmail;
      const response = await authService.login(loginEmail, secret.trim());

      if (response?.data?.access_token) {
        const loggedInUser = authService.getCurrentUser();
        const rawRole = (loggedInUser?.role || loggedInUser?.department || '').toLowerCase();
        const normalizedRole = rawRole === 'employee' ? 'retail' : rawRole;
        navigate(normalizedRole === 'retail' ? '/daily-brief' : '/dashboard');
        return;
      }

      setError(
        response?.data?.message ||
          tr('Login failed. Please try again.', 'فشل تسجيل الدخول. حاول مرة أخرى.')
      );
    } catch (err) {
      setError(
        err.response?.data?.message ||
          err.response?.data?.detail ||
          err.message ||
          tr('Login failed. Please try again.', 'فشل تسجيل الدخول. حاول مرة أخرى.')
      );
    } finally {
      setLoading(false);
    }
  };

  const showOtpFlow = !usesPasswordLogin;

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        direction: isArabic ? 'rtl' : 'ltr',
        background:
          'radial-gradient(circle at 18% 12%, rgba(255,210,0,0.18) 0%, rgba(255,249,231,0.90) 30%, rgba(255,255,255,0.98) 62%, rgba(247,242,233,0.96) 100%)',
      }}
    >
      <Box sx={{ flex: 1, width: '100%', display: 'flex', alignItems: 'center' }}>
        <Container maxWidth="sm">
          <Box sx={{ display: 'flex', justifyContent: isArabic ? 'flex-start' : 'flex-end', mb: 1.5 }}>
            <LanguageToggle compact />
          </Box>

          <Card
            elevation={0}
            sx={{
              borderRadius: 4,
              border: '1px solid rgba(31,53,88,0.12)',
              boxShadow: '0 28px 58px rgba(31,53,88,0.12)',
              backdropFilter: 'blur(12px)',
              background: 'linear-gradient(180deg, rgba(255,255,255,0.98), rgba(255,252,246,0.96))',
            }}
          >
            <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
              <Stack alignItems="center" spacing={1.5} sx={{ mb: 3 }}>
                <img src="/assets/logo.png" alt="Logo" style={{ height: 72, borderRadius: 8 }} />
                <Typography variant="h4" fontWeight={800} textAlign="center" sx={{ color: 'secondary.dark' }}>
                  {tr('Training System', 'نظام التدريب')}
                </Typography>
                <Typography variant="body2" color="text.secondary" textAlign="center">
                  {tr('Sign in to continue', 'سجل الدخول للمتابعة')}
                </Typography>
              </Stack>

              {error && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {error}
                </Alert>
              )}
              {info && (
                <Alert severity="success" sx={{ mb: 2 }}>
                  {info}
                </Alert>
              )}

              <form onSubmit={handleLogin}>
                <TextField
                  fullWidth
                  label={tr('Email', 'البريد الإلكتروني')}
                  variant="outlined"
                  value={email}
                  onChange={(e) => handleEmailChange(e.target.value)}
                  margin="normal"
                  required
                />

                {showOtpFlow && !otpRequested && (
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                    {tr(
                      'Press Send OTP to receive your verification code.',
                      'اضغط إرسال رمز التحقق لاستلام الكود.'
                    )}
                  </Typography>
                )}

                {usesPasswordLogin ? (
                  <>
                    <TextField
                      fullWidth
                      label={tr('Password', 'كلمة المرور')}
                      variant="outlined"
                      value={secret}
                      onChange={(e) => setSecret(e.target.value)}
                      type="password"
                      margin="normal"
                      helperText={tr('Admin and manager accounts use password only.', 'دخول الأدمن بكلمة المرور فقط.')}
                    />

                    <Button
                      fullWidth
                      variant="contained"
                      size="large"
                      type="submit"
                      disabled={loading}
                      sx={{
                        mt: 3,
                        borderRadius: 3,
                        py: 1.25,
                        fontWeight: 800,
                        fontSize: 18,
                        color: 'secondary.dark',
                      }}
                    >
                      {loading ? tr('Signing In...', 'جاري تسجيل الدخول...') : tr('Sign In', 'دخول')}
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      fullWidth
                      variant="outlined"
                      size="large"
                      type="button"
                      onClick={handleRequestOtp}
                      disabled={requestingOtp || loading || !normalizedEmail}
                      sx={{
                        mt: 2,
                        borderRadius: 3,
                        py: 1.25,
                        fontWeight: 800,
                        fontSize: 18,
                        borderColor: 'rgba(31,53,88,0.18)',
                        color: 'secondary.main',
                        backgroundColor: 'rgba(255,255,255,0.84)',
                      }}
                    >
                      {otpRequested ? tr('Resend OTP', 'إعادة إرسال رمز التحقق') : tr('Send OTP', 'إرسال رمز التحقق')}
                    </Button>

                    {otpRequested && (
                      <>
                        <TextField
                          fullWidth
                          label={tr('OTP', 'رمز التحقق')}
                          variant="outlined"
                          value={secret}
                          onChange={(e) => setSecret(e.target.value)}
                          margin="normal"
                          inputProps={{ inputMode: 'numeric' }}
                          helperText={tr('Enter the OTP sent to your email.', 'ادخل رمز التحقق المرسل إلى بريدك.')}
                        />

                        <Button
                          fullWidth
                          variant="contained"
                          size="large"
                          type="submit"
                          disabled={loading || !secret.trim()}
                          sx={{
                            mt: 3,
                            borderRadius: 3,
                            py: 1.25,
                            fontWeight: 800,
                            fontSize: 18,
                            color: 'secondary.dark',
                          }}
                        >
                          {loading ? tr('Signing In...', 'جاري تسجيل الدخول...') : tr('Sign In', 'دخول')}
                        </Button>
                      </>
                    )}
                  </>
                )}

                <Box sx={{ mt: 1.5, textAlign: 'center' }}>
                  <Button
                    component="a"
                    href={`/?lang=${isArabic ? 'ar' : 'en'}`}
                    variant="text"
                    sx={{ fontWeight: 700 }}
                  >
                    {tr('Back to Main Portal Menu', 'الرجوع إلى القائمة الرئيسية للبوابة')}
                  </Button>
                </Box>
              </form>
            </CardContent>
          </Card>
        </Container>
      </Box>
      <Footer />
    </Box>
  );
};

export default Login;
