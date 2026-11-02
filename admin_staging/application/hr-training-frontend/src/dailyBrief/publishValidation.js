export function publishValidationError(form) {
  const filled = value => Boolean(String(value || '').trim());
  if (!filled(form.title) || !form.brief_date) return 'Enter a title and brief date before publishing.';
  if (!form.blocks.length) return 'Add at least one content block before publishing.';
  for (const [index, block] of form.blocks.entries()) {
    const c = block.content || {};
    const required = {
      heading: [['Heading', c.heading]],
      text: [['Text', c.html || c.text]],
      highlight: [['Heading', c.heading || c.title], ['Message', c.text || c.message]],
      alert: [['Heading', c.heading || c.title], ['Message', c.text || c.message]],
      image: [['Image', c.image_url]],
      image_text: [['Image', c.image_url], ['Text', c.text]],
      cta: [['Button label', c.label], ['Link', c.link]],
      bullet_list: [['List item', (c.items || []).find(filled)]],
    }[block.block_type] || [];
    const missing = required.find(([, value]) => !filled(value));
    if (missing) return `Block ${index + 1} (${block.block_type}): ${missing[0]} is required before publishing.`;
  }
  return '';
}
