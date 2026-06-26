import boto3
import os
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_boto3_client(service, region):
    return boto3.client(service, region_name=region)

def get_regions():
    ec2 = boto3.client('ec2', region_name='us-east-1')
    return [region['RegionName'] for region in ec2.describe_regions()['Regions']]

def lambda_handler(event, context):
    """
    Finds unattached EBS volumes. If an unattached volume doesn't have the 'FinOps:MarkedForDeletion' tag,
    it tags it with the current date. If it does have the tag and is older than the retention period (e.g., 7 days),
    it deletes the volume to save costs.
    """
    retention_days = int(os.environ.get('RETENTION_DAYS', 7))
    dry_run = os.environ.get('DRY_RUN', 'True').lower() == 'true'
    
    deleted_volumes = 0
    tagged_volumes = 0
    total_savings_estimated = 0
    
    logger.info(f"Starting EBS Reaper (Dry Run: {dry_run}, Retention: {retention_days} days)")
    
    for region in get_regions():
        logger.info(f"Scanning region: {region}")
        ec2 = get_boto3_client('ec2', region)
        
        # Find available (unattached) volumes
        volumes = ec2.describe_volumes(Filters=[{'Name': 'status', 'Values': ['available']}])['Volumes']
        
        for volume in volumes:
            vol_id = volume['VolumeId']
            size_gb = volume['Size']
            tags = {tag['Key']: tag['Value'] for tag in volume.get('Tags', [])}
            
            # Rough estimate for gp3
            estimated_cost = size_gb * 0.08
            
            if 'FinOps:MarkedForDeletion' not in tags:
                # First time seeing this orphaned volume, mark it
                logger.info(f"Tagging new orphaned volume: {vol_id} ({size_gb}GB, ~$ {estimated_cost}/mo)")
                if not dry_run:
                    ec2.create_tags(
                        Resources=[vol_id],
                        Tags=[{'Key': 'FinOps:MarkedForDeletion', 'Value': datetime.now(timezone.utc).isoformat()}]
                    )
                tagged_volumes += 1
            else:
                # Check how long it has been marked
                marked_date_str = tags['FinOps:MarkedForDeletion']
                try:
                    marked_date = datetime.fromisoformat(marked_date_str)
                    age_days = (datetime.now(timezone.utc) - marked_date).days
                    
                    if age_days >= retention_days:
                        logger.warning(f"DELETING volume {vol_id} (Marked {age_days} days ago). Savings: ${estimated_cost}/mo")
                        if not dry_run:
                            # Optional: Create a final snapshot before deletion (defensive FinOps)
                            ec2.create_snapshot(
                                VolumeId=vol_id,
                                Description=f"Automated final backup by FinOps before deleting {vol_id}",
                                TagSpecifications=[{'ResourceType': 'snapshot', 'Tags': [{'Key': 'FinOps:AutoBackup', 'Value': 'True'}]}]
                            )
                            ec2.delete_volume(VolumeId=vol_id)
                        
                        deleted_volumes += 1
                        total_savings_estimated += estimated_cost
                    else:
                        logger.info(f"Volume {vol_id} marked {age_days} days ago. Waiting for {retention_days} days.")
                except ValueError:
                    logger.error(f"Invalid date format in tag for volume {vol_id}")

    summary = f"EBS Reaper Complete. Tagged: {tagged_volumes}, Deleted: {deleted_volumes}. Est Savings: ${total_savings_estimated:.2f}/mo"
    logger.info(summary)
    
    return {
        'statusCode': 200,
        'body': summary
    }
