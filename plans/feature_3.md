# Feature 3: Processing Status & Advertisement Data Storage

Improve UX clarity by adding a `PROCESSING` state and storing extracted advertisement data per episode.

## Status Changes

Current: `PENDING` → `UPLOADED` → `FAILED`

New: `PENDING` → `PROCESSING` → `READY` (or `FAILED`)

## Model Changes

```python
# limpa/models.py
class Status(models.TextChoices):
    PENDING = "pending"
    PROCESSING = "processing"  # NEW
    READY = "ready"            # Renamed from UPLOADED
    FAILED = "failed"
```

## JSONField Structure Change

Current:
```python
{guid: {"original_url": str, "s3_url": str}}
```

New:
```python
{guid: {"original_url": str, "s3_url": str, "ads": {...}}}  # ads = AdvertisementData.model_dump()
```

## Task Flow

1. `add_podcast` (view): Creates podcast with `PENDING`, uploads feed, enqueues `process_podcast`
2. `process_podcast` (task): Sets `PROCESSING`, enqueues episodes
3. `process_episode` (task): Processes episode, stores ads data, sets `READY` on success / `FAILED` on error

## Implementation Order

| # | Task | Files |
|---|------|-------|
| 1 | Update Status choices: remove `UPLOADED`, add `PROCESSING`, `READY` | `limpa/models.py` |
| 2 | Create migration for status field changes | `limpa/migrations/0004_*.py` |
| 3 | Update `add_podcast` view: keep `PENDING` after upload (remove setting `UPLOADED`) | `limpa/views.py` |
| 4 | Update `process_podcast`: set `PROCESSING` at start | `limpa/tasks.py` |
| 5 | Update `process_episode`: store `ads` in JSONField, set `READY` on success, `FAILED` on error | `limpa/tasks.py` |
| 6 | Update CSS: replace `.status-uploaded` with `.status-ready`, add `.status-processing` | `limpa/static/limpa/style.css` |
| 7 | Run `make format` and `make check` | - |
