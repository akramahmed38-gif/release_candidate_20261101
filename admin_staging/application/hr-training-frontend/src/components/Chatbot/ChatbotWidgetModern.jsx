import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { CircularProgress } from '@mui/material';
import api from '../../services/api';
import { authService } from '../../services/auth';
import { chatbotErrorMessage } from './chatbotErrors';
import { useLanguage } from '../../context/LanguageContext';
import { EXAM_CHAT_LOCK_EVENT, getActiveExamChatLock } from '../../utils/examChatLock';
import {
  CHATBOT_WELCOME_CONFIG,
  buildChatbotWelcomeMessage,
} from './chatbotWelcomeConfig';
import chatbotLogo from '../../../../chatbot/logo fawry clean.png';
import './ChatbotWidgetModern.css';

const CHATBOT_ENDPOINT = '/api/v1/chatbot/ask';
const FEEDBACK_ENDPOINT = '/api/v1/chatbot/feedback';
const INITIAL_WELCOME_DELAY_MS = 1800;
const CHATBOT_PANEL_ID = 'chatbot-widget-panel';
const LAUNCHER_AUTO_COLLAPSE_DELAY_MS = 4000;
const LAUNCHER_RECOLLAPSE_DELAY_MS = 900;

const UI_COPY = {
  ar: {
    welcomeTitle: '\u0645\u0631\u062d\u0628\u0627\u064b',
    welcomeSubtitle: '\u0643\u064a\u0641 \u064a\u0645\u0643\u0646\u0646\u064a \u0645\u0633\u0627\u0639\u062f\u062a\u0643\u061f',
    title: 'Fero',
    emptyState: '\u0627\u0643\u062a\u0628 \u0631\u0633\u0627\u0644\u062a\u0643 \u0648\u0627\u0636\u063a\u0637 \u0639\u0644\u0649 \u0632\u0631 "\u0627\u0644\u0625\u062f\u062e\u0627\u0644"',
    inputPlaceholder: '\u0627\u0643\u062a\u0628 \u0627\u0633\u062a\u0641\u0633\u0627\u0631\u0643',
    loading: '\u062c\u0627\u0631\u064a \u062a\u062c\u0647\u064a\u0632 \u0627\u0644\u0625\u062c\u0627\u0628\u0629...',
    sources: '\u0627\u0644\u0645\u0635\u0627\u062f\u0631',
    primary: '\u0645\u0635\u062f\u0631 \u0623\u0633\u0627\u0633\u064a',
    supporting: '\u0645\u0635\u062f\u0631 \u062f\u0627\u0639\u0645',
    feedbackLabel: '\u0647\u0644 \u0643\u0627\u0646\u062a \u0627\u0644\u0625\u062c\u0627\u0628\u0629 \u0645\u0641\u064a\u062f\u0629\u061f',
    feedbackUseful: '\u0645\u0641\u064a\u062f',
    feedbackWrong: '\u063a\u064a\u0631 \u0635\u062d\u064a\u062d',
    feedbackSaved: '\u062a\u0645 \u062a\u0633\u062c\u064a\u0644 \u0631\u0623\u064a\u0643.',
    feedbackError:
      '\u062a\u0639\u0630\u0631 \u0625\u0631\u0633\u0627\u0644 \u0627\u0644\u062a\u0642\u064a\u064a\u0645. \u062d\u0627\u0648\u0644 \u0645\u0631\u0629 \u0623\u062e\u0631\u0649.',
    unavailable:
      '\u0627\u0644\u0634\u0627\u062a \u0628\u0648\u062a \u063a\u064a\u0631 \u0645\u062a\u0627\u062d \u062d\u0627\u0644\u064a\u0627\u064b\u060c \u062d\u0627\u0648\u0644 \u0645\u0631\u0629 \u0623\u062e\u0631\u0649.',
    examLocked:
      '\u0627\u0644\u0634\u0627\u062a \u0628\u0648\u062a \u063a\u064a\u0631 \u0645\u062a\u0627\u062d \u0623\u062b\u0646\u0627\u0621 \u0627\u0644\u0627\u062e\u062a\u0628\u0627\u0631. \u064a\u0631\u062c\u0649 \u0625\u0631\u0633\u0627\u0644 \u0627\u0644\u0627\u062e\u062a\u0628\u0627\u0631 \u0623\u0648 \u0627\u0646\u062a\u0638\u0627\u0631 \u0627\u0646\u062a\u0647\u0627\u0621 \u0627\u0644\u0648\u0642\u062a.',
    openLauncher: '\u0641\u062a\u062d \u0645\u0633\u0627\u0639\u062f \u0627\u0644\u062f\u0631\u062f\u0634\u0629',
    closeLauncher: '\u0625\u063a\u0644\u0627\u0642 \u0645\u0633\u0627\u0639\u062f \u0627\u0644\u062f\u0631\u062f\u0634\u0629',
    sendMessage: '\u0625\u0631\u0633\u0627\u0644 \u0627\u0644\u0631\u0633\u0627\u0644\u0629',
  },
  en: {
    welcomeTitle: 'Welcome',
    welcomeSubtitle: 'How can I help you?',
    title: 'Fero',
    emptyState: 'Type your message and press Enter',
    inputPlaceholder: '\u0627\u0643\u062a\u0628 \u0627\u0633\u062a\u0641\u0633\u0627\u0631\u0643',
    loading: 'Preparing the answer...',
    sources: 'Sources',
    primary: 'Primary source',
    supporting: 'Supporting source',
    feedbackLabel: 'Was this helpful?',
    feedbackUseful: 'Useful',
    feedbackWrong: 'Wrong',
    feedbackSaved: 'Feedback saved.',
    feedbackError: 'Could not send feedback. Try again.',
    unavailable: 'The chatbot is currently unavailable. Please try again.',
    examLocked:
      'The chatbot is unavailable while your exam attempt is in progress. Please submit the exam or wait for the session to end.',
    openLauncher: 'Open chat assistant',
    closeLauncher: 'Close chat assistant',
    sendMessage: 'Send message',
  },
};

