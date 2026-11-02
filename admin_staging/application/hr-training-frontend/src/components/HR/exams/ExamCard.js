import React from 'react';
import { alpha, useTheme } from '@mui/material/styles';
import {
  Box,
  Button,
  Chip,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { Autorenew, Delete, Edit, Email, Visibility } from '@mui/icons-material';
import { EXAM_LEVELS, getExamLevelLabel, resolveExamLevel } from './examLevelConfig';

const formatShortEndDate = (value, locale) => {
  if (!value) {
    return '-';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return '-';
  }
  return parsed.toLocaleDateString(locale, {
    timeZone: 'Africa/Cairo',
    month: 'short',
    day: 'numeric',
  });
};

const ExamCard = ({
  exam,
  tr,
  isArabic,
  statusLabel,
  getStatusColor,
  onOpen,
  onOpenEdit,
  onDelete,
  onSendMail,
  onRegenerate,
  onMoveLevel,
  sendingMailExamId,
  regeneratingExamId,
  movingExamId,
}) => {
  const theme = useTheme();
  const locale = isArabic ? 'ar-EG' : 'en-US';
  const resolvedLevel = resolveExamLevel(exam.exam_level);

  return (
    <Box
      onClick={() => onOpen(exam)}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpen(exam);
        }
      }}
      sx={{
        p: 1.75,
        borderRadius: '8px',
        border: `0.5px solid ${alpha(theme.palette.secondary.main, 0.18)}`,
        backgroundColor: theme.palette.background.paper,
        cursor: 'pointer',
        transition: 'border-color 180ms ease, background-color 180ms ease',
        '&:hover': {
          borderColor: alpha(theme.palette.primary.main, 0.5),
          backgroundColor: alpha(theme.palette.primary.main, 0.04),
        },
        '&:focus-visible': {
          outline: `2px solid ${alpha(theme.palette.primary.main, 0.8)}`,
          outlineOffset: 2,
        },
      }}
    >
      <Stack spacing={1.25}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
          <Stack spacing={0.5} sx={{ minWidth: 0, flex: 1 }}>
            <Typography
              variant="subtitle2"
              fontWeight={800}
              sx={{
                color: 'text.primary',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                lineHeight: 1.35,
              }}
            >
              {exam.title}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {exam.duration_minutes} {tr('min', 'دقيقة')} · {tr('ends', 'ينتهي')} {formatShortEndDate(exam.end_date, locale)}
            </Typography>
          </Stack>
          <Chip
            size="small"
            label={statusLabel(exam.exam_status)}
            color={getStatusColor(exam.exam_status)}
            sx={{ fontWeight: 800, flexShrink: 0 }}
          />
        </Stack>

        <Stack
          direction={{ xs: 'column', lg: 'row' }}
          spacing={1}
          alignItems={{ xs: 'stretch', lg: 'center' }}
          justifyContent="space-between"
        >
          <TextField
            select
            size="small"
            label={tr('Move to', 'نقل إلى')}
            value={resolvedLevel}
            disabled={movingExamId === exam.exam_id}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => {
              event.stopPropagation();
              onMoveLevel(exam.exam_id, event.target.value);
            }}
            sx={{
              minWidth: { xs: '100%', sm: 190 },
              '& .MuiInputBase-root': {
                borderRadius: 999,
                backgroundColor: alpha(theme.palette.background.default, 0.72),
              },
            }}
          >
            {EXAM_LEVELS.map((levelOption) => (
              <MenuItem
                key={levelOption}
                value={levelOption}
                disabled={levelOption === resolvedLevel}
              >
                {getExamLevelLabel(levelOption, tr)}
              </MenuItem>
            ))}
          </TextField>

          <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
            <Button
              variant="outlined"
              size="small"
              startIcon={<Email />}
              disabled={sendingMailExamId === exam.exam_id}
              onClick={(event) => {
                event.stopPropagation();
                onSendMail(exam.exam_id);
              }}
              sx={{ borderRadius: 999, whiteSpace: 'nowrap' }}
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
              onClick={(event) => {
                event.stopPropagation();
                onRegenerate(exam);
              }}
              sx={{ borderRadius: 999, whiteSpace: 'nowrap' }}
            >
              {regeneratingExamId === exam.exam_id
                ? tr('Regenerating...', 'جارٍ إعادة التوليد...')
                : tr('Regenerate', 'إعادة توليد')}
            </Button>

            <Tooltip title={tr('View', 'عرض')}>
              <IconButton
                size="small"
                color="primary"
                onClick={(event) => {
                  event.stopPropagation();
                  onOpen(exam);
                }}
              >
                <Visibility fontSize="small" />
              </IconButton>
            </Tooltip>

            <Tooltip title={tr('Edit', 'تعديل')}>
              <IconButton
                size="small"
                color="secondary"
                onClick={(event) => {
                  event.stopPropagation();
                  onOpenEdit(exam);
                }}
              >
                <Edit fontSize="small" />
              </IconButton>
            </Tooltip>

            <Tooltip title={tr('Delete', 'حذف')}>
              <IconButton
                size="small"
                color="error"
                onClick={(event) => {
                  event.stopPropagation();
                  onDelete(exam.exam_id);
                }}
              >
                <Delete fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
        </Stack>
      </Stack>
    </Box>
  );
};

export default ExamCard;
