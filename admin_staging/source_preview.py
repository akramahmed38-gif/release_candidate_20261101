"""Bounded, hash-verified original-page/section review. No source mutations."""
from pathlib import Path,PurePosixPath
import base64,hashlib,html,json,re
ROOT=Path(__file__).resolve().parent
if ROOT.name=='next_revision':ROOT=ROOT.parent
RELEASE=ROOT.parent

class SourcePreviewError(ValueError):
    def __init__(self,message,status=409):super().__init__(message);self.status=status

def verified_source(fact,roots=None):
    relative=PurePosixPath(str(fact.get('source_document','')).replace('\\','/'))
    if not relative.parts or relative.is_absolute() or '..' in relative.parts or ':' in str(relative):raise SourcePreviewError('Invalid registered source path',400)
    expected=fact.get('source_sha256','')
    if not re.fullmatch('[a-f0-9]{64}',expected):raise SourcePreviewError('Exact registered source fingerprint required')
    roots=roots or [RELEASE/'source/candidate/fixture_data/source_files',Path(r'\\10.100.175.10\Projects\Production\FP Branches + Forms\HR Training App')]
    for root in roots:
        root=Path(root).resolve();path=root.joinpath(*relative.parts).resolve()
        if not path.is_relative_to(root):raise SourcePreviewError('Registered source escaped its read-only root',400)
        if not path.is_file():continue
        before=path.stat()
        if before.st_size>32*1024*1024:raise SourcePreviewError('Source exceeds bounded preview limit; separate review required',413)
        body=path.read_bytes();after=path.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise SourcePreviewError('Source changed during verification')
        if hashlib.sha256(body).hexdigest()!=expected:raise SourcePreviewError('Source revision changed; dependent review view is invalid')
        return body,path.suffix.casefold()
    raise SourcePreviewError('Registered source version is unavailable',404)

def render(fact,roots=None):
    if fact.get('quarantine_reason') or fact.get('review_status')=='restricted_hold':raise SourcePreviewError('Restricted evidence requires separate authorized review',403)
    body,suffix=verified_source(fact,roots)
    locator=fact.get('locator') or fact.get('source_locator') or {}
    content='';esc=lambda x:html.escape(str(x))
    if suffix=='.pdf':
        import fitz
        try:page_number=int(locator['page'])
        except (KeyError,ValueError,TypeError):raise SourcePreviewError('Bounded original page locator required')
        with fitz.open(stream=body,filetype='pdf') as doc:
            if not 1<=page_number<=len(doc):raise SourcePreviewError('Original page locator is out of range')
            page=doc[page_number-1]
            from catalog_store import SENSITIVE
            if SENSITIVE.search(page.get_text()):raise SourcePreviewError('Original page includes restricted text; bounded redaction review required',403)
            image=page.get_pixmap(matrix=fitz.Matrix(1.2,1.2),alpha=False).tobytes('png')
        content='<p>Original page '+str(page_number)+' rendered from the verified parent source. This image is a derived page view, not a new authoritative source.</p><img alt="Verified original cited page" style="max-width:100%;height:auto" src="data:image/png;base64,'+base64.b64encode(image).decode()+'">'
    elif suffix in {'.md','.txt'}:
        lines=body.decode('utf-8-sig').splitlines()
        try:start,end=int(locator['line_start']),int(locator['line_end'])
        except (KeyError,ValueError,TypeError):raise SourcePreviewError('Bounded original line locator required')
        if not 1<=start<=end<=len(lines) or end-start>150:raise SourcePreviewError('Original line locator is invalid or unbounded')
        excerpt='\n'.join(lines[start-1:end])
        from catalog_store import SENSITIVE
        if SENSITIVE.search(excerpt):raise SourcePreviewError('Original section includes restricted text; separate review required',403)
        content='<h2>Original lines '+str(start)+'–'+str(end)+'</h2><pre dir="auto" style="white-space:pre-wrap">'+esc(excerpt)+'</pre>'
    else:raise SourcePreviewError('This source type requires a separate bounded preview adapter',415)
    return '<!doctype html><html><head><meta charset="utf-8"><title>Source-bound admin review</title></head><body><main style="max-width:1100px;margin:20px auto;font:16px Arial"><h1>Unapproved source review</h1><p>No fidelity or business-currentness approval is granted by this view. A pinned historical source version is not a current-policy certification.</p><p>'+esc(fact.get('fact_id'))+' — '+esc(fact['source_document'])+'</p><p>Parent source SHA-256: <code>'+esc(fact['source_sha256'])+'</code></p><p>Original locator: <code>'+esc(json.dumps(locator,ensure_ascii=False))+'</code></p>'+content+'</main></body></html>'
