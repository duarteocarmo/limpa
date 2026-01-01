import hashlib
import os
from pathlib import Path

import boto3


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("AWS_ENDPOINT_URL"),
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("AWS_S3_REGION", "auto"),
    )


def upload_feed_xml(url_hash: str, xml_content: bytes) -> bool:
    bucket = os.environ["AWS_S3_BUCKET_NAME"]
    key = f"{url_hash}/feed.xml"

    client = get_s3_client()
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=xml_content,
        ContentType="application/xml",
    )
    return True


def get_feed_xml(url_hash: str) -> bytes | None:
    bucket = os.environ["AWS_S3_BUCKET_NAME"]
    key = f"{url_hash}/feed.xml"

    client = get_s3_client()
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()
    except client.exceptions.NoSuchKey:
        return None


def upload_episode_audio(url_hash: str, episode_guid: str, audio_path: Path) -> str:
    bucket = os.environ["AWS_S3_BUCKET_NAME"]
    guid_hash = hashlib.sha256(episode_guid.encode()).hexdigest()
    key = f"{url_hash}/episodes/{guid_hash}.mp3"

    client = get_s3_client()
    with open(audio_path, "rb") as f:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=f,
            ContentType="audio/mpeg",
        )

    endpoint_url = os.environ.get("AWS_ENDPOINT_URL", "https://s3.amazonaws.com")
    return f"{endpoint_url}/{bucket}/{key}"
