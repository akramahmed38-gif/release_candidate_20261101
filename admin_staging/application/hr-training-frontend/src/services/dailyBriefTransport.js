// UTF-8 transport for editor HTML, matching the portal's encoded form approach.
// This is not encryption; server-side validation and sanitization remain required.
export function encodeBriefPayload(form) {
  const payload = {
    title: form.title,
    brief_date: form.brief_date,
    blocks: (form.blocks || []).map(({ block_type, content }) => ({ block_type, content })),
  };
  return encodeDailyBriefEnvelope(payload);
}

export function encodeDailyBriefEnvelope(payload) {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  if (4 * Math.ceil(bytes.length / 3) > 2 * 1024 * 1024) {
    throw new Error('This Daily Brief is too large to save. Reduce its content and try again. Your edits remain in the builder.');
  }
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return { payload_b64: btoa(binary) };
}

export function requireBriefSaveResponse(response, expectedId) {
  const item = response?.data?.item || response?.data;
  if (!item || typeof item !== 'object' || typeof item.id !== 'string' || !item.id
      || (expectedId && item.id !== expectedId)) {
    throw new Error('The server did not confirm the save. Your edits remain in the builder. Check the Daily Brief list before retrying.');
  }
  return response;
}

export function requireBriefActionResponse(response, message) {
  if (response?.data?.message !== message) {
    throw new Error('The server did not confirm the status change. Check the Daily Brief list before retrying.');
  }
  return response;
}
