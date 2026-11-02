import React, { useMemo, useState } from 'react';
import { AppBar, Box, Button, Divider, IconButton, ListItemIcon, ListItemText, Menu, MenuItem, Toolbar, Tooltip, Typography, useMediaQuery } from '@mui/material';
import { AutoStoriesOutlined, CampaignOutlined, DashboardRounded, ExpandMore, FolderOpenOutlined, HistoryOutlined, Logout, ManageAccountsOutlined, MenuBookOutlined, MenuRounded, PersonRemoveOutlined, QuizOutlined, TrendingUpOutlined } from '@mui/icons-material';
import { useLocation, useNavigate } from 'react-router-dom';
import { authService } from '../../services/auth';
import { useLanguage } from '../../context/LanguageContext';
import LanguageToggle from '../Common/LanguageToggle';

const getNavButtonSx = (active) => ({
  color: 'secondary.main', fontWeight: active ? 800 : 700, borderRadius: 999,
  px: { md: 0.82, lg: 1.05, xl: 1.2 }, py: 0.62, minWidth: 0, whiteSpace: 'nowrap', lineHeight: 1.1,
  fontSize: { md: 12.7, lg: 13.5, xl: 14 }, background: active ? 'rgba(255,255,255,0.94)' : 'transparent',
  border: active ? '1px solid rgba(31,53,88,0.14)' : '1px solid transparent',
  boxShadow: active ? 'inset 0 -3px 0 rgba(31,53,88,0.74), 0 8px 18px rgba(31,53,88,0.09)' : 'none',
  transition: 'transform 160ms ease, box-shadow 160ms ease, background-color 160ms ease, border-color 160ms ease',
  '&:hover': { transform: 'translateY(-1px)', bgcolor: active ? 'rgba(255,255,255,0.98)' : 'rgba(255,255,255,0.20)', boxShadow: active ? 'inset 0 -3px 0 rgba(31,53,88,0.74), 0 10px 20px rgba(31,53,88,0.12)' : '0 8px 18px rgba(31,53,88,0.10)' },
});

const navItem = (id, text, path, icon) => ({ id, text, path, icon });
const navGroup = (id, text, children) => ({ id, text, children });

