import React from 'react';
import { alpha, useTheme } from '@mui/material/styles';
import { Box, Button, Chip, Collapse, Stack, Typography } from '@mui/material';
import {
  ExpandMore,
  SchoolOutlined,
  WorkOutlineRounded,
  WorkspacePremiumOutlined,
} from '@mui/icons-material';
import ExamCard from './ExamCard';

const iconByLevel = {
  'Entry Level': SchoolOutlined,
  'Professional Level': WorkOutlineRounded,
  'Expert Level': WorkspacePremiumOutlined,
};

const ExamLevelColumn = ({
  level,
  exams,
  tr,
  isArabic,
  expanded,
  onToggle,
  levelLabel,
  levelSubtitle,
  statusLabel,
  getStatusColor,
  onOpenExam,
  onOpenEdit,
  onDelete,
  onSendMail,
  onRegenerate,
  onMoveLevel,
  sendingMailExamId,
  regeneratingExamId,
  movingExamId,
  onViewAll,
}) => {
  const theme = useTheme();
  const LevelIcon = iconByLevel[level] || SchoolOutlined;
  const panelId = `exam-level-panel-${level.replace(/\s+/g, '-').toLowerCase()}`;
  const headerId = `exam-level-header-${level.replace(/\s+/g, '-').toLowerCase()}`;

  return (
    <Box
      sx={{
        borderRadius: '12px',
        border: `0.5px solid ${alpha(theme.palette.secondary.main, 0.18)}`,
        backgroundColor: alpha(theme.palette.background.paper, 0.98),
        boxShadow: 'none',
        overflow: 'hidden',
      }}
    >
      <Box
        component="button"
        id={headerId}
        type="button"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={() => onToggle(level)}
        sx={{
          width: '100%',
          border: 'none',
          background: 'transparent',
          textAlign: 'inherit',
          p: 2.25,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 2,
          transition: 'background-color 200ms ease',
          '&:hover': {
            backgroundColor: alpha(theme.palette.primary.main, 0.04),
          },
          '&:focus-visible': {
            outline: `2px solid ${alpha(theme.palette.primary.main, 0.75)}`,
            outlineOffset: -2,
          },
        }}
      >
        <Stack direction="row" spacing={1.25} alignItems="flex-start" sx={{ minWidth: 0, flex: 1 }}>
          <Box
            sx={{
              width: 34,
              height: 34,
              borderRadius: '10px',
              border: `0.5px solid ${alpha(theme.palette.primary.main, 0.38)}`,
              backgroundColor: alpha(theme.palette.primary.main, 0.12),
              display: 'grid',
              placeItems: 'center',
              color: theme.palette.secondary.main,
              flexShrink: 0,
              mt: 0.25,
            }}
          >
            <LevelIcon fontSize="small" />
          </Box>

          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              flexWrap="wrap"
              sx={{ mb: 0.25 }}
            >
              <Typography variant="h6" fontWeight={800} sx={{ color: 'text.primary' }}>
                {levelLabel}
              </Typography>
              <Chip
                label={`(${exams.length})`}
                size="small"
                sx={{
                  height: 24,
                  fontWeight: 800,
                  color: theme.palette.secondary.main,
                  backgroundColor: alpha(theme.palette.primary.main, 0.18),
                  border: `0.5px solid ${alpha(theme.palette.primary.main, 0.32)}`,
                }}
              />
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ pr: 1 }}>
              {levelSubtitle}
            </Typography>
          </Box>
        </Stack>

        <ExpandMore
          sx={{
            color: 'text.secondary',
            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 200ms ease',
            flexShrink: 0,
          }}
        />
      </Box>

      <Collapse in={expanded} timeout={200} unmountOnExit>
        <Box
          id={panelId}
          role="region"
          aria-labelledby={headerId}
          sx={{
            px: 2.25,
            pb: 2.25,
            pt: 0,
          }}
        >
          <Stack spacing={1.25}>
            {exams.length === 0 ? (
              <Box
                sx={{
                  px: 1,
                  py: 2,
                  borderRadius: '8px',
                  border: `0.5px solid ${alpha(theme.palette.secondary.main, 0.14)}`,
                  backgroundColor: alpha(theme.palette.background.default, 0.55),
                }}
              >
                <Typography variant="body2" color="text.secondary">
                  {tr('No exams in this level yet', 'لا توجد اختبارات في هذا المستوى حتى الآن')}
                </Typography>
              </Box>
            ) : (
              exams.map((exam) => (
                <ExamCard
                  key={exam.exam_id}
                  exam={exam}
                  tr={tr}
                  isArabic={isArabic}
                  statusLabel={statusLabel}
                  getStatusColor={getStatusColor}
                  onOpen={onOpenExam}
                  onOpenEdit={onOpenEdit}
                  onDelete={onDelete}
                  onSendMail={onSendMail}
                  onRegenerate={onRegenerate}
                  onMoveLevel={onMoveLevel}
                  sendingMailExamId={sendingMailExamId}
                  regeneratingExamId={regeneratingExamId}
                  movingExamId={movingExamId}
                />
              ))
            )}

            <Box sx={{ display: 'flex', justifyContent: isArabic ? 'flex-start' : 'flex-end', pt: 0.5 }}>
              <Button
                variant="text"
                color="secondary"
                onClick={() => onViewAll(level)}
                sx={{
                  fontWeight: 800,
                  px: 0.5,
                  '&:hover': {
                    backgroundColor: 'transparent',
                    color: 'secondary.dark',
                  },
                }}
              >
                {tr(`View all ${exams.length}`, `عرض الكل ${exams.length}`)}
              </Button>
            </Box>
          </Stack>
        </Box>
      </Collapse>
    </Box>
  );
};

export default ExamLevelColumn;
