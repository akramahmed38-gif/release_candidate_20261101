import React from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { Autorenew, Delete, Edit, Email, Visibility } from '@mui/icons-material';
import { EXAM_LEVELS, resolveExamLevel } from './examLevelConfig';

const ExamLevelTableDialog = ({
  open,
  onClose,
  level,
  exams,
  tr,
  isArabic,
  levelLabel,
  sortableColumns,
  sortConfig,
  onSort,
  formatDateTime,
  statusLabel,
  getStatusColor,
  onMoveLevel,
  onSendMail,
  onRegenerate,
  onOpenExam,
  onOpenEdit,
  onDelete,
  sendingMailExamId,
  regeneratingExamId,
  movingExamId,
  getLevelLabel,
}) => {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xl">
      <DialogTitle>
        <Stack spacing={0.5}>
          <Typography variant="h6" fontWeight={800}>
            {levelLabel}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {tr('Full exam list filtered by this level.', 'قائمة الاختبارات الكاملة بعد التصفية حسب هذا المستوى.')}
          </Typography>
        </Stack>
      </DialogTitle>
      <DialogContent dividers>
        <TableContainer>
          <Table sx={{ minWidth: 1080 }}>
            <TableHead>
              <TableRow>
                {sortableColumns.map((column) => (
                  <TableCell key={column.key}>
                    <TableSortLabel
                      active={sortConfig.key === column.key}
                      direction={sortConfig.key === column.key ? sortConfig.direction : 'asc'}
                      onClick={() => onSort(column.key)}
                    >
                      <strong>{column.label}</strong>
                    </TableSortLabel>
                  </TableCell>
                ))}
                <TableCell>
                  <strong>{tr('Move to', 'نقل إلى')}</strong>
                </TableCell>
                <TableCell align="right">
                  <strong>{tr('Actions', 'الإجراءات')}</strong>
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {exams.map((exam) => {
                const statusTone = getStatusColor(exam.exam_status);
                return (
                  <TableRow key={exam.exam_id} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight={700}>
                        {exam.title}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {(exam.description || '').substring(0, 60)}...
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography
                        component="span"
                        sx={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          px: 1.25,
                          py: 0.5,
                          borderRadius: 999,
                          fontSize: '0.75rem',
                          fontWeight: 800,
                          bgcolor: `${statusTone}.light`,
                          color: `${statusTone}.dark`,
                        }}
                      >
                        {statusLabel(exam.exam_status)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      {exam.duration_minutes} {tr('min', 'دقيقة')}
                    </TableCell>
                    <TableCell>{formatDateTime(exam.start_date, isArabic ? 'ar-EG' : 'en-US')}</TableCell>
                    <TableCell>{formatDateTime(exam.end_date, isArabic ? 'ar-EG' : 'en-US')}</TableCell>
                    <TableCell>{formatDateTime(exam.created_on || exam.created_at, isArabic ? 'ar-EG' : 'en-US')}</TableCell>
                    <TableCell>
                      <TextField
                        select
                        size="small"
                        value={resolveExamLevel(exam.exam_level)}
                        disabled={movingExamId === exam.exam_id}
                        onChange={(event) => onMoveLevel(exam.exam_id, event.target.value)}
                        sx={{ minWidth: 170 }}
                      >
                        {EXAM_LEVELS.map((levelOption) => (
                          <MenuItem
                            key={levelOption}
                            value={levelOption}
                            disabled={levelOption === resolveExamLevel(exam.exam_level)}
                          >
                            {getLevelLabel(levelOption)}
                          </MenuItem>
                        ))}
                      </TextField>
                    </TableCell>
                    <TableCell align="right">
                      <Stack
                        direction="row"
                        spacing={0.75}
                        justifyContent="flex-end"
                        alignItems="center"
                        flexWrap="wrap"
                      >
                        <Button
                          variant="outlined"
                          size="small"
                          startIcon={<Email />}
                          disabled={sendingMailExamId === exam.exam_id}
                          onClick={() => onSendMail(exam.exam_id)}
                          sx={{ whiteSpace: 'nowrap' }}
                        >
                          {sendingMailExamId === exam.exam_id
                            ? tr('Sending...', 'جارٍ الإرسال...')
                            : tr('Send Mail', 'إرسال بريد')}
                        </Button>
                        <Button
                          variant="outlined"
                          size="small"
                          startIcon={<Autorenew />}
                          disabled={regeneratingExamId === exam.exam_id}
                          onClick={() => onRegenerate(exam)}
                          sx={{ whiteSpace: 'nowrap' }}
                        >
                          {regeneratingExamId === exam.exam_id
                            ? tr('Regenerating...', 'جارٍ إعادة التوليد...')
                            : tr('Regenerate', 'إعادة توليد')}
                        </Button>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          <Tooltip title={tr('View', 'عرض')}>
                            <IconButton size="small" color="primary" onClick={() => onOpenExam(exam)}>
                              <Visibility fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title={tr('Edit', 'تعديل')}>
                            <IconButton size="small" color="secondary" onClick={() => onOpenEdit(exam)}>
                              <Edit fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title={tr('Delete', 'حذف')}>
                            <IconButton size="small" color="error" onClick={() => onDelete(exam.exam_id)}>
                              <Delete fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </Box>
                      </Stack>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="secondary">
          {tr('Close', 'إغلاق')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ExamLevelTableDialog;
