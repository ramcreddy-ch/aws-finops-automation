import boto3
from datetime import datetime, timedelta

def find_unused_ebs_volumes():
    ec2 = boto3.resource('ec2')
    unused = []
    for vol in ec2.volumes.all():
        if vol.state == 'available':
            unused.append(vol.id)
            print(f"Unused Volume: {vol.id}, Size: {vol.size}GB")
    return unused

if __name__ == "__main__":
    find_unused_ebs_volumes()
