import boto3
import os
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Manages EBS snapshot lifecycles.
    - Snapshots > 30 days: Move to EBS Snapshots Archive (saves ~75%).
    - Snapshots > 90 days: Delete permanently (unless tagged 'FinOps:Retain').
    """
    archive_days = int(os.environ.get('ARCHIVE_DAYS', 30))
    delete_days = int(os.environ.get('DELETE_DAYS', 90))
    dry_run = os.environ.get('DRY_RUN', 'True').lower() == 'true'
    
    ec2 = boto3.client('ec2', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
    
    now = datetime.now(timezone.utc)
    archive_threshold = now - timedelta(days=archive_days)
    delete_threshold = now - timedelta(days=delete_days)
    
    archived_count = 0
    deleted_count = 0
    
    logger.info(f"Starting Snapshot Manager (Dry Run: {dry_run})")
    
    # Get all snapshots owned by this account
    paginator = ec2.get_paginator('describe_snapshots')
    for page in paginator.paginate(OwnerIds=['self']):
        for snap in page['Snapshots']:
            snap_id = snap['SnapshotId']
            start_time = snap['StartTime']
            state = snap['State']
            storage_tier = snap.get('StorageTier', 'standard')
            tags = {t['Key']: t['Value'] for t in snap.get('Tags', [])}
            
            # Skip if explicitly retained
            if tags.get('FinOps:Retain', '').lower() == 'true':
                continue
            
            # 1. Delete if older than 90 days
            if start_time < delete_threshold:
                logger.warning(f"DELETING Snapshot: {snap_id} (Created: {start_time})")
                if not dry_run:
                    try:
                        ec2.delete_snapshot(SnapshotId=snap_id)
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"Failed to delete {snap_id}: {e}")
                else:
                    deleted_count += 1
                    
            # 2. Archive if older than 30 days (and not already archived)
            elif start_time < archive_threshold and storage_tier == 'standard':
                logger.info(f"ARCHIVING Snapshot: {snap_id} (Created: {start_time})")
                if not dry_run:
                    try:
                        ec2.modify_snapshot_tier(SnapshotId=snap_id, StorageTier='archive')
                        archived_count += 1
                    except Exception as e:
                        logger.error(f"Failed to archive {snap_id}: {e}")
                else:
                    archived_count += 1
                    
    summary = f"Snapshot Manager Complete. Archived: {archived_count}, Deleted: {deleted_count}"
    logger.info(summary)
    
    return {'statusCode': 200, 'body': summary}
