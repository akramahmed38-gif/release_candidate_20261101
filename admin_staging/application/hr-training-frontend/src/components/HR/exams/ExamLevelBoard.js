import React, { useMemo, useState } from 'react';
import { Stack } from '@mui/material';
import ExamLevelColumn from './ExamLevelColumn';
import ExamLevelTableDialog from './ExamLevelTableDialog';
import {
  EXAM_LEVELS,
  getExamLevelLabel,
  getExamLevelSubtitle,
  resolveExamLevel,
} from './examLevelConfig';

const ExamLevelBoard = ({
  exams,
  tr,
  isArabic,
  allowMultipleOpen = false,
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
}) => {
  const [activeTableLevel, setActiveTableLevel] = useState(null);
  const [expandedLevel, setExpandedLevel] = useState(null);

  const groupedExams = useMemo(() => {
    const grouped = EXAM_LEVELS.reduce((accumulator, level) => {
      accumulator[level] = [];
      return accumulator;
    }, {});

    exams.forEach((exam) => {
      grouped[resolveExamLevel(exam.exam_level)].push(exam);
    });

    return grouped;
  }, [exams]);

  const handleToggleLevel = (level) => {
    if (allowMultipleOpen) {
      setExpandedLevel((previous) => {
        const current = previous && typeof previous === 'object' ? previous : {};
        return {
          ...current,
          [level]: !current[level],
        };
      });
      return;
    }
    setExpandedLevel((previous) => (previous === level ? null : level));
  };

  const isLevelExpanded = (level) => {
    if (allowMultipleOpen) {
      return Boolean(expandedLevel && typeof expandedLevel === 'object' && expandedLevel[level]);
    }
    return expandedLevel === level;
  };

  const filteredExams = activeTableLevel ? groupedExams[activeTableLevel] || [] : [];

  return (
    <>
      <Stack spacing={2}>
        {EXAM_LEVELS.map((level) => (
          <ExamLevelColumn
            key={level}
            level={level}
            exams={groupedExams[level] || []}
            tr={tr}
            isArabic={isArabic}
            expanded={isLevelExpanded(level)}
            onToggle={handleToggleLevel}
            levelLabel={getExamLevelLabel(level, tr)}
            levelSubtitle={getExamLevelSubtitle(level, tr)}
            statusLabel={statusLabel}
            getStatusColor={getStatusColor}
            onOpenExam={onOpenExam}
            onOpenEdit={onOpenEdit}
            onDelete={onDelete}
            onSendMail={onSendMail}
            onRegenerate={onRegenerate}
            onMoveLevel={onMoveLevel}
            sendingMailExamId={sendingMailExamId}
            regeneratingExamId={regeneratingExamId}
            movingExamId={movingExamId}
            onViewAll={setActiveTableLevel}
          />
        ))}
      </Stack>

      <ExamLevelTableDialog
        open={Boolean(activeTableLevel)}
        onClose={() => setActiveTableLevel(null)}
        level={activeTableLevel}
        exams={filteredExams}
        tr={tr}
        isArabic={isArabic}
        levelLabel={activeTableLevel ? getExamLevelLabel(activeTableLevel, tr) : ''}
        sortableColumns={sortableColumns}
        sortConfig={sortConfig}
        onSort={onSort}
        formatDateTime={formatDateTime}
        statusLabel={statusLabel}
        getStatusColor={getStatusColor}
        onMoveLevel={onMoveLevel}
        onSendMail={onSendMail}
        onRegenerate={onRegenerate}
        onOpenExam={onOpenExam}
        onOpenEdit={onOpenEdit}
        onDelete={onDelete}
        sendingMailExamId={sendingMailExamId}
        regeneratingExamId={regeneratingExamId}
        movingExamId={movingExamId}
        getLevelLabel={(value) => getExamLevelLabel(value, tr)}
      />
    </>
  );
};

export default ExamLevelBoard;
