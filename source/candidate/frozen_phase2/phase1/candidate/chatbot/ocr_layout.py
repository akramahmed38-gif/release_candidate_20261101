"""Retain OCR geometry and uncertainty; geometry never invents table semantics."""
import re
from statistics import median


def summarize_layout(items):
    blocks = []
    for box, text, confidence in items:
        if not str(text).strip():
            continue
        points = [[float(x), float(y)] for x, y in box]
        blocks.append({'text': str(text).strip(), 'confidence': float(confidence), 'box': points,
                       'left': min(p[0] for p in points), 'right': max(p[0] for p in points),
                       'top': min(p[1] for p in points), 'bottom': max(p[1] for p in points)})
    rows = []
    for block in sorted(blocks, key=lambda b: (b['top'], b['left'])):
        center = (block['top'] + block['bottom']) / 2
        height = max(1, block['bottom'] - block['top'])
        matching = next((r for r in reversed(rows) if abs(r['center'] - center) <= min(r['height'], height) * .45), None)
        if matching is None:
            matching = {'center': center, 'height': height, 'cells': []}
            rows.append(matching)
        matching['cells'].append(block)
    lines = []
    table_candidates = 0
    for row in rows:
        arabic = sum(len(re.findall(r'[\u0621-\u064a]', b['text'])) for b in row['cells'])
        latin = sum(len(re.findall(r'[A-Za-z]', b['text'])) for b in row['cells'])
        cells = sorted(row['cells'], key=lambda b: b['left'], reverse=arabic > latin)
        row['cells'] = cells
        # Delimiters preserve separation; they do not label a cell's business meaning.
        lines.append(' | '.join(b['text'] for b in cells))
        if len(cells) > 1 and any(re.search(r'\d|[٠-٩]', c['text']) for c in cells):
            table_candidates += 1
    low = [b for b in blocks if b['confidence'] < .60]
    reasons = []
    if not blocks:
        reasons.append('no_recognized_text')
    if low:
        reasons.append('low_confidence_blocks')
    if table_candidates:
        reasons.append('numeric_table_requires_relationship_review')
    return {'text': '\n'.join(lines), 'blocks': blocks, 'rows': rows,
            'median_confidence': median(b['confidence'] for b in blocks) if blocks else 0,
            'quality': 'review_required' if reasons else 'supported', 'review_reasons': reasons,
            'quality_is_semantic_certificate': False}
