# services/s3_service.py
import boto3
from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, BUCKET_NAME, OUTPUT_BUCKET_NAME

s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

def upload_file_to_s3(local_path, s3_file_key):
    """Uploads binary files (videos) to AWS S3."""
    try:
        s3_client.upload_file(local_path, BUCKET_NAME, s3_file_key)
        return f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_file_key}"
    except Exception as e:
        print(f"❌ S3 Video Upload Failed: {e}")
        return None

def upload_text_to_s3(text_content, s3_file_key):
    """Uploads raw transcript strings to AWS S3 output bucket."""
    try:
        print(f"📤 Uploading transcript to S3...")
        print(f"   Bucket: {OUTPUT_BUCKET_NAME}")
        print(f"   Key: {s3_file_key}")
        print(f"   Content length: {len(text_content)} characters")
        
        s3_client.put_object(
            Bucket=OUTPUT_BUCKET_NAME, 
            Key=s3_file_key,
            Body=text_content.encode('utf-8'), 
            ContentType='text/plain'
        )
        
        url = f"https://{OUTPUT_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_file_key}"
        print(f"✅ Transcript uploaded successfully: {url}")
        return url
    except Exception as e:
        print(f"❌ S3 Transcript Upload Failed: {e}")
        import traceback
        traceback.print_exc()
        return None