export const CHATBOT_WELCOME_CONFIG = {
  ar: {
    assistantLabel: 'Fero',
  },
  en: {
    assistantLabel: 'Fero',
  },
};

export function buildChatbotWelcomeMessage(displayName = '') {
  const normalizedName = typeof displayName === 'string' ? displayName.trim() : '';
  const greetingLine = normalizedName
    ? `أهلاً بيك ${normalizedName} 👋`
    : 'أهلاً بيك 👋';

  return [
    greetingLine,
    'أنا فيرو، مساعدك الذكي من فوري بلس ✨',
    'موجود معاك 24 ساعة علشان أجاوبك على أي استفسار',
    'خلّينا نبدأ، أساعدك إزاي؟',
  ].join('\n');
}
