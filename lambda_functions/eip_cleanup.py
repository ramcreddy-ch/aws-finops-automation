import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Finds and releases unassociated Elastic IP (EIP) addresses.
    Unassociated EIPs cost ~$3.60/month per IP.
    """
    dry_run = os.environ.get('DRY_RUN', 'True').lower() == 'true'
    
    # We must check all regions since EIPs are regional
    ec2_global = boto3.client('ec2', region_name='us-east-1')
    regions = [r['RegionName'] for r in ec2_global.describe_regions()['Regions']]
    
    released_count = 0
    total_savings = 0.0
    
    logger.info(f"Starting EIP Cleanup (Dry Run: {dry_run})")
    
    for region in regions:
        ec2 = boto3.client('ec2', region_name=region)
        
        # Describe all EIPs in the region
        addresses = ec2.describe_addresses()['Addresses']
        
        for address in addresses:
            public_ip = address.get('PublicIp')
            allocation_id = address.get('AllocationId')
            association_id = address.get('AssociationId')
            
            # If AssociationId is missing, the IP is not attached to an EC2 instance or NAT Gateway
            if not association_id:
                logger.warning(f"Releasing unassociated EIP: {public_ip} in {region}")
                if not dry_run:
                    try:
                        ec2.release_address(AllocationId=allocation_id)
                        released_count += 1
                        total_savings += 3.60
                    except Exception as e:
                        logger.error(f"Failed to release EIP {public_ip}: {e}")
                else:
                    released_count += 1
                    total_savings += 3.60
                    
    summary = f"EIP Cleanup Complete. Released: {released_count}. Est Savings: ${total_savings:.2f}/mo"
    logger.info(summary)
    
    return {'statusCode': 200, 'body': summary}
