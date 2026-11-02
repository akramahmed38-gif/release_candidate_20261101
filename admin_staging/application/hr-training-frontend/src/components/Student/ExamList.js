import React, { useState, useEffect, useCallback } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  Typography,
} from '@mui/material';
import { AccessTime, CalendarMonth, Info, Refresh as RefreshIcon } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { examService } from '../../services/auth';

const statusToColor = (status = '') => {
  const normalized = status.toLowerCase();
  if (normalized === 'open') return 'success';
  if (normalized === 'on hold') return 'warning';
  if (normalized === 'closed') return 'default';
  return 'primary';
};

const formatDate = (value) => {
  if (!value) return '-';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString(undefined, {
        timeZone: 'Africa/Cairo',
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
};

const ExamList = () => {
  const navigate = useNavigate();
  const [exams, setExams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadExams = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await examService.getStudentExams();
      setExams(response.data.exams || []);
    } catch (err) {
      setError(
        err.response?.data?.message ||
          err.response?.data?.detail ||
          'Failed to load your exams. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadExams();
  }, [loadExams]);

  return (
    <Box>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 2,
          mb: 3,
        }}
      >
        <Box>
          <Typography variant="h4" fontWeight="bold">
            My Exams
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Only exams assigned to your HR ID are listed here.
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<Info />}
            onClick={() => navigate('/employee/contact')}
          >
            Contact Us
          </Button>
          <Button
            variant="contained"
            color="primary"
            startIcon={<RefreshIcon />}
            onClick={loadExams}
          >
            Refresh
          </Button>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}>
          <CircularProgress />
        </Box>
      ) : exams.length === 0 ? (
        <Card>
          <CardContent>
            <Typography variant="h6" fontWeight="bold" gutterBottom>
              No exams available
            </Typography>
            <Typography variant="body2" color="text.secondary">
              When an exam is assigned to your HR ID it will appear here automatically.
            </Typography>
          </CardContent>
        </Card>
      ) : (
        <Grid container spacing={3}>
          {exams.map((exam) => (
            <Grid item xs={12} md={6} key={exam.exam_id}>
              <Card
                elevation={2}
                sx={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  borderTop: '4px solid',
                  borderColor:
                    exam.exam_status?.toLowerCase() === 'open' ? 'success.main' : 'divider',
                }}
              >
                <CardContent sx={{ flexGrow: 1 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Chip
                      label={exam.exam_status}
                      color={statusToColor(exam.exam_status)}
                      size="small"
                    />
                    <Typography variant="caption" color="text.secondary">
                      Duration: {exam.duration_minutes} mins
                    </Typography>
                  </Box>
                  <Typography variant="h6" fontWeight="bold" gutterBottom>
                    {exam.title}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    {exam.description}
                  </Typography>

                  <Divider sx={{ my: 2 }} />

                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <CalendarMonth color="primary" fontSize="small" />
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          Starts
                        </Typography>
                        <Typography variant="body2" fontWeight={600}>
                          {formatDate(exam.start_date)}
                        </Typography>
                      </Box>
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <CalendarMonth color="primary" fontSize="small" />
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          Ends
                        </Typography>
                        <Typography variant="body2" fontWeight={600}>
                          {formatDate(exam.end_date)}
                        </Typography>
                      </Box>
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <AccessTime color="primary" fontSize="small" />
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          Materials
                        </Typography>
                        <Typography variant="body2" fontWeight={600}>
                          {exam.materials?.length || 0} linked files
                        </Typography>
                      </Box>
                    </Box>
                  </Box>
                </CardContent>
                <Box sx={{ p: 2, pt: 0 }}>
                  <Button
                    variant="contained"
                    fullWidth
                    onClick={() => navigate(`/employee/exams/${exam.exam_id}`)}
                  >
                    View Details
                  </Button>
                </Box>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
};

export default ExamList;