function buildMessageId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function nowMs() {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now();
  }
  return Date.now();
}

function roundLatency(value) {
  return Number(value.toFixed(2));
}

function buildWelcomeMessage(content, conversationId, sessionId) {
  return {
    id: buildMessageId('welcome'),
    messageId: null,
    requestId: null,
    conversationId,
    sessionId,
    role: 'assistant',
    content,
    sources: [],
    sourcePayload: [],
    question: '',
    type: 'welcome',
    clarification: null,
    isWelcome: true,
  };
}

function formatNameFromEmail(email) {
  if (typeof email !== 'string' || !email.includes('@')) {
    return '';
  }

  const localPart = email.split('@')[0].trim();
  if (!localPart) {
    return '';
  }

  const tokens = localPart
    .split(/[._-]+/)
    .map((token) => token.trim())
    .filter(Boolean);

  if (!tokens.length) {
    return localPart;
  }

  const hasArabic = tokens.some((token) => /[\u0600-\u06FF]/.test(token));
  if (hasArabic) {
    return tokens.join(' ');
  }

  return tokens
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1).toLowerCase())
    .join(' ');
}

function resolveWelcomeUserName(user) {
  const candidates = [
    user?.name,
    user?.full_name,
    user?.fullName,
    user?.display_name,
    user?.displayName,
    user?.username,
  ];

  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) {
      return candidate.trim();
    }
  }

  return formatNameFromEmail(user?.email);
}

function pushLatencyTrace(trace) {
  if (typeof window === 'undefined' || !trace) {
    return;
  }

  const storageKey = '__HR_TRAINING_CHATBOT_LATENCY_TRACES';
  const existingTraces = Array.isArray(window[storageKey]) ? window[storageKey] : [];
  window[storageKey] = [...existingTraces, trace].slice(-200);
}

function getOrCreateBrowserSessionId() {
  if (typeof window === 'undefined') {
    return buildMessageId('session');
  }

  const storageKey = 'hr_training_chatbot_session_id';
  const existingValue = window.sessionStorage.getItem(storageKey);
  if (existingValue) {
    return existingValue;
  }

  const nextValue = buildMessageId('session');
  window.sessionStorage.setItem(storageKey, nextValue);
  return nextValue;
}

function normalizeSource(source, index) {
  if (typeof source === 'string') {
    return {
      id: `source-${index}`,
      label: source,
      score: null,
      role: 'supporting',
      primarySource: false,
    };
  }

  const sourceName =
    source?.source_name || source?.file_name || source?.name || 'Training material';
  const locationLabel =
    source?.location_label || source?.page || source?.section || source?.slide || '';
  const score =
    typeof source?.score === 'number'
      ? source.score
      : typeof source?.final_score === 'number'
        ? source.final_score
        : null;
  const isPrimary = Boolean(source?.primary_source) || source?.role === 'primary';
  const labelParts = [sourceName, locationLabel].filter(Boolean);

  return {
    id: `source-${index}-${sourceName}-${locationLabel}`,
    label: labelParts.join(' \u2022 '),
    score,
    role: isPrimary ? 'primary' : 'supporting',
    primarySource: isPrimary,
  };
}

