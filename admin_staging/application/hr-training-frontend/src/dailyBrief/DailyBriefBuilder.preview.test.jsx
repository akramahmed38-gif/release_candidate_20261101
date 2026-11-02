import { afterEach, describe, expect, it } from 'vitest';
import { restorePreviewSession } from './DailyBriefBuilder';

afterEach(() => window.sessionStorage.clear());

describe('DailyBriefBuilder preview recovery', () => {
  it('restores an existing draft snapshot exactly once after preview', () => {
    const recoveryKey = 'daily-brief:preview-recovery:draft-123:test';
    const snapshot = {
      briefStatus: 'DRAFT',
      form: {
        title: 'تحديث Retail / Retail update',
        brief_date: '2026-09-21',
        blocks: [
          { id: 'text-1', block_type: 'text', content: { html: '<p><strong>Important</strong> تحديث</p>' } },
          { id: 'image-1', block_type: 'image', content: { image_url: '/api/v1/daily-briefs/images/qa.png', alt: 'QA' } },
          { id: 'alert-1', block_type: 'alert', content: { heading: 'Alert', text: 'Message', style: 'warning' } },
        ],
      },
    };
    window.sessionStorage.setItem(recoveryKey, JSON.stringify(snapshot));

    expect(restorePreviewSession(recoveryKey)).toEqual(snapshot);
    expect(restorePreviewSession(recoveryKey)).toBeNull();
  });
});
