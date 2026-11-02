import React from 'react';
import { Box, Button, Card, CardContent, FormControl, InputLabel, MenuItem, Select, Stack, Typography } from '@mui/material';
import {
  buildManagementPeriodFilterOptions,
  buildRoleFilterOptions,
  getManagementPeriodSelectionValue,
} from './managementDashboardUtils';

const ManagementFilterBar = ({
  filters,
  audienceRegions,
  audienceAreas,
  audienceBranches,
  audienceDepartments,
  monthOptions,
  onChange,
  onReset,
  disabled,
  tr,
  isArabic = false,
}) => {
  const periodOptions = buildManagementPeriodFilterOptions(tr, monthOptions, isArabic);
  const roleOptions = buildRoleFilterOptions(audienceDepartments, tr);

  return (
    <Card sx={{ borderRadius: 4 }}>
      <CardContent>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          justifyContent="space-between"
          alignItems={{ xs: 'flex-start', md: 'center' }}
          spacing={1}
          sx={{ mb: 2 }}
        >
          <Box>
            <Typography sx={{ fontSize: '1.25rem', fontWeight: 800, color: '#102a56' }}>
              {tr('Global Filters', 'الفلاتر العامة')}
            </Typography>
            <Typography color="text.secondary" variant="body2">
              {tr(
                'Scope all management KPIs, trends, branch analytics, and exam insights with the same filter set.',
                'طبّق نفس نطاق التصفية على مؤشرات الإدارة والاتجاهات وتحليلات الفروع ورؤى الاختبارات.'
              )}
            </Typography>
          </Box>
          <Button onClick={onReset} disabled={disabled} sx={{ fontWeight: 700 }}>
            {tr('Reset Filters', 'إعادة ضبط الفلاتر')}
          </Button>
        </Stack>

        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: {
              xs: '1fr',
              sm: 'repeat(2, minmax(0, 1fr))',
              xl: 'repeat(5, minmax(0, 1fr))',
            },
            gap: 1.5,
          }}
        >
          <FormControl fullWidth disabled={disabled}>
            <InputLabel>{tr('Period', 'الفترة')}</InputLabel>
            <Select
              label={tr('Period', 'الفترة')}
              value={getManagementPeriodSelectionValue(filters)}
              onChange={(event) => onChange('periodSelection', event.target.value)}
              MenuProps={{ PaperProps: { sx: { maxHeight: 360 } } }}
            >
              {periodOptions.map((option) => (
                <MenuItem key={option.value} value={option.value} disabled={option.disabled}>
                  {option.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl fullWidth disabled={disabled}>
            <InputLabel>{tr('Region', 'المنطقة')}</InputLabel>
            <Select
              label={tr('Region', 'المنطقة')}
              value={filters.region}
              onChange={(event) => onChange('region', event.target.value)}
            >
              <MenuItem value="">{tr('All Regions', 'كل المناطق')}</MenuItem>
              {audienceRegions.map((region) => (
                <MenuItem key={region.region} value={region.region}>
                  {region.region}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl fullWidth disabled={disabled || !audienceAreas.length}>
            <InputLabel>{tr('Area', 'القطاع')}</InputLabel>
            <Select
              label={tr('Area', 'القطاع')}
              value={filters.area}
              onChange={(event) => onChange('area', event.target.value)}
            >
              <MenuItem value="">{tr('All Areas', 'كل القطاعات')}</MenuItem>
              {audienceAreas.map((area) => (
                <MenuItem key={area.area} value={area.area}>
                  {area.area}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl fullWidth disabled={disabled || !audienceBranches.length}>
            <InputLabel>{tr('Branch', 'الفرع')}</InputLabel>
            <Select
              label={tr('Branch', 'الفرع')}
              value={filters.branch_code}
              onChange={(event) => onChange('branch_code', event.target.value)}
            >
              <MenuItem value="">{tr('All Branches', 'كل الفروع')}</MenuItem>
              {audienceBranches.map((branch) => (
                <MenuItem key={branch.branch_code} value={branch.branch_code}>
                  {branch.branch_name} ({branch.branch_code})
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl fullWidth disabled={disabled}>
            <InputLabel>{tr('Role', 'الدور')}</InputLabel>
            <Select
              label={tr('Role', 'الدور')}
              value={filters.role}
              onChange={(event) => onChange('role', event.target.value)}
            >
              {roleOptions.map((option) => (
                <MenuItem key={option.value || 'all'} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>
      </CardContent>
    </Card>
  );
};

export default ManagementFilterBar;
