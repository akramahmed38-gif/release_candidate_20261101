"""Chroma scalar metadata with lossless JSON for structured question aliases."""
import json


def encode_metadata(metadata):
    return {key: value if isinstance(value, (str, int, float, bool)) else json.dumps(value, ensure_ascii=False)
            for key, value in metadata.items() if value is not None}
