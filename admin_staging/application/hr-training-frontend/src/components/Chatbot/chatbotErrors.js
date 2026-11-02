export function chatbotErrorMessage(error, isArabic, fallback, examLocked) {
  const status = error?.response?.status;
  const detail = String(error?.response?.data?.detail || error?.message || '');
  if (status === 504 || error?.code === 'ECONNABORTED' || /timed?\s*out|timeout/i.test(detail)) {
    return isArabic
      ? 'الرد استغرق وقتاً أطول من المتوقع. سياق المحادثة محفوظ؛ حاول إرسال السؤال مرة أخرى.'
      : 'The reply took too long. Your conversation context is saved; please send the question again.';
  }
  if (status === 423) return examLocked;
  if (status === 503) {
    return isArabic ? 'المساعد مشغول حالياً. حاول مرة أخرى بعد قليل.' : 'The assistant is busy. Please try again shortly.';
  }
  return fallback;
}