const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const user = authService.getCurrentUser();
  const { t, isArabic } = useLanguage();
  const [mobileNavAnchor, setMobileNavAnchor] = useState(null);
  const [openGroup, setOpenGroup] = useState({ id: null, anchorEl: null });
  const [mobileExpandedGroups, setMobileExpandedGroups] = useState({});
  const isTabletNav = useMediaQuery('(max-width:1199.95px)');
  const basePath = import.meta.env.VITE_BASENAME || '/training';
  const normalizedBasePath = basePath.startsWith('/') ? basePath : `/${basePath}`;
  const rawRole = (user?.role || user?.department || '').toLowerCase();
  const normalizedRole = rawRole === 'employee' ? 'retail' : rawRole;
  const homePath = normalizedRole === 'retail' ? '/daily-brief' : '/dashboard';
  const displayRole = (user?.department || user?.role || '').toUpperCase();
  const isRetailExamDetail = normalizedRole === 'retail' && location.pathname.startsWith('/employee/exams/');
  const isActivePath = (path) => (path === '/dashboard' ? location.pathname === path : location.pathname === path || location.pathname.startsWith(`${path}/`));

  const navigationByRole = {
    admin: [
      navItem('dashboard', t('Dashboard', 'لوحة التحكم'), '/dashboard', DashboardRounded),
      navItem('daily-brief', t('Daily Brief', 'الملخص اليومي'), '/daily-brief', CampaignOutlined),
      navItem('business-vocabulary', t('Business Vocabulary', 'مفردات الأعمال'), '/business-vocabulary', MenuBookOutlined),
      navGroup('exams', t('Exams', 'الاختبارات'), [
        navItem('exam-list', t('Exams', 'الاختبارات'), '/hr/exams', QuizOutlined),
        navItem('question-bank', t('Question Bank', 'بنك الأسئلة'), '/hr/question-bank', MenuBookOutlined),
      ]),
      navGroup('learning-content', t('Learning Content', 'محتوى التعلم'), [
        navItem('materials', t('Materials', 'المواد التدريبية'), '/materials', FolderOpenOutlined),
        navItem('script-book', t('Script Book', 'كتاب السكربتات'), '/script-book', AutoStoriesOutlined),
      ]),
      navGroup('management', t('Management', 'الإدارة'), [
        navItem('users', t('User Management', 'إدارة المستخدمين'), '/admin/users', ManageAccountsOutlined),
        navItem('employee-performance', t('Employee Performance', 'أداء الموظفين'), '/hr/employee-performance', TrendingUpOutlined),
        navItem('audit-trail', t('Audit Trail', 'سجل العمليات'), '/admin/audit', HistoryOutlined),
        navItem('resigned-users', t('Resigned Users', 'المستقيلون'), '/admin/resigned-users', PersonRemoveOutlined),
      ]),
    ],
    hr: [
      navItem('dashboard', t('Dashboard', 'لوحة التحكم'), '/dashboard', DashboardRounded),
      navItem('daily-brief', t('Daily Brief', 'الملخص اليومي'), '/daily-brief', CampaignOutlined),
      navItem('business-vocabulary', t('Business Vocabulary', 'مفردات الأعمال'), '/business-vocabulary', MenuBookOutlined),
      navGroup('exams', t('Exams', 'الاختبارات'), [
        navItem('exam-list', t('Exams', 'الاختبارات'), '/hr/exams', QuizOutlined),
        navItem('question-bank', t('Question Bank', 'بنك الأسئلة'), '/hr/question-bank', MenuBookOutlined),
      ]),
      navGroup('learning-content', t('Learning Content', 'محتوى التعلم'), [
        navItem('materials', t('Materials', 'المواد التدريبية'), '/materials', FolderOpenOutlined),
        navItem('script-book', t('Script Book', 'كتاب السكربتات'), '/script-book', AutoStoriesOutlined),
      ]),
      navGroup('management', t('Management', 'الإدارة'), [
        navItem('users', t('User Management', 'إدارة المستخدمين'), '/admin/users', ManageAccountsOutlined),
        navItem('employee-performance', t('Employee Performance', 'أداء الموظفين'), '/hr/employee-performance', TrendingUpOutlined),
      ]),
    ],
    manager: [navItem('manager-overview', t('Manager Overview', 'لوحة متابعة المدير'), '/dashboard', DashboardRounded)],
    retail: [
      navItem('daily-brief', t('Daily Brief', 'الملخص اليومي'), '/daily-brief', CampaignOutlined),
      navItem('business-vocabulary', t('Business Vocabulary', 'مفردات الأعمال'), '/business-vocabulary', MenuBookOutlined),
      navItem('my-exams', t('My Exams', 'اختباراتي'), '/employee/exams', QuizOutlined),
      navItem('materials', t('Materials', 'المواد التدريبية'), '/materials', FolderOpenOutlined),
      navItem('script-book', t('Script Book', 'كتاب السكربتات'), '/script-book', AutoStoriesOutlined),
      navItem('contact-us', t('Contact Us', 'تواصل معنا'), '/employee/contact', CampaignOutlined),
    ],
  };
  navigationByRole.auditor = navigationByRole.admin.map((entry) => entry.children
    ? { ...entry, children: entry.children.filter((child) => child.id !== 'audit-trail') }
    : entry);
  const currentMenu = navigationByRole[normalizedRole] || [];
  const openGroupConfig = currentMenu.find((entry) => entry.id === openGroup.id) || null;
  const shortUserLabel = useMemo(() => user?.email?.split('@')?.[0]?.trim() || user?.name || t('User', 'مستخدم'), [t, user?.email, user?.name]);
  const fullUserLabel = useMemo(() => (!user?.email && !displayRole ? shortUserLabel : [user?.email, displayRole].filter(Boolean).join(' • ')), [displayRole, shortUserLabel, user?.email]);

  const handleLogout = () => { authService.logout(); navigate('/login'); };
  const handleNavigate = (path) => {
    if (isRetailExamDetail && path === '/employee/exams') window.location.assign(`${normalizedBasePath}${path}`);
    else navigate(path);
  };
  const closeGroupMenu = () => setOpenGroup({ id: null, anchorEl: null });
  const openGroupMenu = (event, groupId) => setOpenGroup((current) => (current.id === groupId ? { id: null, anchorEl: null } : { id: groupId, anchorEl: event.currentTarget }));
  const selectGroupItem = (path) => { closeGroupMenu(); handleNavigate(path); };
  const handleMobileMenuClose = () => { setMobileNavAnchor(null); setMobileExpandedGroups({}); };
  const handleMobileNavigate = (path) => { handleMobileMenuClose(); handleNavigate(path); };
  const toggleMobileGroup = (groupId) => setMobileExpandedGroups((current) => ({ ...current, [groupId]: !current[groupId] }));

  const menuItemSx = (active) => ({
    minHeight: 42, borderRadius: 1.6, px: 1.15, gap: 0.2, fontSize: 14, fontWeight: active ? 800 : 650, color: 'secondary.main',
    '&.Mui-selected': { bgcolor: 'rgba(255,210,0,0.20)', borderInlineStart: '3px solid', borderColor: 'primary.main', pl: 0.8 },
    '&:hover': { bgcolor: active ? 'rgba(255,210,0,0.24)' : 'rgba(255,210,0,0.12)' },
  });

  return (
    <AppBar position="sticky" elevation={0}>
      <Toolbar sx={{ minHeight: { xs: 'auto', md: 72 }, width: '100%', maxWidth: 1440, mx: 'auto', px: { xs: 1.25, md: 1.8, lg: 2.15 }, py: { xs: 0.75, md: 0.82 }, gap: { xs: 0.8, md: 1, lg: 1.25 }, direction: isArabic ? 'rtl' : 'ltr', alignItems: 'center', justifyContent: 'space-between', flexWrap: isTabletNav ? 'wrap' : 'nowrap', borderRadius: { xs: 0, md: 3 }, background: 'transparent' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.9, cursor: 'pointer', flexShrink: 0, order: 1, minWidth: 0, flex: isTabletNav ? '1 1 auto' : '0 0 auto' }} onClick={() => navigate(homePath)}>
          <img src="/assets/logo.png" alt="Fawry Plus" style={{ height: 38, display: 'block', borderRadius: 10, background: 'rgba(255,255,255,0.92)', padding: 4, boxShadow: '0 8px 18px rgba(31,53,88,0.10)' }} />
          <Typography sx={{ fontWeight: 800, color: 'secondary.main', fontSize: { xs: 15.5, sm: 18, md: 21.5, lg: 22.5, xl: 24 }, lineHeight: 1.1, fontFamily: '"Segoe UI", "Tahoma", "Arial", sans-serif', letterSpacing: '-0.02em', whiteSpace: 'nowrap', overflow: { xs: 'hidden', md: 'visible' }, textOverflow: { xs: 'ellipsis', md: 'clip' }, maxWidth: { xs: '52vw', sm: '43vw', md: 'none' } }}>{t('Training System', 'نظام التدريب')}</Typography>
        </Box>

        {!isTabletNav && <Box sx={{ flex: '1 1 auto', minWidth: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', order: 2, px: { md: 0.35, lg: 0.6 } }}><Box sx={{ minWidth: 0, width: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: { md: 0.55, lg: 0.75, xl: 0.95 }, whiteSpace: 'nowrap' }}>
          {currentMenu.map((entry) => {
            const isGroup = Boolean(entry.children);
            const active = isGroup ? entry.children.some((child) => isActivePath(child.path)) : isActivePath(entry.path);
            return <Button key={entry.id} id={`nav-${entry.id}`} onClick={isGroup ? (event) => openGroupMenu(event, entry.id) : () => handleNavigate(entry.path)} endIcon={isGroup ? <ExpandMore sx={{ fontSize: 17, transform: openGroup.id === entry.id ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 150ms ease' }} /> : undefined} aria-haspopup={isGroup ? 'menu' : undefined} aria-expanded={isGroup ? openGroup.id === entry.id : undefined} aria-controls={isGroup && openGroup.id === entry.id ? `nav-menu-${entry.id}` : undefined} sx={getNavButtonSx(active)}>{entry.text}</Button>;
          })}
        </Box></Box>}

        <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 0.55, md: 0.7, lg: 0.8 }, order: isTabletNav ? 2 : 3, marginInlineStart: 'auto', flexShrink: 0, justifyContent: 'flex-end', flexWrap: 'nowrap' }}>
          {isTabletNav && <Tooltip title={t('Navigation', 'التنقل')}><IconButton onClick={(event) => setMobileNavAnchor(event.currentTarget)} size="small" aria-label={t('Open navigation menu', 'فتح قائمة التنقل')} sx={{ width: 40, height: 40, borderRadius: 999, color: 'secondary.main', background: 'rgba(255,255,255,0.94)', border: '1px solid rgba(31,53,88,0.12)', boxShadow: '0 8px 18px rgba(31,53,88,0.08)', '&:hover': { background: 'rgba(255,255,255,1)' } }}><MenuRounded fontSize="small" /></IconButton></Tooltip>}
          <LanguageToggle compact abbreviated={!isTabletNav} />
          <Tooltip title={fullUserLabel}><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.7, bgcolor: 'rgba(255,255,255,0.90)', border: '1px solid rgba(31,53,88,0.14)', borderRadius: 999, px: { xs: 0.95, md: 1.1, lg: 1.2 }, py: 0.55, maxWidth: { xs: 124, md: 170, lg: 188 }, boxShadow: '0 8px 18px rgba(31,53,88,0.08), inset 0 1px 0 rgba(255,255,255,0.9)' }}><Typography variant="body2" sx={{ fontWeight: 700, color: 'secondary.main', direction: 'ltr', unicodeBidi: 'plaintext', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0, fontSize: { xs: 12, lg: 12.6 } }}>{shortUserLabel}</Typography><Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800, fontSize: 10.5, whiteSpace: 'nowrap' }}>{displayRole}</Typography></Box></Tooltip>
          <Tooltip title={t('Logout', 'خروج')}><IconButton onClick={handleLogout} aria-label={t('Logout', 'خروج')} size="small" sx={{ width: 42, height: 42, borderRadius: 999, background: 'rgba(255,255,255,0.96)', color: 'secondary.dark', border: '1px solid rgba(31,53,88,0.12)', boxShadow: '0 10px 22px rgba(31,53,88,0.10)', '&:hover': { background: 'rgba(255,255,255,1)', boxShadow: '0 12px 24px rgba(31,53,88,0.14)' } }}><Logout fontSize="small" /></IconButton></Tooltip>
        </Box>

        <Menu id={openGroup.id ? `nav-menu-${openGroup.id}` : undefined} anchorEl={openGroup.anchorEl} open={Boolean(openGroup.anchorEl)} onClose={closeGroupMenu} anchorOrigin={{ vertical: 'bottom', horizontal: isArabic ? 'right' : 'left' }} transformOrigin={{ vertical: 'top', horizontal: isArabic ? 'right' : 'left' }} MenuListProps={{ 'aria-labelledby': openGroup.id ? `nav-${openGroup.id}` : undefined }} PaperProps={{ sx: { mt: 0.9, minWidth: 236, p: 0.75, borderRadius: 2.5, border: '1px solid rgba(31,53,88,0.14)', boxShadow: '0 16px 36px rgba(31,53,88,0.14)', direction: isArabic ? 'rtl' : 'ltr' } }}>
          {openGroupConfig?.children.map((item) => {
            const Icon = item.icon;
            const active = isActivePath(item.path);
            return <MenuItem key={item.id} selected={active} onClick={() => selectGroupItem(item.path)} sx={menuItemSx(active)}><ListItemIcon sx={{ minWidth: 34, color: active ? 'secondary.main' : 'text.secondary' }}><Icon fontSize="small" /></ListItemIcon><ListItemText primary={item.text} /></MenuItem>;
          })}
        </Menu>

        <Menu anchorEl={mobileNavAnchor} open={Boolean(mobileNavAnchor)} onClose={handleMobileMenuClose} anchorOrigin={{ vertical: 'bottom', horizontal: isArabic ? 'left' : 'right' }} transformOrigin={{ vertical: 'top', horizontal: isArabic ? 'left' : 'right' }} PaperProps={{ sx: { mt: 1, minWidth: 255, maxWidth: 'calc(100vw - 24px)', maxHeight: 'calc(100vh - 100px)', overflowY: 'auto', borderRadius: 2.5, border: '1px solid rgba(31,53,88,0.12)', boxShadow: '0 16px 36px rgba(31,53,88,0.12)', direction: isArabic ? 'rtl' : 'ltr' } }}>
          {currentMenu.map((entry, index) => {
            if (!entry.children) {
              const Icon = entry.icon;
              const active = isActivePath(entry.path);
              return <MenuItem key={entry.id} selected={active} onClick={() => handleMobileNavigate(entry.path)} sx={{ minHeight: 44, fontSize: 14, fontWeight: active ? 800 : 650, color: 'secondary.main', '&.Mui-selected': { bgcolor: 'rgba(255,210,0,0.18)' } }}><ListItemIcon sx={{ minWidth: 34 }}><Icon fontSize="small" /></ListItemIcon><ListItemText primary={entry.text} /></MenuItem>;
            }
            const expanded = Boolean(mobileExpandedGroups[entry.id]);
            const isGroupActive = entry.children.some((child) => isActivePath(child.path));
            return <React.Fragment key={entry.id}>{index > 0 && <Divider sx={{ my: 0.45 }} />}<MenuItem onClick={() => toggleMobileGroup(entry.id)} aria-expanded={expanded} aria-controls={`mobile-${entry.id}`} sx={{ minHeight: 44, fontSize: 14, fontWeight: isGroupActive ? 800 : 700, color: 'secondary.main', bgcolor: isGroupActive ? 'rgba(255,210,0,0.12)' : 'transparent' }}><ListItemText primary={entry.text} /><ExpandMore sx={{ fontSize: 19, transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 150ms ease' }} /></MenuItem>{expanded && entry.children.map((child) => {
              const ChildIcon = child.icon;
              const active = isActivePath(child.path);
              return <MenuItem key={child.id} id={`mobile-${entry.id}`} selected={active} onClick={() => handleMobileNavigate(child.path)} sx={{ minHeight: 42, pl: 4, fontSize: 13.5, fontWeight: active ? 800 : 600, color: 'secondary.main', '&.Mui-selected': { bgcolor: 'rgba(255,210,0,0.18)' } }}><ListItemIcon sx={{ minWidth: 32 }}><ChildIcon fontSize="small" /></ListItemIcon><ListItemText primary={child.text} /></MenuItem>;
            })}</React.Fragment>;
          })}
        </Menu>
      </Toolbar>
    </AppBar>
  );
};

export default Navbar;
