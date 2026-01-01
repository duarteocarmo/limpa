# Feature 2: Episode Processing Architecture

Process last 2 episodes (by publish date) of each podcast, store processed audio in S3, serve modified feed with S3 URLs.

## Model Changes

```python
# Add to Podcast model
processed_episodes = models.JSONField(default=dict)  # {guid: {original_url, s3_url}}
last_refreshed_at = models.DateTimeField(null=True, blank=True)
```

## S3 Structure

```
{bucket}/{url_hash}/
  feed.xml                          # Modified RSS (processed episodes → S3 URLs)
  episodes/{episode_guid_hash}.mp3  # Processed audio files
```

## Processing Flow

1. **process_podcast task** - Parse feed, get 2 most recent episodes by publish date, skip already processed, enqueue `process_episode` for each
2. **process_episode task** - Download to temp → trim last 30s with ffmpeg → upload to S3 → update `processed_episodes` → call `regenerate_feed`
3. **regenerate_feed** (function, not task) - Fetch original feed, replace enclosure URLs for processed episodes, upload to S3
4. **refresh_feeds management command** - Calls `process_podcast` for all podcasts (run manually or via cron)

## Feed Behavior

- Keep entire original feed structure
- Only replace `<enclosure url>` for episodes in `processed_episodes`
- Unprocessed episodes keep original URLs

## New Endpoint

```
GET /feed/{url_hash}/  # Serves feed.xml from S3, returns 404 if podcast doesn't exist
```

## Infrastructure

- Dockerfile: install ffmpeg via apt

## Implementation Order

| # | Task | Files |
|---|------|-------|
| 1 | Dockerfile: install ffmpeg | `Dockerfile` |
| 2 | Migration: add `processed_episodes`, `last_refreshed_at` | `limpa/migrations/0003_*.py` |
| 3 | S3 service: add `upload_episode_audio()`, `get_feed_xml()` | `limpa/services/s3.py` |
| 4 | Audio processing: `trim_audio_end()` using ffmpeg subprocess | `limpa/services/audio.py` (new) |
| 5 | Feed manipulation: `regenerate_feed()` | `limpa/services/feed.py` |
| 6 | Task: `process_episode` | `limpa/tasks.py` |
| 7 | Update `process_podcast` to parse & dispatch episodes | `limpa/tasks.py` |
| 8 | View: `/feed/{url_hash}/` proxy endpoint | `limpa/views.py`, `config/urls.py` |
| 9 | Management command: `refresh_feeds` | `limpa/management/commands/refresh_feeds.py` |
| 10 | Update UI: show episodes processed count | `limpa/templates/limpa/home.html` |
