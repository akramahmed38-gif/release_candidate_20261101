import React, { useEffect, useRef, useState } from 'react';
import {
  CircularProgress,
  IconButton,
  Tooltip,
} from '@mui/material';
import ChatBubbleOutlineRoundedIcon from '@mui/icons-material/ChatBubbleOutlineRounded';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import SendRoundedIcon from '@mui/icons-material/SendRounded';
import SmartToyRoundedIcon from '@mui/icons-material/SmartToyRounded';
import api from '../../services/api';
import { useLanguage } from '../../context/LanguageContext';
import './ChatbotWidget.css';

const CHATBOT_ENDPOINT = '/api/v1/chatbot/ask';
const FEEDBACK_ENDPOINT = '/api/v1/chatbot/feedback';
const FRIENDLY_ERROR_MESSAGE = 'الشات بوت غير متاح حالياً، حاول مرة أخرى.';
const WELCOME_MESSAGE = {
  id: 'welcome-message',
  role: 'assistant',
  content: 'اسأل عن أي إجراء أو معلومة موجودة داخل مواد التدريب المتاحة.',
  sources: [],
  sourcePayload: [],
  question: '',
};

function buildMessageId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function normalizeSource(source, index) {
  if (typeof source === 'string') {
    return {
      id: `source-${index}`,
      label: source,
    };
  }

  const sourceName = source?.source_name || source?.file_name || source?.name || 'Training material';
  const locationLabel = source?.location_label || source?.page || source?.section || source?.slide || '';
  const score = typeof source?.score === 'number'
    ? source.score
    : (typeof source?.final_score === 'number' ? source.final_score : null);
  const labelParts = [sourceName, locationLabel].filter(Boolean);

  return {
    id: `source-${index}-${sourceName}-${locationLabel}`,
    label: labelParts.join(' • '),
    score,
    role: source?.role === 'primary' ? 'primary' : 'supporting',
    primarySource: Boolean(source?.primary_source),
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
  const answer = typeof payload.answer === 'string' ? payload.answer.trim() : '';
  const rawSources = Array.isArray(payload.sources) ? payload.sources : [];
  const sources = rawSources.map(normalizeSource);

  return { answer, sources, rawSources };
}

function ChatbotWidget() {
  const { isArabic } = useLanguage();
  const [isOpen, setIsOpen] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [messages, setMessages] = useState([WELCOME_MESSAGE]);
  const [feedbackByMessageId, setFeedbackByMessageId] = useState({});
  const inputRef = useRef(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [isLoading, isOpen, messages]);

  useEffect(() => {
    if (isOpen) {
      window.setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  const appendAssistantMessage = (content, sources = [], question = '', sourcePayload = []) => {
    setMessages((currentMessages) => [
      ...currentMessages,
      {
        id: buildMessageId('assistant'),
        role: 'assistant',
        content,
        sources,
        sourcePayload,
        question,
      },
    ]);
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
    if (!question || isLoading) {
      return;
    }

    setErrorMessage('');
    setInputValue('');
    setMessages((currentMessages) => [
      ...currentMessages,
      {
        id: buildMessageId('user'),
        role: 'user',
        content: question,
        sources: [],
      },
    ]);
    setIsLoading(true);

    try {
      const response = await api.post(CHATBOT_ENDPOINT, { question });
      const { answer, sources, rawSources } = extractChatbotPayload(response?.data);

      if (!answer) {
        setErrorMessage(FRIENDLY_ERROR_MESSAGE);
        appendAssistantMessage(FRIENDLY_ERROR_MESSAGE, [], question, []);
        return;
      }

      appendAssistantMessage(answer, sources, question, rawSources);
    } catch (error) {
      setErrorMessage(FRIENDLY_ERROR_MESSAGE);
      appendAssistantMessage(FRIENDLY_ERROR_MESSAGE, [], question, []);
    } finally {
      setIsLoading(false);
    }
  };

  const handleInputKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSubmit(event);
    }
  };

  return (
    <div className="chatbot-widget" dir={isArabic ? 'rtl' : 'ltr'}>
      {isOpen ? (
        <section
          className="chatbot-widget__panel"
          aria-label="Fawry Assistant"
          data-testid="chatbot-panel"
        >
          <header className="chatbot-widget__header">
            <div className="chatbot-widget__header-content">
              <div className="chatbot-widget__avatar" aria-hidden="true">
                <SmartToyRoundedIcon fontSize="small" />
              </div>
              <div>
                <h2 className="chatbot-widget__title">Fawry Assistant</h2>
                <p className="chatbot-widget__subtitle">Answers from training materials only</p>
              </div>
            </div>
            <IconButton
              aria-label="Close chatbot"
              className="chatbot-widget__close"
              onClick={() => setIsOpen(false)}
              size="small"
            >
              <CloseRoundedIcon fontSize="small" />
            </IconButton>
          </header>

          <div className="chatbot-widget__messages" aria-live="polite">
            {messages.map((message) => (
              <article
                key={message.id}
                className={`chatbot-widget__message chatbot-widget__message--${message.role}`}
              >
                <p className="chatbot-widget__message-text" dir="auto">
                  {message.content}
                </p>
                {false ? (
                  <div className="chatbot-widget__sources">
                    <span className="chatbot-widget__sources-label">Sources</span>
                    <ul className="chatbot-widget__sources-list">
                      {message.sources.map((source) => (
                        <li key={source.id} className="chatbot-widget__source-item" dir="auto">
                          <span className="chatbot-widget__source-copy">
                            <span>{source.label}</span>
                            <span className={`chatbot-widget__source-role chatbot-widget__source-role--${source.role}`}>
                              {source.role === 'primary'
                                ? (isArabic ? 'مصدر أساسي' : 'Primary')
                                : (isArabic ? 'مصدر داعم' : 'Supporting')}
                            </span>
                          </span>
                          {source.score !== null ? (
                            <span className="chatbot-widget__source-score">
                              {(source.score * 100).toFixed(0)}%
                            </span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {message.role === 'assistant' && message.question ? (
                  <div className="chatbot-widget__feedback">
                    <span className="chatbot-widget__feedback-label">
                      {isArabic ? 'هل كانت الإجابة مفيدة؟' : 'Was this helpful?'}
                    </span>
                    <div className="chatbot-widget__feedback-actions">
                      <button
                        type="button"
                        className={`chatbot-widget__feedback-button${feedbackByMessageId[message.id]?.rating === 'useful' ? ' is-active' : ''}`}
                        onClick={() => handleFeedback(message, 'useful')}
                        disabled={feedbackByMessageId[message.id]?.status === 'pending' || feedbackByMessageId[message.id]?.status === 'sent'}
                      >
                        👍 Useful
                      </button>
                      <button
                        type="button"
                        className={`chatbot-widget__feedback-button chatbot-widget__feedback-button--negative${feedbackByMessageId[message.id]?.rating === 'wrong' ? ' is-active' : ''}`}
                        onClick={() => handleFeedback(message, 'wrong')}
                        disabled={feedbackByMessageId[message.id]?.status === 'pending' || feedbackByMessageId[message.id]?.status === 'sent'}
                      >
                        👎 Wrong
                      </button>
                    </div>
                    {feedbackByMessageId[message.id]?.status === 'sent' ? (
                      <span className="chatbot-widget__feedback-status">
                        {isArabic ? 'تم تسجيل رأيك.' : 'Feedback saved.'}
                      </span>
                    ) : null}
                    {feedbackByMessageId[message.id]?.status === 'error' ? (
                      <span className="chatbot-widget__feedback-status chatbot-widget__feedback-status--error">
                        {isArabic ? 'تعذر إرسال التقييم. حاول مرة أخرى.' : 'Could not send feedback. Try again.'}
                      </span>
                    ) : null}
                  </div>
                ) : null}
              </article>
            ))}

            {isLoading ? (
              <article className="chatbot-widget__message chatbot-widget__message--assistant chatbot-widget__message--loading">
                <CircularProgress size={18} thickness={4.6} />
                <span>جاري تجهيز الإجابة...</span>
              </article>
            ) : null}

            <div ref={messagesEndRef} />
          </div>

          {errorMessage ? (
            <div className="chatbot-widget__error" role="status">
              {errorMessage}
            </div>
          ) : null}

          <form className="chatbot-widget__composer" onSubmit={handleSubmit}>
            <label className="chatbot-widget__sr-only" htmlFor="chatbot-widget-input">
              Ask the Fawry assistant
            </label>
            <textarea
              id="chatbot-widget-input"
              ref={inputRef}
              className="chatbot-widget__input"
              placeholder={
                isArabic
                  ? 'اكتب سؤالك من مواد التدريب...'
                  : 'Ask a question from the training materials...'
              }
              rows={1}
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              onKeyDown={handleInputKeyDown}
              disabled={isLoading}
            />
            <button
              type="submit"
              className="chatbot-widget__send"
              aria-label="Send message"
              disabled={isLoading || !inputValue.trim()}
            >
              {isLoading ? <CircularProgress size={18} color="inherit" /> : <SendRoundedIcon fontSize="small" />}
            </button>
          </form>
        </section>
      ) : null}

      <Tooltip title="Fawry Assistant" placement="left">
        <button
          type="button"
          className="chatbot-widget__toggle"
          aria-label="Open chatbot"
          data-testid="chatbot-toggle"
          onClick={() => setIsOpen((currentValue) => !currentValue)}
        >
          <ChatBubbleOutlineRoundedIcon />
        </button>
      </Tooltip>
    </div>
  );
}

export default ChatbotWidget;
