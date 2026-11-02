import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { CircularProgress, Box, Alert } from '@mui/material';
import { examService } from '../../services/auth';
import CreateExam from './CreateExam';
import { useLanguage } from '../../context/LanguageContext';

const EditExam = () => {
  const { examId } = useParams();
  const navigate = useNavigate();
  const { t, isArabic } = useLanguage();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [examData, setExamData] = useState(null);

  const loadExam = useCallback(async () => {
    try {
      setLoading(true);
      const response = await examService.getExamById(examId);
      setExamData(response.data.exam);
    } catch (error) {
      console.error('Error loading exam:', error);
      setError(t('Failed to load exam. Redirecting...', 'تعذر تحميل الاختبار. جارٍ التحويل...'));
      setTimeout(() => navigate('/hr/exams'), 2000);
    } finally {
      setLoading(false);
    }
  }, [examId, navigate, t]);

  useEffect(() => {
    loadExam();
  }, [loadExam]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <CircularProgress size={60} />
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ p: 3, direction: isArabic ? 'rtl' : 'ltr' }}>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  return <CreateExam editMode={true} initialData={examData} examId={examId} />;
};

export default EditExam;
