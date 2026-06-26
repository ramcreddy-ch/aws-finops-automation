# 11 — S3 Cost Optimization

> *S3 is $0.023/GB, which sounds cheap. But at petabyte scale, with millions of PUT/GET requests and cross-region replication, S3 bills easily exceed $100K/month. Optimization here requires understanding access patterns.*

---

## 🧠 S3 Intelligent-Tiering: The Silver Bullet

If you do not know the access pattern of your data, use **S3 Intelligent-Tiering (INT)**. It automatically moves objects between access tiers based on actual usage, saving up to 68% automatically.

**Cost Math:**
- Standard: $0.023 / GB
- INT Infrequent Access (after 30 days): $0.0125 / GB
- INT Archive Instant Access (after 90 days): $0.004 / GB
- INT Monitoring Fee: $0.0025 per 1,000 objects

**Rule of Thumb:**
Do NOT use INT for buckets with millions of tiny objects (< 128KB). The monitoring fee will exceed the storage savings.

---

## 🤖 Global S3 Lifecycle Enforcer

```python
# 25-Automation/lambda_functions/s3_lifecycle_enforcer.py
"""
Scans all S3 buckets in an account.
If a bucket has no lifecycle policy, it applies a default policy
moving objects to Intelligent-Tiering after 30 days.
"""
import boto3
import logging
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_LIFECYCLE_RULE = {
    'Rules': [
        {
            'ID': 'FinOps-Auto-IntelligentTiering',
            'Filter': {'Prefix': ''}, # Apply to whole bucket
            'Status': 'Enabled',
            'Transitions': [
                {
                    'Days': 30,
                    'StorageClass': 'INTELLIGENT_TIERING'
                }
            ],
            'AbortIncompleteMultipartUpload': {
                'DaysAfterInitiation': 7 # Stop paying for failed uploads!
            }
        }
    ]
}

def lambda_handler(event, context):
    s3 = boto3.client('s3')
    buckets = s3.list_buckets()['Buckets']
    
    compliant = 0
    enforced = 0
    
    for bucket in buckets:
        bucket_name = bucket['Name']
        
        try:
            # Check if lifecycle exists
            s3.get_bucket_lifecycle_configuration(Bucket=bucket_name)
            compliant += 1
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchLifecycleConfiguration':
                logger.warning(f"No lifecycle policy found on {bucket_name}. Applying default.")
                try:
                    s3.put_bucket_lifecycle_configuration(
                        Bucket=bucket_name,
                        LifecycleConfiguration=DEFAULT_LIFECYCLE_RULE
                    )
                    enforced += 1
                except Exception as ex:
                    logger.error(f"Failed to apply policy to {bucket_name}: {ex}")
            else:
                logger.error(f"Error checking {bucket_name}: {e}")

    logger.info(f"S3 Audit Complete. Checked: {len(buckets)} | Compliant: {compliant} | Enforced: {enforced}")
    return {"enforced_buckets": enforced}
```

---

## 🕵️ Incomplete Multipart Uploads: The Invisible Waste

When you upload large files to S3, AWS splits them into parts. If the upload fails or is canceled, the parts stay in S3 forever, hidden, charging you Standard storage rates. They do not appear in the AWS Console.

**Prevention via Terraform:**
```hcl
resource "aws_s3_bucket_lifecycle_configuration" "bucket_config" {
  bucket = aws_s3_bucket.my_bucket.id

  rule {
    id     = "abort-failed-uploads"
    status = "Enabled"

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
```

---

## 📊 S3 Storage Lens

Storage Lens is the best native tool for S3 FinOps. The free tier gives organization-wide visibility into:
- Total storage bytes
- Object counts
- Incomplete multipart upload bytes (the invisible waste)
- Non-current version bytes (versioning waste)

**Action:** Enable Storage Lens organizational dashboard immediately. Look for buckets with high "Non-current version bytes" — this means you have Versioning turned on but no Lifecycle rule to delete old versions.

---

## ✅ S3 Optimization Checklist

- [ ] Apply 7-day `AbortIncompleteMultipartUpload` lifecycle rule to EVERY bucket in the organization.
- [ ] Migrate unknown-access-pattern data to Intelligent Tiering (watch out for object size < 128KB).
- [ ] For buckets with Versioning enabled, add a rule to expire non-current versions after X days.
- [ ] Review S3 API request costs (millions of HEAD/GET requests can cost more than the storage).
- [ ] Eliminate S3 egress costs via NAT Gateway by deploying S3 Gateway VPC Endpoints (FREE).
