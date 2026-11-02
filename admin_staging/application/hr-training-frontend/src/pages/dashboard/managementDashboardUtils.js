export const defaultManagementSummary = {
  generated_at: null,
  cache: { hit: false, ttl_seconds: 300 },
  filters: {
    period: 'all',
    month: null,
    region: null,
    area: null,
    branch_code: null,
    role: null,
  },
  access: {
    access_role: '',
    can_view_employee_attention: false,
    can_export_attention_lists: false,
  },
  filter_options: {
    regions: [],
    areas: [],
    branches: [],
    months: [],
  },
  overview: {
    active_employees: 0,
    resigned_employees: 0,
    users_with_attempts: 0,
    training_participation_rate: 0,
    average_exam_score_pct: 0,
    pass_rate_pct: 0,
    no_exam_attempts: 0,
    never_logged_in: 0,
    never_active: 0,
    active_open_exams: 0,
    overdue_open_exams: 0,
  },
  trends: {
    grouping: 'month',
    items: [],
  },
  branches: {
    top: [],
    low: [],
    lowest_participation: [],
    highest_no_attempts: [],
    comparison: [],
  },
  mistake_topics: [],
  exam_status_mix: {
    Open: 0,
    Closed: 0,
    'On Hold': 0,
  },
  exam_insights: {
    highest_participation: [],
    lowest_participation: [],
    highest_failure_rate: [],
    lowest_average_score: [],
    active_open: [],
    overdue_open: [],
  },
  attention: {
    no_attempts_count: 0,
    low_score_count: 0,
    repeated_failure_count: 0,
    never_logged_in_count: 0,
    never_active_count: 0,
  },
  alerts: [],
};

export const managementPeriodOptions = (tr) => [
  { value: 'all', label: tr('All Time', 'كل الفترات') },
  { value: 'week', label: tr('This Week', 'هذا الأسبوع') },
  { value: 'month', label: tr('This Month', 'هذا الشهر') },
  { value: 'year', label: tr('This Year', 'هذا العام') },
];

export const getManagementPeriodSelectionValue = (filters = {}) =>
  filters.month ? `month:${filters.month}` : `preset:${filters.period || 'all'}`;

export const formatManagementMonthLabel = (monthValue, isArabic = false) => {
  if (!monthValue) {
    return monthValue;
  }
  try {
    const [yearValue, monthValueNumber] = String(monthValue).split('-').map(Number);
    const dateValue = new Date(Date.UTC(yearValue, monthValueNumber - 1, 1));
    return new Intl.DateTimeFormat(isArabic ? 'ar-EG' : 'en-US', {
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(dateValue);
  } catch (_error) {
    return String(monthValue);
  }
};

export const buildManagementPeriodFilterOptions = (tr, months = [], isArabic = false) => {
  const presetOptions = managementPeriodOptions(tr).map((option) => ({
    value: `preset:${option.value}`,
    label: option.label,
  }));
  const monthOptions = Array.from(
    new Set(
      (months || [])
        .map((value) => String(value || '').trim())
        .filter(Boolean)
    )
  ).map((value) => ({
    value: `month:${value}`,
    label: formatManagementMonthLabel(value, isArabic),
  }));

  if (!monthOptions.length) {
    return presetOptions;
  }

  return [
    ...presetOptions,
    {
      value: '__months__',
      label: tr('Available Months', 'الشهور المتاحة'),
      disabled: true,
    },
    ...monthOptions,
  ];
};

export const safeCount = (value) => Number(value || 0).toLocaleString();

export const safePercent = (value, digits = 1) => {
  const numeric = Number(value || 0);
  return `${numeric.toFixed(digits)}%`;
};

export const safeDateTimeLabel = (value) => {
  if (!value) {
    return '-';
  }
  try {
    return new Date(value).toLocaleString();
  } catch (_error) {
    return String(value);
  }
};

export const defaultAttentionKind = 'no_attempts';

export const attentionKinds = (tr) => [
  { value: 'no_attempts', label: tr('No Attempts', 'بدون محاولات') },
  { value: 'low_scores', label: tr('Low Scores', 'درجات منخفضة') },
  { value: 'repeated_failures', label: tr('Repeated Failures', 'رسوب متكرر') },
  { value: 'never_logged_in', label: tr('Never Logged In', 'لم يسجل الدخول') },
  { value: 'never_active', label: tr('Never Active', 'بدون نشاط') },
];

export const examInsightTabs = (tr) => [
  { value: 'highest_participation', label: tr('Highest Participation', 'أعلى مشاركة') },
  { value: 'lowest_participation', label: tr('Lowest Participation', 'أقل مشاركة') },
  { value: 'highest_failure_rate', label: tr('Highest Failure Rate', 'أعلى رسوب') },
  { value: 'lowest_average_score', label: tr('Lowest Average Score', 'أقل متوسط درجات') },
  { value: 'active_open', label: tr('Active/Open Exams', 'الاختبارات المفتوحة') },
  { value: 'overdue_open', label: tr('Overdue Open Exams', 'الاختبارات المتأخرة') },
];

export const buildRoleFilterOptions = (departments = [], tr) => {
  const scopedDepartments = (departments || [])
    .map((value) => String(value || '').trim())
    .filter(Boolean)
    .filter((value) => ['retail', 'employee'].includes(value.toLowerCase()));
  const uniqueDepartments = Array.from(new Set(scopedDepartments));

  return [
    { value: '', label: tr('All Roles', 'كل الأدوار') },
    ...uniqueDepartments.map((value) => ({
      value: value.toLowerCase(),
      label: value,
    })),
  ];
};