function extractChatbotPayload(responseData) {
  const nestedData =
    responseData?.data &&
    typeof responseData.data === 'object' &&
    (responseData.data.answer !== undefined || responseData.data.sources !== undefined)
      ? responseData.data
      : null;

  const payload = nestedData || responseData || {};
  const type = payload.type === 'clarification' ? 'clarification' : 'answer';
  const answer = typeof payload.answer === 'string' ? payload.answer.trim() : '';
  const rawSources = Array.isArray(payload.sources) ? payload.sources : [];
  const sources = rawSources.map(normalizeSource);
  const clarification =
    payload?.clarification && typeof payload.clarification === 'object'
      ? payload.clarification
      : null;

  return { type, answer, sources, rawSources, clarification };
}

function BrandLogo({ className, alt = '' }) {
  return (
    <img
      className={className}
      src={chatbotLogo}
      alt={alt}
      loading="eager"
      decoding="async"
      draggable="false"
    />
  );
}

function SendArrowIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M4 11.6 20 4l-4.9 16-2.8-6.1L4 11.6Z"
        fill="currentColor"
        opacity="0.24"
      />
      <path
        d="M4 11.6 20 4l-7.7 9.9"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="m9.4 13.6 5.7 6.4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CloseIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M6 6 18 18M18 6 6 18"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ThumbIcon({ className, direction = 'up' }) {
  const path =
    direction === 'up'
      ? 'M10.9 4.4c.3-1 .8-1.6 1.8-1.6 1.2 0 1.9.9 1.9 2.2v2.5h3.3c1.3 0 2.1 1.1 1.8 2.3l-1.2 5.4c-.2 1-1.1 1.8-2.1 1.8h-7c-.8 0-1.5-.7-1.5-1.5V9.7c0-.4.2-.8.5-1.1l1.8-1.8Z M4.5 9.3h2.3V17H4.5c-.8 0-1.5-.7-1.5-1.5v-4.7c0-.8.7-1.5 1.5-1.5Z'
      : 'M13.1 19.6c-.3 1-.8 1.6-1.8 1.6-1.2 0-1.9-.9-1.9-2.2v-2.5H6.1c-1.3 0-2.1-1.1-1.8-2.3l1.2-5.4c.2-1 1.1-1.8 2.1-1.8h7c.8 0 1.5.7 1.5 1.5v5.8c0 .4-.2.8-.5 1.1l-1.8 1.8Z M19.5 14.7h-2.3V7h2.3c.8 0 1.5.7 1.5 1.5v4.7c0 .8-.7 1.5-1.5 1.5Z';

  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d={path} fill="currentColor" />
    </svg>
  );
}

