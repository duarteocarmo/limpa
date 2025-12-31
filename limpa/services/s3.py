import os

import boto3


def get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("AWS_S3_REGION", "us-east-1"),
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
