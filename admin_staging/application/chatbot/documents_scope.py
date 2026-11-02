"""Explicitly validated document scope; pending media cannot hide document failures."""
import hashlib
import json
from pathlib import Path
from .content_catalog import MEDIA_TYPES


def documents_manifest(manifest):
    files = [row for row in manifest['files'] if Path(row['path']).suffix.lower() not in MEDIA_TYPES]
    if not files or any(row.get('status') != 'ready' for row in files) or manifest.get('missing_libraries'):
        raise ValueError('Document extraction is incomplete')
    pending = [row['path'] for row in manifest['files'] if Path(row['path']).suffix.lower() in MEDIA_TYPES]
    signature = hashlib.sha256(json.dumps({'scope':'documents-v1', 'files':files,
        'vocabulary_hash':manifest['vocabulary_hash']}, sort_keys=True).encode()).hexdigest()
    return {**manifest, 'files':files, 'source_files':len(files), 'ready_files':len(files),
            'complete':True, 'scope':'documents_only', 'excluded_media_files':pending,
            'signature':signature}
