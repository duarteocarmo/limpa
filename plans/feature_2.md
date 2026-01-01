# Feature 2: Episode Processing Architecture

Process last 2 episodes of each podcast, store processed audio in S3, serve modified feed with S3 URLs.

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

1. **process_podcast** - Parse feed, get last 2 episodes, skip already processed, enqueue `process_episode` for each
2. **process_episode** - Download to temp → remove last 30s → upload to S3 → update `processed_episodes` → enqueue `regenerate_feed`
3. **regenerate_feed** - Fetch original feed, replace enclosure URLs for processed episodes, upload to S3
4. **refresh_all_feeds** (daily cron, configurable) - Enqueue `process_podcast` for all podcasts

## Feed Behavior

- Keep entire original feed structure
- Only replace `<enclosure url>` for episodes in `processed_episodes`
- Unprocessed episodes keep original URLs

## New Endpoint

```
GET /feed/{url_hash}/  # Proxy that serves feed.xml from S3
```

## Implementation Order

1. Migration: add `processed_episodes`, `last_refreshed_at` to Podcast
2. S3 service: add `upload_episode_audio()`, `download_to_temp()`
3. Audio processing: function to trim last 30s (ffmpeg or pydub)
4. Task: `process_episode`
5. Task: `regenerate_feed` (XML manipulation)
6. Update `process_podcast` to parse & dispatch episodes
7. View: `/feed/{url_hash}/` proxy endpoint
8. Periodic task: `refresh_all_feeds`
