export const EXAM_LEVELS = ['Entry Level', 'Professional Level', 'Expert Level'];
export const DEFAULT_EXAM_LEVEL = EXAM_LEVELS[0];

export const resolveExamLevel = (value) =>
  EXAM_LEVELS.includes(value) ? value : DEFAULT_EXAM_LEVEL;

export const getExamLevelLabel = (level, tr) => {
  if (level === 'Professional Level') {
    return tr('Professional Level', 'مستوى احترافي');
  }
  if (level === 'Expert Level') {
    return tr('Expert Level', 'مستوى خبير');
  }
  return tr('Entry Level', 'مستوى مبتدئ');
};

export const getExamLevelSubtitle = (level, tr) => {
  if (level === 'Professional Level') {
    return tr(
      'Operational depth for confident day-to-day execution.',
      'مستوى عملي للتعامل اليومي بثقة وكفاءة.'
    );
  }
  if (level === 'Expert Level') {
    return tr(
      'Advanced scenarios, edge cases, and expert readiness.',
      'مستوى متقدم للحالات الخاصة والجاهزية الخبيرة.'
    );
  }
  return tr(
    'Core onboarding knowledge and essential exam basics.',
    'أساسيات التهيئة والمعرفة الرئيسية للمستوى المبتدئ.'
  );
};
