"""Coordinate-preserving PDF evidence candidates. Never infer missing facts.

PDF words are already decoded by the renderer. Sorting a complete Arabic page
as left-to-right text reverses word order. Reorder within each visual line,
retaining contiguous Latin/numeric runs and geometry for human verification.
This is an alternative candidate, not automatic semantic approval.
"""
import re
import unicodedata

VERSION = 'pdf-coordinate-lines-v1'
_ARABIC = re.compile(r'[\u0621-\u064a]')


def coordinate_lines(words):
    rows = []
    for item in words:
        x0, y0, x1, y1, text = item[:5]
        text = unicodedata.normalize('NFKC', str(text))
        if not text.strip():
            continue
        block = {'text': text, 'box': [float(x0), float(y0), float(x1), float(y1)]}
        center, height = (y0+y1)/2, max(1, y1-y0)
        # Baseline grouping must not join adjacent visual rows or columns.
        match = next((row for row in reversed(rows)
                      if abs(row['center']-center) <= min(row['height'],height)*.35), None)
        if match is None:
            match = {'center': center, 'height': height, 'words': []}
            rows.append(match)
        match['words'].append(block)
    result = []
    for row in sorted(rows, key=lambda row: row['center']):
        ordered = sorted(row['words'], key=lambda block: block['box'][0])
        rtl = sum(len(_ARABIC.findall(w['text'])) for w in ordered) > sum(
            len(re.findall(r'[A-Za-z]',w['text'])) for w in ordered)
        # Separate wide gaps: do not flatten independent table cells or columns.
        cells, current = [], []
        for word in ordered:
            if current and word['box'][0]-current[-1]['box'][2] > max(20,row['height']*2.5):
                cells.append(current); current = []
            current.append(word)
        if current: cells.append(current)
        if rtl: cells.reverse()
        texts = []
        for cell in cells:
            if rtl:
                # LTR islands keep their internal order (AXIS PAY, 100 000).
                runs, run = [], []
                for word in cell:
                    kind = bool(_ARABIC.search(word['text']))
                    if run and kind != bool(_ARABIC.search(run[-1]['text'])):
                        runs.append(run); run = []
                    run.append(word)
                if run: runs.append(run)
                cell = [w for run in reversed(runs) for w in
                        (reversed(run) if _ARABIC.search(run[0]['text']) else run)]
            texts.append(' '.join(w['text'] for w in cell))
        result.append({'text': ' | '.join(texts), 'direction': 'rtl' if rtl else 'ltr',
                       'cells': cells, 'words': ordered,
                       'box': [min(w['box'][0] for w in ordered), min(w['box'][1] for w in ordered),
                               max(w['box'][2] for w in ordered), max(w['box'][3] for w in ordered)]})
    return {'version': VERSION, 'lines': result, 'text': '\n'.join(r['text'] for r in result),
            'quality': 'unverified_candidate', 'semantic_verified': False,
            'table_relationships_inferred': False}


def extract_coordinate_page(page):
    return coordinate_lines(page.get_text('words', sort=False))
