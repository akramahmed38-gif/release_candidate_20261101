import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Layout from '../Layout/Layout';
import { LanguageProvider } from '../../context/LanguageContext';
import api from '../../services/api';
import { authService } from '../../services/auth';
import {
  CHATBOT_WELCOME_CONFIG,
  buildChatbotWelcomeMessage,
} from './chatbotWelcomeConfig';

jest.mock('../../services/api', () => ({
  __esModule: true,
  default: {
    post: jest.fn(),
  },
}));

jest.mock('../../services/auth', () => ({
  __esModule: true,
  authService: {
    getCurrentUser: jest.fn(() => null),
  },
}));

jest.mock('../Layout/Navbar', () => ({
  __esModule: true,
  default: () => <div>Navbar</div>,
}));

jest.mock('../Layout/Footer', () => ({
  __esModule: true,
  default: () => <div>Footer</div>,
}));

function renderChatbot(route = '/dashboard') {
  return render(
    <LanguageProvider>
      <MemoryRouter initialEntries={[route]}>
        <Layout>
          <div>Dashboard</div>
        </Layout>
      </MemoryRouter>
    </LanguageProvider>
  );
}

function findWelcomeMessageNode(expectedMessage) {
  return screen.findByText((_, element) => element?.textContent === expectedMessage, {}, {
    timeout: 2600,
  });
}

describe('ChatbotWidget', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  test('shows the delayed Arabic personalized welcome message on first open', async () => {
    window.localStorage.setItem('app_lang', 'ar');
    authService.getCurrentUser.mockReturnValue({
      name: 'Eslam Salem',
      email: 'eslam.salem@fawry-retail.com',
    });

    renderChatbot();

    await userEvent.click(screen.getByLabelText(/open chatbot/i));

    expect(
      await findWelcomeMessageNode(buildChatbotWelcomeMessage('Eslam Salem'))
    ).toBeInTheDocument();
    expect(screen.getByText(CHATBOT_WELCOME_CONFIG.ar.assistantLabel)).toBeInTheDocument();
  });

  test('does not duplicate the welcome message when the chat is closed and reopened', async () => {
    window.localStorage.setItem('app_lang', 'ar');
    authService.getCurrentUser.mockReturnValue({
      name: 'Eslam Salem',
      email: 'eslam.salem@fawry-retail.com',
    });

    renderChatbot();

    await userEvent.click(screen.getByLabelText(/open chatbot/i));
    await findWelcomeMessageNode(buildChatbotWelcomeMessage('Eslam Salem'));

    await userEvent.click(screen.getByLabelText(/close chatbot/i));
    await userEvent.click(screen.getByLabelText(/open chatbot/i));

    expect(
      screen.getAllByText((_, element) => {
        return element?.textContent === buildChatbotWelcomeMessage('Eslam Salem');
      })
    ).toHaveLength(1);
  });

  test('falls back to a friendly name derived from email when profile name is missing', async () => {
    window.localStorage.setItem('app_lang', 'ar');
    authService.getCurrentUser.mockReturnValue({
      email: 'ali.redwan@fawry-retail.com',
    });

    renderChatbot();

    await userEvent.click(screen.getByLabelText(/open chatbot/i));

    expect(
      await findWelcomeMessageNode(buildChatbotWelcomeMessage('Ali Redwan'))
    ).toBeInTheDocument();
  });

  test('appears in layout and shows a chatbot answer after sending a question', async () => {
    api.post.mockResolvedValue({
      data: {
        answer: 'Contact the branch supervisor using the available branch guide.',
        sources: [
          {
            source_name: 'branch-guide.pdf',
            location_label: 'Page 3',
            final_score: 0.91,
          },
        ],
      },
    });

    renderChatbot();

    const openButton = screen.getByLabelText(/open chatbot/i);
    expect(openButton).toBeInTheDocument();

    await userEvent.click(openButton);

    expect(screen.getByText('Fero')).toBeInTheDocument();

    await userEvent.type(
      screen.getByLabelText(/ask fero/i),
      'Who should I contact when the counting machine stops?'
    );
    await userEvent.click(screen.getByLabelText(/send message/i));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/api/v1/chatbot/ask',
        expect.objectContaining({
          question: 'Who should I contact when the counting machine stops?',
          conversation_id: expect.any(String),
          session_id: expect.any(String),
          message_id: expect.any(String),
        })
      );
    });

    expect(
      await screen.findByText('Contact the branch supervisor using the available branch guide.')
    ).toBeInTheDocument();
    expect(screen.getByText(/branch-guide\.pdf/i)).toBeInTheDocument();
  });

  test('restores input focus after send-button submission', async () => {
    api.post.mockResolvedValue({
      data: {
        answer: 'You can contact the branch supervisor.',
        sources: [],
      },
    });

    renderChatbot();

    await userEvent.click(screen.getByLabelText(/open chatbot/i));

    const input = screen.getByLabelText(/ask fero/i);
    await userEvent.type(input, 'Who should I contact?');
    expect(input).toHaveFocus();

    await userEvent.click(screen.getByLabelText(/send message/i));

    expect(input).toHaveValue('');
    expect(await screen.findByText('You can contact the branch supervisor.')).toBeInTheDocument();

    await waitFor(() => {
      expect(input).toHaveFocus();
    });
  });

  test('restores input focus after enter submission', async () => {
    api.post.mockResolvedValue({
      data: {
        answer: 'Follow the branch maintenance procedure.',
        sources: [],
      },
    });

    renderChatbot();

    await userEvent.click(screen.getByLabelText(/open chatbot/i));

    const input = screen.getByLabelText(/ask fero/i);
    await userEvent.type(input, 'What should I do?{enter}');

    expect(input).toHaveValue('');
    expect(await screen.findByText('Follow the branch maintenance procedure.')).toBeInTheDocument();

    await waitFor(() => {
      expect(input).toHaveFocus();
    });
  });

  test('renders clarification response without sources', async () => {
    api.post.mockResolvedValue({
      data: {
        type: 'clarification',
        answer: 'Please clarify exactly which customer data you want to update.',
        clarification: {
          question: 'Please clarify exactly which customer data you want to update.',
          original_question: 'I want to update customer data',
          attempts: 1,
        },
        sources: [],
        fallback_used: false,
        fallback_stage: 'clarification',
        fallback_reason: 'fallback_answer_replaced_by_clarification',
      },
    });

    renderChatbot();

    await userEvent.click(screen.getByLabelText(/open chatbot/i));
    await userEvent.type(screen.getByLabelText(/ask fero/i), 'I want to update customer data');
    await userEvent.click(screen.getByLabelText(/send message/i));

    expect(
      await screen.findByText('Please clarify exactly which customer data you want to update.')
    ).toBeInTheDocument();
    expect(screen.queryByText(/branch-guide\.pdf/i)).not.toBeInTheDocument();
  });

  test('hides the chatbot while a retail exam session is in progress', () => {
    authService.getCurrentUser.mockReturnValue({
      role: 'retail',
      hrid: '26688',
      email: 'eslam.salem@fawry-retail.com',
    });
    window.localStorage.setItem(
      'exam_session_demo_26688',
      JSON.stringify({
        status: 'in-progress',
        attemptId: 'attempt-1',
        expiresAt: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
      })
    );

    renderChatbot('/employee/exams/demo');

    expect(screen.queryByLabelText(/open chatbot/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId('chatbot-panel')).not.toBeInTheDocument();
  });
});
