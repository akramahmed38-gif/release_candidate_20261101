import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

const LanguageContext = createContext({
  lang: 'en',
  isArabic: false,
  setLanguage: () => {},
  toggleLanguage: () => {},
  t: (enText, arText) => enText,
});

function getInitialLanguage() {
  if (typeof window === 'undefined') {
    return 'en';
  }
  const queryLang = new URLSearchParams(window.location.search).get('lang');
  if (queryLang === 'ar' || queryLang === 'en') {
    localStorage.setItem('app_lang', queryLang);
    return queryLang;
  }
  return localStorage.getItem('app_lang') === 'ar' ? 'ar' : 'en';
}

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(getInitialLanguage);
  const isArabic = lang === 'ar';

  useEffect(() => {
    localStorage.setItem('app_lang', lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = isArabic ? 'rtl' : 'ltr';
    document.title = isArabic ? 'نظام التدريب' : 'Training System';
  }, [isArabic, lang]);

  const value = useMemo(
    () => ({
      lang,
      isArabic,
      setLanguage: (next) => setLang(next === 'ar' ? 'ar' : 'en'),
      toggleLanguage: () => setLang((prev) => (prev === 'ar' ? 'en' : 'ar')),
      t: (enText, arText) => (isArabic ? arText : enText),
    }),
    [isArabic, lang]
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  return useContext(LanguageContext);
}
