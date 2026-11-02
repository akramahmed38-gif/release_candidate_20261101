import React from 'react';
import { authService } from '../services/auth';
import DailyBriefAdmin from '../dailyBrief/DailyBriefAdmin';
import RetailDailyBrief from '../dailyBrief/RetailDailyBrief';

export default function DailyBriefPage() {
  const user = authService.getCurrentUser();
  const role = String(user?.role || user?.department || '').toLowerCase();
  return role === 'retail' || role === 'employee' ? <RetailDailyBrief /> : <DailyBriefAdmin />;
}
