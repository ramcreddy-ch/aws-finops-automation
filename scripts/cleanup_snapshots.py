import boto3
from datetime import datetime, timedelta, timezone

def cleanup_old_snapshots(days=30):
    ec2 = boto3.client('ec2')
    delete_before = datetime.now(timezone.utc) - timedelta(days=days)
    
    snapshots = ec2.describe_snapshots(OwnerIds=['self'])['Snapshots']
    for snap in snapshots:
        if snap['StartTime'] < delete_before:
            print(f"Deleting snapshot {snap['SnapshotId']} (Created on {snap['StartTime']})")
            # ec2.delete_snapshot(SnapshotId=snap['SnapshotId'])

if __name__ == "__main__":
    cleanup_old_snapshots(90)
