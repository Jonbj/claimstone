"""Active immutable chunks, published by a document's complete generation manifest."""
from __future__ import annotations

from typing import Any
from .store import Store, sha256_text


def current(store: Store) -> dict[str, dict[str, Any]]:
    held = store.latest_by('chunks.jsonl', 'chunk_id')
    documents = store.latest_by('documents.jsonl', 'source_id')
    active = {key: row for key, row in held.items()
              if row.get('source_id') not in documents and not row.get('generation_sha256')}
    for source, document in documents.items():
        if not document.get('fulltext_confirmed'):
            continue
        if 'chunk_ids' in document:
            wanted = set(document['chunk_ids'])
            for key in wanted:
                row = held.get(key)
                if row is None or row.get('source_id') != source:
                    raise ValueError(f'incomplete chunk manifest for {source}: {key}')
                if row.get('generation_sha256') != document.get('generation_sha256'):
                    raise ValueError(f'chunk generation mismatch for {source}: {key}')
                if row.get("text_sha256") and row["text_sha256"] != text_hash(row):
                    raise ValueError(f"chunk text hash mismatch for {source}: {key}")
                active[key] = row
        else:
            # Old stores did not record a manifest. Preserve their known positional ids;
            # new-generation rows written before a crash are never legacy chunks.
            legacy = {key: row for key, row in held.items()
                      if row.get('source_id') == source and not row.get('generation_sha256')}
            if document.get('chunks') is not None and len(legacy) != document['chunks']:
                raise ValueError(f'ambiguous legacy chunk set for {source}; run normalize --force')
            active.update(legacy)
    return active


def text_hash(row: dict[str, Any]) -> str:
    return sha256_text(str(row.get('text') or ''))
