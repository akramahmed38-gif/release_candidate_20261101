"""Decode Office image assets without interpreting embedded movies as images."""
from pathlib import Path
import io
import subprocess
import tempfile
from PIL import Image


def decode_office_asset(data, suffix):
    suffix = suffix.lower()
    if suffix in {'.mp4', '.mov', '.m4v', '.avi', '.wmv', '.mp3', '.wav'}:
        return None, 'embedded_media_deferred'
    if suffix == '.svg':
        import fitz
        with fitz.open(stream=data, filetype='svg') as document:
            return document[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes('png'), None
    if suffix in {'.wdp', '.jxr', '.hdp'}:
        with tempfile.TemporaryDirectory(prefix='hr-image-') as folder:
            source, target = Path(folder)/'source.wdp', Path(folder)/'decoded.png'
            source.write_bytes(data)
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-File',
                str(Path(__file__).with_name('decode_jpegxr.ps1')), str(source), str(target)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode or not target.exists():
                raise ValueError('JPEG-XR decoding unavailable')
            return target.read_bytes(), None
    with Image.open(io.BytesIO(data)) as image:
        image.load()
    return data, None