function ChatbotWidgetModern() {
  const { isArabic } = useLanguage();
  const uiText = isArabic ? UI_COPY.ar : UI_COPY.en;
  const currentUser = authService.getCurrentUser();
  const welcomeConfig = CHATBOT_WELCOME_CONFIG.ar;
  const welcomeMessage = buildChatbotWelcomeMessage(resolveWelcomeUserName(currentUser));
  const [isOpen, setIsOpen] = useState(false);
  const [isLauncherVisible, setIsLauncherVisible] = useState(false);
  const [isMessageExpanded, setIsMessageExpanded] = useState(true);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isWelcomePending, setIsWelcomePending] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [messages, setMessages] = useState([]);
  const [feedbackByMessageId, setFeedbackByMessageId] = useState({});
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  const [sessionId] = useState(() => getOrCreateBrowserSessionId());
  const [conversationId, setConversationId] = useState(() => buildMessageId('conversation'));
  const [examChatLock, setExamChatLock] = useState(() =>
    getActiveExamChatLock(authService.getCurrentUser())
  );
  const inputRef = useRef(null);
  const messagesEndRef = useRef(null);
  const pendingLatencyByMessageIdRef = useRef(new Map());
  const welcomeTimerRef = useRef(null);
  const launcherCollapseTimerRef = useRef(null);
  const launcherVisibilityFrameRef = useRef(null);
  const launcherVisibilityTimeoutRef = useRef(null);
  const isLauncherHoveredRef = useRef(false);
  const isLauncherFocusWithinRef = useRef(false);
  const hasScheduledInitialCollapseRef = useRef(false);
  const isOpenRef = useRef(false);
  const shouldRestoreInputFocusRef = useRef(false);
  const suppressMobileFocusRestoreRef = useRef(false);
  const isCoarsePointerRef = useRef(false);
  const isChatLocked = Boolean(examChatLock?.locked);

  const focusInput = () => {
    const input = inputRef.current;
    if (!input) {
      return;
    }

    try {
      input.focus({ preventScroll: true });
    } catch (error) {
      input.focus();
    }
  };

  const clearWelcomeTimer = () => {
    if (welcomeTimerRef.current) {
      window.clearTimeout(welcomeTimerRef.current);
      welcomeTimerRef.current = null;
    }
  };

  const clearLauncherCollapseTimer = () => {
    if (launcherCollapseTimerRef.current) {
      window.clearTimeout(launcherCollapseTimerRef.current);
      launcherCollapseTimerRef.current = null;
    }
  };

  const clearLauncherVisibilityTimers = () => {
    if (launcherVisibilityFrameRef.current !== null) {
      window.cancelAnimationFrame(launcherVisibilityFrameRef.current);
      launcherVisibilityFrameRef.current = null;
    }
    if (launcherVisibilityTimeoutRef.current !== null) {
      window.clearTimeout(launcherVisibilityTimeoutRef.current);
      launcherVisibilityTimeoutRef.current = null;
    }
  };

  const scheduleLauncherCollapse = (delayMs = LAUNCHER_RECOLLAPSE_DELAY_MS) => {
    clearLauncherCollapseTimer();

    launcherCollapseTimerRef.current = window.setTimeout(() => {
      if (
        isOpenRef.current ||
        isLauncherHoveredRef.current ||
        isLauncherFocusWithinRef.current
      ) {
        return;
      }

      setIsMessageExpanded(false);
      launcherCollapseTimerRef.current = null;
    }, delayMs);
  };

  const expandLauncherMessage = (collapseDelayMs = null) => {
    clearLauncherCollapseTimer();
    setIsMessageExpanded(true);

    if (collapseDelayMs !== null && !isOpenRef.current) {
      scheduleLauncherCollapse(collapseDelayMs);
    }
  };

  const handleLauncherMouseEnter = () => {
    isLauncherHoveredRef.current = true;
    expandLauncherMessage();
  };

  const handleLauncherMouseLeave = () => {
    isLauncherHoveredRef.current = false;
    if (!isLauncherFocusWithinRef.current && !isOpenRef.current) {
      scheduleLauncherCollapse();
    }
  };

  const handleLauncherFocusCapture = () => {
    isLauncherFocusWithinRef.current = true;
    expandLauncherMessage();
  };

  const handleLauncherBlurCapture = (event) => {
    const nextTarget = event.relatedTarget;
    if (event.currentTarget.contains(nextTarget)) {
      return;
    }

    isLauncherFocusWithinRef.current = false;
    if (!isLauncherHoveredRef.current && !isOpenRef.current) {
      scheduleLauncherCollapse();
    }
  };

  useEffect(() => {
    const refreshChatLock = () => {
      setExamChatLock(getActiveExamChatLock(authService.getCurrentUser()));
    };

    refreshChatLock();
    window.addEventListener(EXAM_CHAT_LOCK_EVENT, refreshChatLock);
    window.addEventListener('storage', refreshChatLock);
    return () => {
      window.removeEventListener(EXAM_CHAT_LOCK_EVENT, refreshChatLock);
      window.removeEventListener('storage', refreshChatLock);
    };
  }, []);

  useEffect(() => {
    isOpenRef.current = isOpen;
  }, [isOpen]);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }

    const mediaQuery = window.matchMedia('(pointer: coarse)');
    const updatePointerType = () => {
      isCoarsePointerRef.current = mediaQuery.matches;
    };

    updatePointerType();

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', updatePointerType);
      return () => mediaQuery.removeEventListener('change', updatePointerType);
    }

    mediaQuery.addListener(updatePointerType);
    return () => mediaQuery.removeListener(updatePointerType);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }

    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updateMotionPreference = () => {
      setPrefersReducedMotion(mediaQuery.matches);
    };

    updateMotionPreference();

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', updateMotionPreference);
      return () => mediaQuery.removeEventListener('change', updateMotionPreference);
    }

    mediaQuery.addListener(updateMotionPreference);
    return () => mediaQuery.removeListener(updateMotionPreference);
  }, []);

  useEffect(() => {
    clearLauncherVisibilityTimers();
    setIsLauncherVisible(false);

    if (prefersReducedMotion) {
      setIsLauncherVisible(true);
      return undefined;
    }

    launcherVisibilityFrameRef.current = window.requestAnimationFrame(() => {
      launcherVisibilityTimeoutRef.current = window.setTimeout(() => {
        setIsLauncherVisible(true);
        launcherVisibilityTimeoutRef.current = null;
      }, 20);
    });

    return () => {
      clearLauncherVisibilityTimers();
    };
  }, [prefersReducedMotion]);

  useEffect(() => {
    if (isChatLocked) {
      clearLauncherCollapseTimer();
      return;
    }

    if (isOpen) {
      clearLauncherCollapseTimer();
      setIsMessageExpanded(true);
      return;
    }

    if (!hasScheduledInitialCollapseRef.current) {
      const readyToCollapse = prefersReducedMotion || isLauncherVisible;
      if (!readyToCollapse) {
        return;
      }

      hasScheduledInitialCollapseRef.current = true;
      clearLauncherCollapseTimer();
      setIsMessageExpanded(true);
      launcherCollapseTimerRef.current = window.setTimeout(() => {
        if (
          isOpenRef.current ||
          isLauncherHoveredRef.current ||
          isLauncherFocusWithinRef.current
        ) {
          return;
        }

        setIsMessageExpanded(false);
        launcherCollapseTimerRef.current = null;
      }, LAUNCHER_AUTO_COLLAPSE_DELAY_MS);
    }
  }, [isChatLocked, isLauncherVisible, isOpen, prefersReducedMotion]);

  useEffect(() => {
    return () => {
      clearWelcomeTimer();
      clearLauncherCollapseTimer();
      clearLauncherVisibilityTimers();
    };
  }, []);

  useEffect(() => {
    if (!isChatLocked) {
      return;
    }
    setIsOpen(false);
    setIsLoading(false);
    setIsWelcomePending(false);
    setErrorMessage('');
    setIsMessageExpanded(true);
  }, [isChatLocked]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [isLoading, isOpen, isWelcomePending, messages]);

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    const focusTimer = window.setTimeout(() => focusInput(), 140);
    return () => window.clearTimeout(focusTimer);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || isLoading || !shouldRestoreInputFocusRef.current) {
      return undefined;
    }

    if (suppressMobileFocusRestoreRef.current) {
      shouldRestoreInputFocusRef.current = false;
      suppressMobileFocusRestoreRef.current = false;
      return undefined;
    }

    const focusFrame = window.requestAnimationFrame(() => {
      focusInput();
      shouldRestoreInputFocusRef.current = false;
      suppressMobileFocusRestoreRef.current = false;
    });

    return () => window.cancelAnimationFrame(focusFrame);
  }, [isLoading, isOpen, messages.length]);

  useEffect(() => {
    const input = inputRef.current;
    if (!input) {
      return;
    }

    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 148)}px`;
  }, [inputValue, isOpen]);

  useEffect(() => {
    messages.forEach((message) => {
      const pendingTrace = pendingLatencyByMessageIdRef.current.get(message.id);
      if (!pendingTrace) {
        return;
      }

      const renderCommittedAtMs = nowMs();
      const finalizedTrace = {
        ...pendingTrace,
        frontend: {
          ...pendingTrace.frontend,
          renderCommittedAtMs,
          renderCommitMs: roundLatency(
            renderCommittedAtMs - pendingTrace.frontend.renderQueuedAtMs
          ),
          totalClientMs: roundLatency(
            renderCommittedAtMs - pendingTrace.frontend.submitStartedAtMs
          ),
        },
      };
      pushLatencyTrace(finalizedTrace);
      pendingLatencyByMessageIdRef.current.delete(message.id);
    });
  }, [messages]);

  const appendAssistantMessage = (
    content,
    sources = [],
    question = '',
    sourcePayload = [],
    metadata = {},
  ) => {
    const assistantMessageId = `${metadata.messageId || buildMessageId('assistant')}-assistant`;
    setMessages((currentMessages) => [
      ...currentMessages,
      {
        id: assistantMessageId,
        messageId: metadata.messageId || null,
        requestId: metadata.requestId || null,
        conversationId: metadata.conversationId || conversationId,
        sessionId: metadata.sessionId || sessionId,
        role: 'assistant',
        content,
        sources,
        sourcePayload,
        question,
        type: metadata.type || 'answer',
        clarification: metadata.clarification || null,
      },
    ]);
    return assistantMessageId;
  };

  const ensureWelcomeMessage = () => {
    clearWelcomeTimer();
    setIsWelcomePending(true);
    welcomeTimerRef.current = window.setTimeout(() => {
      setMessages((currentMessages) => {
        if (currentMessages.length > 0) {
          return currentMessages;
        }
        return [buildWelcomeMessage(welcomeMessage, conversationId, sessionId)];
      });
      setIsWelcomePending(false);
      welcomeTimerRef.current = null;
    }, INITIAL_WELCOME_DELAY_MS);
  };

  const sendQuestion = async (question) => {
    if (!question || isLoading || isChatLocked) {
      return;
    }

    clearWelcomeTimer();
    setIsWelcomePending(false);
    setErrorMessage('');
    const exchangeMessageId = buildMessageId('message');
    const requestId = buildMessageId('request');
    const activeConversationId = conversationId;
    const submitStartedAtMs = nowMs();
    setMessages((currentMessages) => [
      ...currentMessages,
      {
        id: `${exchangeMessageId}-user`,
        messageId: exchangeMessageId,
        requestId,
        conversationId: activeConversationId,
        sessionId,
        role: 'user',
        content: question,
        sources: [],
      },
    ]);
    setIsLoading(true);

    try {
      const requestPayload = {
        question,
        request_id: requestId,
        session_id: sessionId,
        conversation_id: activeConversationId,
        message_id: exchangeMessageId,
      };
      const requestPreparedAtMs = nowMs();
      const response = await api.post(CHATBOT_ENDPOINT, requestPayload);
      const responseReceivedAtMs = nowMs();
      const { type, answer, sources, rawSources, clarification } = extractChatbotPayload(
        response?.data
      );
      const responseParsedAtMs = nowMs();
      const responseConversationId = response?.data?.conversation_id || activeConversationId;
      const responseSessionId = response?.data?.session_id || sessionId;
      const responseMessageId = response?.data?.message_id || exchangeMessageId;
      const responseRequestId = response?.data?.request_id || requestId;
      const frontendLatency = {
        requestId: responseRequestId,
        frontend: {
          submitStartedAtMs,
          requestPreparedAtMs,
          responseReceivedAtMs,
          responseParsedAtMs,
          requestPrepareMs: roundLatency(requestPreparedAtMs - submitStartedAtMs),
          networkRoundtripMs: roundLatency(responseReceivedAtMs - requestPreparedAtMs),
          responseParseMs: roundLatency(responseParsedAtMs - responseReceivedAtMs),
          renderQueuedAtMs: nowMs(),
        },
      };

      if (!answer) {
        setErrorMessage(uiText.unavailable);
        setInputValue((current) => current || question);
        return;
      }

      const assistantMessageId = appendAssistantMessage(answer, sources, question, rawSources, {
        messageId: responseMessageId,
        requestId: responseRequestId,
        conversationId: responseConversationId,
        sessionId: responseSessionId,
        type,
        clarification,
      });
      pendingLatencyByMessageIdRef.current.set(assistantMessageId, frontendLatency);
    } catch (error) {
      const serverMessage = chatbotErrorMessage(error, isArabic, uiText.unavailable, uiText.examLocked);
      setErrorMessage(serverMessage);
      setInputValue((current) => current || question);
    } finally {
      setIsLoading(false);
    }
  };

  const handleOpen = () => {
    if (isChatLocked) {
      return;
    }
    clearLauncherCollapseTimer();
    setIsMessageExpanded(true);
    setIsOpen(true);
    if (messages.length === 0) {
      ensureWelcomeMessage();
    }
  };

  const handleClose = () => {
    if (messages.length === 0) {
      clearWelcomeTimer();
      setIsWelcomePending(false);
    }
    shouldRestoreInputFocusRef.current = false;
    suppressMobileFocusRestoreRef.current = false;
    setIsOpen(false);
    expandLauncherMessage(
      isLauncherHoveredRef.current || isLauncherFocusWithinRef.current
        ? null
        : LAUNCHER_RECOLLAPSE_DELAY_MS
    );
  };

  const handleFeedback = async (message, rating) => {
    if (!message?.question || !message?.content) {
      return;
    }

    const feedbackState = feedbackByMessageId[message.id]?.status;
    if (feedbackState === 'pending' || feedbackState === 'sent') {
      return;
    }

    setFeedbackByMessageId((currentValue) => ({
      ...currentValue,
      [message.id]: { status: 'pending', rating },
    }));

    try {
      await api.post(FEEDBACK_ENDPOINT, {
        question: message.question,
        answer: message.content,
        sources: message.sourcePayload || [],
        rating,
        timestamp: new Date().toISOString(),
        session_id: message.sessionId || sessionId,
        conversation_id: message.conversationId || conversationId,
        message_id: message.messageId || null,
      });
      setFeedbackByMessageId((currentValue) => ({
        ...currentValue,
        [message.id]: { status: 'sent', rating },
      }));
    } catch (error) {
      setFeedbackByMessageId((currentValue) => ({
        ...currentValue,
        [message.id]: { status: 'error', rating },
      }));
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    const question = inputValue.trim();
    if (!question || isLoading || isChatLocked) {
      return;
    }

    shouldRestoreInputFocusRef.current = true;
    suppressMobileFocusRestoreRef.current = false;
    setInputValue('');
    await sendQuestion(question);
  };

  const handleInputKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSubmit(event);
    }
  };

  const handleInputBlur = () => {
    if (isLoading && isCoarsePointerRef.current) {
      suppressMobileFocusRestoreRef.current = true;
    }
  };

  const hasConversation = messages.length > 0 || isLoading || isWelcomePending;
  if (isChatLocked) {
    return null;
  }

  const widgetMarkup = (
    <aside
      className={`chatbot-widget-modern${isOpen ? ' chatbot-widget-modern--open' : ''}`}
      dir={isArabic ? 'rtl' : 'ltr'}
      aria-label="Chat widget"
    >
      <section
        id={CHATBOT_PANEL_ID}
        className="chatbot-widget-modern__panel"
        role="dialog"
        aria-modal="false"
        aria-hidden={!isOpen}
        aria-labelledby="chatbot-widget-title"
        data-testid="chatbot-panel"
      >
        <header className="chatbot-widget-modern__header">
          <button
            type="button"
            className="chatbot-widget-modern__close"
            aria-label={uiText.closeLauncher}
            onClick={handleClose}
          >
            <CloseIcon className="chatbot-widget-modern__close-icon" />
          </button>

          <div className="chatbot-widget-modern__header-main">
            <div className="chatbot-widget-modern__header-icon" aria-hidden="true">
              <span className="chatbot-widget-modern__header-icon-shell">
                <BrandLogo
                  className="chatbot-widget-modern__brand-logo chatbot-widget-modern__brand-logo--small"
                />
              </span>
            </div>

            <div className="chatbot-widget-modern__header-copy">
              <h2 id="chatbot-widget-title" className="chatbot-widget-modern__title">
                {uiText.title}
              </h2>
              <span className="chatbot-widget-modern__sr-only">Fero</span>
            </div>
          </div>

          <button type="button" disabled={isLoading} onClick={() => {
            clearWelcomeTimer();
            setIsWelcomePending(false);
            setMessages([]);
            setFeedbackByMessageId({});
            setErrorMessage('');
            setInputValue('');
            setConversationId(buildMessageId('conversation'));
          }} className="chatbot-widget-modern__new-chat">
            {isArabic ? 'محادثة جديدة' : 'New chat'}
          </button>
        </header>

        <div className="chatbot-widget-modern__body">
          <div
            className={`chatbot-widget-modern__surface${hasConversation ? '' : ' chatbot-widget-modern__surface--empty'}`}
            aria-live="polite"
          >
            {!hasConversation ? (
              <div className="chatbot-widget-modern__empty-state">
                <p className="chatbot-widget-modern__empty-hint">{uiText.emptyState}</p>
              </div>
            ) : (
              <div className="chatbot-widget-modern__message-list">
                {isWelcomePending ? (
                  <article className="chatbot-widget-modern__message chatbot-widget-modern__message--assistant chatbot-widget-modern__message--typing">
                    <div className="chatbot-widget-modern__typing" aria-label="Fero is typing">
                      <span className="chatbot-widget-modern__typing-dot" />
                      <span className="chatbot-widget-modern__typing-dot" />
                      <span className="chatbot-widget-modern__typing-dot" />
                    </div>
                  </article>
                ) : null}

                {messages.map((message) => (
                  <React.Fragment key={message.id}>
                    <article
                      className={`chatbot-widget-modern__message chatbot-widget-modern__message--${message.role}${
                        message.isWelcome ? ' chatbot-widget-modern__message--welcome' : ''
                      }`}
                    >
                      {message.isWelcome ? (
                        <div className="chatbot-widget-modern__welcome-message">
                          <span
                            className="chatbot-widget-modern__welcome-avatar"
                            aria-hidden="true"
                          >
                            <BrandLogo
                              className="chatbot-widget-modern__brand-logo chatbot-widget-modern__brand-logo--small"
                            />
                          </span>
                          <div className="chatbot-widget-modern__welcome-copy">
                            <span className="chatbot-widget-modern__welcome-label">
                              {welcomeConfig.assistantLabel}
                            </span>
                            <p className="chatbot-widget-modern__message-text" dir="auto">
                              {message.content}
                            </p>
                          </div>
                        </div>
                      ) : (
                        <p className="chatbot-widget-modern__message-text" dir="auto">
                          {message.content}
                        </p>
                      )}

                      {message.role === 'assistant' &&
                      message.question &&
                      message.type !== 'clarification' ? (
                        <div className="chatbot-widget-modern__feedback">
                          <span className="chatbot-widget-modern__feedback-label">
                            {uiText.feedbackLabel}
                          </span>

                          <div className="chatbot-widget-modern__feedback-actions">
                            <button
                              type="button"
                              className={`chatbot-widget-modern__feedback-button${
                                feedbackByMessageId[message.id]?.rating === 'useful'
                                  ? ' is-active'
                                  : ''
                              }`}
                              onClick={() => handleFeedback(message, 'useful')}
                              disabled={
                                feedbackByMessageId[message.id]?.status === 'pending' ||
                                feedbackByMessageId[message.id]?.status === 'sent'
                              }
                            >
                              <ThumbIcon
                                className="chatbot-widget-modern__thumb-icon"
                                direction="up"
                              />
                              <span>{uiText.feedbackUseful}</span>
                            </button>

                            <button
                              type="button"
                              className={`chatbot-widget-modern__feedback-button chatbot-widget-modern__feedback-button--negative${
                                feedbackByMessageId[message.id]?.rating === 'wrong'
                                  ? ' is-active'
                                  : ''
                              }`}
                              onClick={() => handleFeedback(message, 'wrong')}
                              disabled={
                                feedbackByMessageId[message.id]?.status === 'pending' ||
                                feedbackByMessageId[message.id]?.status === 'sent'
                              }
                            >
                              <ThumbIcon
                                className="chatbot-widget-modern__thumb-icon"
                                direction="down"
                              />
                              <span>{uiText.feedbackWrong}</span>
                            </button>
                          </div>

                          {feedbackByMessageId[message.id]?.status === 'sent' ? (
                            <span className="chatbot-widget-modern__feedback-status">
                              {uiText.feedbackSaved}
                            </span>
                          ) : null}

                          {feedbackByMessageId[message.id]?.status === 'error' ? (
                            <span className="chatbot-widget-modern__feedback-status chatbot-widget-modern__feedback-status--error">
                              {uiText.feedbackError}
                            </span>
                          ) : null}
                        </div>
                      ) : null}
                    </article>

                  </React.Fragment>
                ))}

                {isLoading ? (
                  <article className="chatbot-widget-modern__message chatbot-widget-modern__message--assistant chatbot-widget-modern__message--loading">
                    <CircularProgress size={18} thickness={4.6} />
                    <span>{uiText.loading}</span>
                  </article>
                ) : null}

                <div ref={messagesEndRef} />
              </div>
            )}
          </div>
        </div>

        {errorMessage ? (
          <div className="chatbot-widget-modern__error" role="status">
            {errorMessage}
          </div>
        ) : null}

        <form className="chatbot-widget-modern__composer" onSubmit={handleSubmit}>
          <div className="chatbot-widget-modern__input-wrap">
            <label
              className="chatbot-widget-modern__sr-only"
              htmlFor="chatbot-widget-input"
            >
              Ask Fero
            </label>
            <textarea
              id="chatbot-widget-input"
              ref={inputRef}
              className="chatbot-widget-modern__input"
              placeholder={uiText.inputPlaceholder}
              rows={1}
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              onKeyDown={handleInputKeyDown}
              onBlur={handleInputBlur}
              readOnly={isLoading}
              aria-busy={isLoading}
              tabIndex={isOpen ? 0 : -1}
            />
            <button
              type="submit"
              className="chatbot-widget-modern__send"
              aria-label={uiText.sendMessage}
              onMouseDown={(event) => event.preventDefault()}
              disabled={isLoading || !inputValue.trim()}
              tabIndex={isOpen ? 0 : -1}
            >
              {isLoading ? (
                <CircularProgress size={18} color="inherit" />
              ) : (
                <SendArrowIcon className="chatbot-widget-modern__send-icon" />
              )}
            </button>
          </div>
        </form>
      </section>

      <div
        className={`chatbot-widget-modern__compact${isLauncherVisible ? ' is-visible' : ''}${
          isMessageExpanded || isOpen ? ' is-message-expanded' : ' is-message-collapsed'
        }`}
        onMouseEnter={handleLauncherMouseEnter}
        onMouseLeave={handleLauncherMouseLeave}
        onFocusCapture={handleLauncherFocusCapture}
        onBlurCapture={handleLauncherBlurCapture}
      >
        {!isOpen ? (
          <button
            type="button"
            className={`chatbot-widget-modern__welcome${
              isMessageExpanded ? '' : ' is-collapsed'
            }`}
            aria-label={uiText.openLauncher}
            aria-controls={CHATBOT_PANEL_ID}
            aria-expanded={isOpen}
            aria-haspopup="dialog"
            aria-hidden={!isMessageExpanded}
            dir={isArabic ? 'rtl' : 'ltr'}
            onClick={handleOpen}
            tabIndex={isMessageExpanded ? 0 : -1}
          >
            <span className="chatbot-widget-modern__welcome-title">
              {uiText.welcomeTitle}
            </span>
            <span className="chatbot-widget-modern__welcome-subtitle">
              {uiText.welcomeSubtitle}
            </span>
          </button>
        ) : null}

        <button
          type="button"
          className="chatbot-widget-modern__fab"
          aria-label={uiText.openLauncher}
          aria-controls={CHATBOT_PANEL_ID}
          aria-expanded={isOpen}
          aria-haspopup="dialog"
          data-testid="chatbot-toggle"
          onClick={handleOpen}
        >
          <BrandLogo className="chatbot-widget-modern__brand-logo chatbot-widget-modern__brand-logo--launcher" />
        </button>
      </div>
    </aside>
  );

  return createPortal(widgetMarkup, document.body);
}

export default ChatbotWidgetModern;
