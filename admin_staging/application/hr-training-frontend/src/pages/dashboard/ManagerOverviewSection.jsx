import React, { useMemo, useState } from 'react';
import { alpha } from '@mui/material/styles';
import { Bar, Doughnut } from 'react-chartjs-2';
import { Box, Card, CardContent, Chip, FormControl, InputLabel, MenuItem, Select, Typography } from '@mui/material';
import { safeCount, safePercent } from './managementDashboardUtils';

const managerBarOptions = (theme, isArabic) => ({
  responsive: true,
  maintainAspectRatio: false,
  indexAxis: 'y',
  plugins: {
    legend: { display: false },
    tooltip: { rtl: isArabic },
  },
  scales: {
    x: {
      min: 0,
      max: 100,
      ticks: {
        callback: (value) => `${value}%`,
        color: theme.palette.text.secondary,
      },
      grid: { color: alpha(theme.palette.secondary.main, 0.08) },
    },
    y: {
      ticks: { color: theme.palette.text.primary },
      grid: { display: false },
    },
  },
});

const managerDonutOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'bottom' },
  },
};

const HeroMetricCard = ({ label, value }) => (
  <Box
    sx={{
      borderRadius: 3,
      border: '1px solid rgba(16,42,86,0.08)',
      bgcolor: 'rgba(255,255,255,0.86)',
      px: 2,
      py: 1.75,
      minHeight: 104,
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'space-between',
    }}
  >
    <Typography sx={{ color: '#5C7299', fontWeight: 800, fontSize: '1rem' }}>{label}</Typography>
    <Typography sx={{ fontSize: '2rem', fontWeight: 900, color: '#102a56', lineHeight: 1 }}>{value}</Typography>
  </Box>
);

const CompactMetricCard = ({ label, value, helper }) => (
  <Card
    sx={{
      borderRadius: 4,
      border: '1px solid rgba(16,42,86,0.08)',
      boxShadow: '0 18px 40px rgba(16,42,86,0.08)',
      height: '100%',
    }}
  >
    <CardContent sx={{ px: 2.75, py: 2.5 }}>
      <Typography sx={{ color: '#5C7299', fontWeight: 800, fontSize: '0.98rem', mb: 1.1 }}>{label}</Typography>
      <Typography sx={{ fontSize: '2.1rem', fontWeight: 900, color: '#102a56', lineHeight: 1.05, mb: 1 }}>
        {value}
      </Typography>
      {helper ? (
        <Typography color="text.secondary" variant="body2">
          {helper}
        </Typography>
      ) : null}
    </CardContent>
  </Card>
);

const ChartCard = ({ title, subtitle, children }) => (
  <Card
    sx={{
      borderRadius: 4,
      border: '1px solid rgba(16,42,86,0.08)',
      boxShadow: '0 18px 40px rgba(16,42,86,0.08)',
      height: '100%',
    }}
  >
    <CardContent sx={{ height: '100%', px: 2.75, py: 2.5 }}>
      <Typography sx={{ fontSize: '1.18rem', fontWeight: 900, color: '#102a56' }}>{title}</Typography>
      {subtitle ? (
        <Typography color="text.secondary" variant="body2" sx={{ mt: 0.5, mb: 2 }}>
          {subtitle}
        </Typography>
      ) : null}
      <Box sx={{ height: 360 }}>{children}</Box>
    </CardContent>
  </Card>
);

const ChartEmptyState = ({ message }) => (
  <Box
    sx={{
      height: '100%',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      textAlign: 'center',
      px: 3,
    }}
  >
    <Typography color="text.secondary" variant="body1">
      {message}
    </Typography>
  </Box>
);

const TopicBranchInsights = ({ rows, tr, showAllBranchesForSingleTopic = false }) => (
  <Box
    sx={{
      borderRadius: 3,
      border: '1px solid rgba(16,42,86,0.08)',
      bgcolor: 'rgba(247,250,255,0.8)',
      p: 1.5,
      display: 'grid',
      gap: 1.25,
      maxHeight: 430,
      overflowY: 'auto',
    }}
  >
    <Typography sx={{ fontSize: '0.98rem', fontWeight: 900, color: '#102a56' }}>
      {tr('Branches Behind Topic Mistakes', 'الفروع الأكثر تسببا في أخطاء كل موضوع')}
    </Typography>

    {rows.map((row) => {
      const visibleBranches = showAllBranchesForSingleTopic ? row.branches || [] : (row.branches || []).slice(0, 3);

      return (
        <Box
          key={row.topic_key || row.topic}
        sx={{
          borderRadius: 3,
          border: '1px solid rgba(16,42,86,0.08)',
          bgcolor: '#ffffff',
          p: 1.25,
          display: 'grid',
          gap: 1,
        }}
      >
        <Box
          sx={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 1,
          }}
        >
          <Typography sx={{ fontWeight: 800, color: '#102a56', flex: 1, minWidth: 0 }}>{row.topic}</Typography>
          <Chip
            size="small"
            label={`${safePercent(row.error_rate_pct)} ${tr('wrong rate', 'معدل الخطأ')}`}
            sx={{
              bgcolor: 'rgba(194,65,12,0.10)',
              color: '#C2410C',
              fontWeight: 800,
              borderRadius: 999,
            }}
          />
        </Box>

        <Typography color="text.secondary" variant="caption">
          {safeCount(row.wrong_answers)} {tr('wrong answers out of', 'إجابات خاطئة من أصل')} {safeCount(row.total_answers)}
        </Typography>

        {visibleBranches.length ? (
          <Box sx={{ display: 'grid', gap: 0.75 }}>
            {visibleBranches.map((branch) => (
              <Box
                key={`${row.topic_key || row.topic}-${branch.branch_code}`}
                sx={{
                  display: 'grid',
                  gridTemplateColumns: 'minmax(0, 1fr) auto',
                  gap: 1,
                  alignItems: 'center',
                }}
              >
                <Box sx={{ minWidth: 0 }}>
                  <Typography sx={{ fontWeight: 700, color: '#102a56' }}>
                    {branch.branch_name || branch.branch_code}
                    {branch.branch_code ? ` (${branch.branch_code})` : ''}
                  </Typography>
                  <Typography color="text.secondary" variant="caption">
                    {safeCount(branch.wrong_answers)} {tr('wrong', 'خطأ')} / {safeCount(branch.total_answers)} {tr('answers', 'إجابات')}
                  </Typography>
                </Box>
                <Typography sx={{ fontWeight: 800, color: '#C2410C', whiteSpace: 'nowrap' }}>
                  {safePercent(branch.error_rate_pct)}
                </Typography>
              </Box>
            ))}
          </Box>
        ) : (
          <Typography color="text.secondary" variant="body2">
            {tr('No branch-level mistakes are available for this topic yet.', 'لا توجد أخطاء على مستوى الفروع لهذا الموضوع حتى الآن.')}
          </Typography>
        )}
        </Box>
      );
    })}
  </Box>
);

const ManagerOverviewSection = ({
  overview,
  branches,
  mistakeTopics,
  examStatusMix,
  activeBranchCode,
  theme,
  isArabic,
  tr,
  audience = 'manager',
}) => {
  const [selectedTopicKey, setSelectedTopicKey] = useState('');
  // Active Users represents all current employee accounts, regardless of exam participation.
  const activeUsers = Math.max(Number(overview?.active_employees || 0), 0);
  const joinedUsers = Math.max(Number(overview?.users_with_attempts || 0), 0);
  const trainingParticipation = activeUsers ? (joinedUsers / activeUsers) * 100 : 0;
  const overdueOpenExams = Math.max(Number(overview?.overdue_open_exams || 0), 0);

  const scoredBranches = useMemo(
    () =>
      [...(branches?.comparison || [])].filter(
        (row) =>
          Number(row?.scored_attempts || 0) > 0 ||
          (Number(row?.participating_employees || 0) > 0 && Number(row?.average_score_pct || 0) > 0)
      ),
    [branches?.comparison]
  );

  const heroCopy = useMemo(() => {
    if (overdueOpenExams > 0) {
      return {
        badge: tr('Execution Risk', 'مخاطر التنفيذ'),
        title: tr(
          'Training execution needs cleanup on overdue exams.',
          'تنفيذ التدريب يحتاج معالجة للاختبارات المفتوحة المتأخرة.'
        ),
        subtitle: tr(
          audience === 'manager'
            ? 'Close or reschedule overdue open exams to keep reporting accurate for management.'
            : 'Close or reschedule overdue open exams to keep reporting accurate.',
          'أغلق أو أعد جدولة الاختبارات المفتوحة المتأخرة للحفاظ على دقة التقارير الإدارية.'
        ),
      };
    }

    return {
      badge: audience === 'manager' ? tr('Manager Snapshot', 'ملخص المدير') : tr('Dashboard Snapshot', 'ملخص اللوحة'),
      title: tr(
        'Training performance is stable across the current exam cycle.',
        'أداء التدريب مستقر عبر دورة الاختبارات الحالية.'
      ),
      subtitle: tr(
        'Monitor active users, exam participation, and branch outcomes from one place.',
        'تابع المستخدمين النشطين ومشاركة الاختبارات ونتائج الفروع من مكان واحد.'
      ),
    };
  }, [audience, overdueOpenExams, tr]);

  const topSuccessfulBranches = useMemo(
    () =>
      [...scoredBranches]
        .sort((left, right) => {
          const scoreDiff = Number(right?.average_score_pct || 0) - Number(left?.average_score_pct || 0);
          if (scoreDiff !== 0) {
            return scoreDiff;
          }
          const participationDiff = Number(right?.participating_employees || 0) - Number(left?.participating_employees || 0);
          if (participationDiff !== 0) {
            return participationDiff;
          }
          return String(left?.branch_name || '').localeCompare(String(right?.branch_name || ''));
        })
        .slice(0, 10),
    [scoredBranches]
  );

  const improvementBranches = useMemo(
    () =>
      [...scoredBranches]
        .sort((left, right) => {
          const scoreDiff = Number(left?.average_score_pct || 0) - Number(right?.average_score_pct || 0);
          if (scoreDiff !== 0) {
            return scoreDiff;
          }
          const passRateDiff = Number(left?.pass_rate_pct || 0) - Number(right?.pass_rate_pct || 0);
          if (passRateDiff !== 0) {
            return passRateDiff;
          }
          return String(left?.branch_name || '').localeCompare(String(right?.branch_name || ''));
        })
        .slice(0, 10),
    [scoredBranches]
  );

  const mistakeTopicRows = useMemo(
    () =>
      [...(mistakeTopics || [])].sort((left, right) => {
        const wrongDiff = Number(right?.wrong_answers || 0) - Number(left?.wrong_answers || 0);
        if (wrongDiff !== 0) {
          return wrongDiff;
        }
        const errorRateDiff = Number(right?.error_rate_pct || 0) - Number(left?.error_rate_pct || 0);
        if (errorRateDiff !== 0) {
          return errorRateDiff;
        }
        return String(left?.topic || '').localeCompare(String(right?.topic || ''));
      }),
    [mistakeTopics]
  );

  const topicOptions = useMemo(
    () =>
      mistakeTopicRows.map((row) => ({
        value: row.topic_key || row.topic || '',
        label: row.topic || '-',
      })),
    [mistakeTopicRows]
  );

  const resolvedSelectedTopicKey = useMemo(
    () => (topicOptions.some((option) => option.value === selectedTopicKey) ? selectedTopicKey : ''),
    [selectedTopicKey, topicOptions]
  );

  const filteredMistakeTopicRows = useMemo(() => {
    if (!resolvedSelectedTopicKey) {
      return mistakeTopicRows;
    }
    return mistakeTopicRows.filter((row) => (row.topic_key || row.topic || '') === resolvedSelectedTopicKey);
  }, [mistakeTopicRows, resolvedSelectedTopicKey]);

  const topSuccessfulChart = useMemo(
    () => ({
      labels: topSuccessfulBranches.map((row) => `${row.branch_name || '-'} (${row.branch_code || '-'})`),
      datasets: [
        {
          data: topSuccessfulBranches.map((row) => Number(row.average_score_pct || 0)),
          backgroundColor: theme.palette.primary.dark,
          borderRadius: 6,
        },
      ],
    }),
    [theme.palette.primary.dark, topSuccessfulBranches]
  );

  const improvementBranchesChart = useMemo(
    () => ({
      labels: improvementBranches.map((row) => `${row.branch_name || '-'} (${row.branch_code || '-'})`),
      datasets: [
        {
          data: improvementBranches.map((row) => Number(row.average_score_pct || 0)),
          backgroundColor: '#B45309',
          borderRadius: 6,
        },
      ],
    }),
    [improvementBranches]
  );

  const mistakeTopicsChart = useMemo(
    () => ({
      labels: filteredMistakeTopicRows.map((row) => row.topic || '-'),
      datasets: [
        {
          data: filteredMistakeTopicRows.map((row) => Number(row.error_rate_pct || 0)),
          backgroundColor: '#C2410C',
          borderRadius: 6,
        },
      ],
    }),
    [filteredMistakeTopicRows]
  );

  const statusMixChart = useMemo(
    () => ({
      labels: [tr('Open', 'مفتوح'), tr('On Hold', 'معلق'), tr('Closed', 'مغلق')],
      datasets: [
        {
          data: [Number(examStatusMix?.Open || 0), Number(examStatusMix?.['On Hold'] || 0), Number(examStatusMix?.Closed || 0)],
          backgroundColor: [theme.palette.primary.dark, '#B45309', theme.palette.secondary.main],
          borderColor: '#ffffff',
          borderWidth: 2,
        },
      ],
    }),
    [examStatusMix, theme.palette.primary.dark, theme.palette.secondary.main, tr]
  );

  const mistakeTopicSubtitle = activeBranchCode
    ? tr(
        `Grouped by question topic and ranked by wrong-answer rate for branch ${activeBranchCode}.`,
        `مجمعة حسب موضوع السؤال ومرتبة حسب معدل الإجابات الخاطئة للفرع ${activeBranchCode}.`
      )
    : tr(
        'Grouped by question topic and ranked by wrong-answer rate.',
        'مجمعة حسب موضوع السؤال ومرتبة حسب معدل الإجابات الخاطئة.'
      );

  return (
    <Box sx={{ display: 'grid', gap: 3 }}>
      <Box
        sx={{
          borderRadius: 5,
          border: '1px solid rgba(80,117,191,0.14)',
          background: 'linear-gradient(180deg, rgba(247,250,255,0.98) 0%, rgba(239,245,255,0.96) 100%)',
          boxShadow: '0 24px 50px rgba(16,42,86,0.10)',
          px: { xs: 2, md: 3.5 },
          py: { xs: 2.5, md: 3.25 },
        }}
      >
        <Chip
          label={heroCopy.badge}
          sx={{
            mb: 2,
            bgcolor: 'rgba(47,106,215,0.12)',
            color: '#0C4AA6',
            fontWeight: 800,
            borderRadius: 999,
          }}
        />
        <Typography
          sx={{
            fontSize: { xs: '2rem', md: '2.8rem' },
            lineHeight: 1.15,
            fontWeight: 900,
            color: '#102a56',
            maxWidth: 1080,
          }}
        >
          {heroCopy.title}
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 1.25, fontSize: { xs: '1rem', md: '1.15rem' }, maxWidth: 980 }}>
          {heroCopy.subtitle}
        </Typography>

        <Box
          sx={{
            mt: 3,
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0, 1fr))' },
            gap: 1.5,
          }}
        >
          <HeroMetricCard label={tr('Active Users', 'المستخدمون النشطون')} value={safeCount(activeUsers)} />
          <HeroMetricCard label={tr('Active Exams', 'الاختبارات النشطة')} value={safeCount(overview?.active_open_exams)} />
          <HeroMetricCard label={tr('Pass Rate', 'معدل النجاح')} value={safePercent(overview?.pass_rate_pct)} />
        </Box>
      </Box>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))', xl: 'repeat(4, minmax(0, 1fr))' },
          gap: 2,
        }}
      >
        <CompactMetricCard
          label={tr('Training Participation', 'نسبة المشاركة التدريبية')}
          value={safePercent(trainingParticipation)}
          helper={`${safeCount(joinedUsers)} ${tr('users joined exams', 'مستخدم شارك في الاختبارات')}`}
        />
        <CompactMetricCard
          label={tr('Users Joined Exams', 'المستخدمون المشاركون')}
          value={safeCount(joinedUsers)}
          helper={tr(
            'Employees with at least one submitted exam attempt.',
            'الموظفون الذين لديهم محاولة اختبار مرسلة واحدة على الأقل.'
          )}
        />
        <CompactMetricCard
          label={tr('Overdue Open Exams', 'الاختبارات المفتوحة المتأخرة')}
          value={safeCount(overdueOpenExams)}
          helper={tr('Open exams with an end date before today.', 'اختبارات مفتوحة انتهى تاريخها قبل اليوم.')}
        />
        <CompactMetricCard
          label={tr('Average Score', 'متوسط الدرجات')}
          value={safePercent(overview?.average_exam_score_pct)}
          helper={tr(
            'Average percentage score across submitted attempts.',
            'متوسط النسبة المئوية عبر المحاولات المرسلة.'
          )}
        />
      </Box>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', xl: '0.9fr 1.25fr 1.25fr' },
          gap: 2,
          alignItems: 'stretch',
        }}
      >
        <ChartCard
          title={tr('Exam Status Mix', 'توزيع حالات الاختبارات')}
          subtitle={tr(
            'Open, on-hold, and closed exams in the current scope.',
            'الاختبارات المفتوحة والمعلقة والمغلقة داخل النطاق الحالي.'
          )}
        >
          <Doughnut data={statusMixChart} options={managerDonutOptions} />
        </ChartCard>

        <ChartCard
          title={tr('Top 10 Branches by Average Success', 'أفضل 10 فروع حسب متوسط النجاح')}
          subtitle={tr(
            'Sorted by branch average success percentage.',
            'مرتبة حسب متوسط نسبة النجاح في كل فرع.'
          )}
        >
          {topSuccessfulBranches.length ? (
            <Bar data={topSuccessfulChart} options={managerBarOptions(theme, isArabic)} />
          ) : (
            <ChartEmptyState
              message={tr(
                'No scored branch data is available for the selected scope yet.',
                'لا توجد بيانات درجات للفروع ضمن النطاق المحدد حتى الآن.'
              )}
            />
          )}
        </ChartCard>

        <ChartCard
          title={tr('10 Branches with Lowest Total Exam Scores', '10 فروع لديها أقل درجات في إجمالي الاختبارات')}
          subtitle={tr(
            'Sorted by branch average score across all submitted exams in scope.',
            'مرتبة حسب متوسط درجات الفرع عبر جميع الاختبارات المرسلة داخل النطاق.'
          )}
        >
          {improvementBranches.length ? (
            <Bar data={improvementBranchesChart} options={managerBarOptions(theme, isArabic)} />
          ) : (
            <ChartEmptyState
              message={tr(
                'No scored branch data is available for the selected scope yet.',
                'لا توجد بيانات درجات للفروع ضمن النطاق المحدد حتى الآن.'
              )}
            />
          )}
        </ChartCard>
      </Box>

      <Card
        sx={{
          borderRadius: 4,
          border: '1px solid rgba(16,42,86,0.08)',
          boxShadow: '0 18px 40px rgba(16,42,86,0.08)',
        }}
      >
        <CardContent sx={{ px: 2.75, py: 2.5 }}>
          <Box
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', lg: 'row' },
              justifyContent: 'space-between',
              alignItems: { xs: 'stretch', lg: 'flex-start' },
              gap: 2,
              mb: 2,
            }}
          >
            <Box>
          <Typography sx={{ fontSize: '1.18rem', fontWeight: 900, color: '#102a56' }}>
            {tr('Topics Employees Mistake In', 'المواضيع التي يكثر فيها خطأ الموظفين')}
          </Typography>
          <Typography color="text.secondary" variant="body2" sx={{ mt: 0.5 }}>
            {mistakeTopicSubtitle}
          </Typography>
            </Box>

            {topicOptions.length ? (
              <FormControl size="small" sx={{ minWidth: { xs: '100%', sm: 240 }, maxWidth: 320 }}>
                <InputLabel id="manager-topic-filter-label">{tr('Topic', 'الموضوع')}</InputLabel>
                <Select
                  id="manager-topic-filter"
                  labelId="manager-topic-filter-label"
                  label={tr('Topic', 'الموضوع')}
                  value={resolvedSelectedTopicKey}
                  onChange={(event) => setSelectedTopicKey(event.target.value)}
                  MenuProps={{ PaperProps: { sx: { maxHeight: 360 } } }}
                >
                  <MenuItem value="">{tr('All Topics', 'كل المواضيع')}</MenuItem>
                  {topicOptions.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            ) : null}
          </Box>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', xl: '1.25fr 0.95fr' },
              gap: 2,
              alignItems: 'stretch',
            }}
          >
            <Box sx={{ minHeight: 430 }}>
              {filteredMistakeTopicRows.length ? (
                <Bar data={mistakeTopicsChart} options={managerBarOptions(theme, isArabic)} />
              ) : (
                <ChartEmptyState
                  message={tr(
                    'No topic-level mistakes are available for the selected scope yet.',
                    'لا توجد أخطاء على مستوى المواضيع ضمن النطاق المحدد حتى الآن.'
                  )}
                />
              )}
            </Box>

            {filteredMistakeTopicRows.length ? (
              <TopicBranchInsights
                rows={filteredMistakeTopicRows}
                tr={tr}
                showAllBranchesForSingleTopic={Boolean(resolvedSelectedTopicKey)}
              />
            ) : (
              <Box sx={{ minHeight: 430 }}>
                <ChartEmptyState
                  message={tr(
                    'Branch-level mistake analytics will appear here when wrong answers are available.',
                    'ستظهر هنا تحليلات أخطاء الفروع عند توفر إجابات خاطئة.'
                  )}
                />
              </Box>
            )}
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
};

export default ManagerOverviewSection;
