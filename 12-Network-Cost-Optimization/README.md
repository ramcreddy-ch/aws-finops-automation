# 12 — Network Cost Optimization

> *Network is the most underestimated cost category. NAT Gateways, cross-region data transfer, and inter-AZ traffic regularly rank in the top 3 line items for data-heavy companies.*

---

## 🌐 AWS Network Cost Anatomy

```
AWS Network Charges (per GB transferred):

WITHIN SAME AZ:        FREE
Same region, diff AZ:  $0.01/GB each direction = $0.02/GB round trip
Same region, VPC peer: $0.01/GB each direction
Internet Egress:       $0.085–$0.09/GB (first 10TB/month)
Cross-Region:          $0.02–$0.08/GB (depends on region pair)
NAT Gateway:           $0.045/GB processed + $0.045/hr
PrivateLink:           $0.01/GB + $0.01/AZ/hr
CloudFront:            $0.0085–$0.085/GB (massive savings vs direct)
S3 Transfer Accel:     $0.04–$0.08/GB on top of S3 prices
```

---

## 🚨 Real Incident: NAT Gateway Bill Exploded

**Scenario:** A FinTech company's AWS bill increased by $22K/month. NAT Gateway processing went from 500GB to 12TB/month.

**Investigation:**

```python
# scripts/nat_gateway_analyzer.py
"""
Analyzes NAT Gateway traffic using CloudWatch Metrics and VPC Flow Logs.
Identifies which subnets and instances are sending the most traffic through NAT GW.
"""

import boto3
import json
from datetime import datetime, timezone, timedelta

def get_nat_gateway_traffic(region: str = 'us-east-1', lookback_days: int = 7) -> list:
    """Returns NAT Gateway traffic stats for the region."""
    ec2 = boto3.client('ec2', region_name=region)
    cw = boto3.client('cloudwatch', region_name=region)

    nat_gateways = ec2.describe_nat_gateways(
        Filter=[{'Name': 'state', 'Values': ['available']}]
    )['NatGateways']

    results = []
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=lookback_days)

    for nat in nat_gateways:
        nat_id = nat['NatGatewayId']
        subnet_id = nat['SubnetId']

        # Get bytes out to destination (internet-bound traffic)
        metrics = cw.get_metric_statistics(
            Namespace='AWS/NATGateway',
            MetricName='BytesOutToDestination',
            Dimensions=[{'Name': 'NatGatewayId', 'Value': nat_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,
            Statistics=['Sum']
        )

        total_bytes = sum(dp['Sum'] for dp in metrics.get('Datapoints', []))
        total_gb = total_bytes / (1024 ** 3)
        estimated_cost = total_gb * 0.045  # $0.045/GB

        # Get packets dropped (sign of congestion)
        dropped = cw.get_metric_statistics(
            Namespace='AWS/NATGateway',
            MetricName='PacketsDropCount',
            Dimensions=[{'Name': 'NatGatewayId', 'Value': nat_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,
            Statistics=['Sum']
        )
        total_dropped = sum(dp['Sum'] for dp in dropped.get('Datapoints', []))

        results.append({
            'nat_gateway_id': nat_id,
            'subnet_id': subnet_id,
            'region': region,
            'total_gb_7d': round(total_gb, 2),
            'estimated_processing_cost_7d': round(estimated_cost, 2),
            'estimated_monthly_cost': round(estimated_cost * 30 / lookback_days, 2),
            'packets_dropped': int(total_dropped),
            'tags': {t['Key']: t['Value'] for t in nat.get('Tags', [])}
        })

    return sorted(results, key=lambda x: x['total_gb_7d'], reverse=True)

if __name__ == '__main__':
    results = get_nat_gateway_traffic()
    for nat in results:
        print(f"\nNAT Gateway: {nat['nat_gateway_id']} ({nat['subnet_id']})")
        print(f"  Traffic (7d): {nat['total_gb_7d']} GB")
        print(f"  Est. Monthly Cost: ${nat['estimated_monthly_cost']}")
        print(f"  Packets Dropped: {nat['packets_dropped']}")
```

**Root Cause Found via VPC Flow Logs Athena Query:**

```sql
-- Query: Find top talkers through NAT Gateway using VPC Flow Logs
-- This identified that EKS pods were pulling container images from Docker Hub (internet)
-- instead of ECR (internal) — causing massive egress through NAT GW

SELECT
    srcaddr,
    dstaddr,
    SUM(bytes) / 1073741824.0 AS total_gb,
    COUNT(*) AS flow_count,
    MIN(start) AS first_seen,
    MAX(start) AS last_seen
FROM
    vpc_flow_logs
WHERE
    year = '2024'
    AND month = '06'
    AND action = 'ACCEPT'
    AND flow_direction = 'egress'
    -- NAT Gateway ENI ID
    AND interface_id = 'eni-REPLACE_WITH_NAT_ENI'
GROUP BY
    srcaddr, dstaddr
ORDER BY
    total_gb DESC
LIMIT 50;
```

**Resolution:** Migrated all container images to Amazon ECR. Pods now pull from ECR via VPC endpoint — zero NAT Gateway charges for image pulls. **Savings: $18K/month.**

---

## 🔌 VPC Endpoints: The Most Underused Cost Saver

### Services Where VPC Endpoints Eliminate NAT Gateway Costs

| AWS Service | Without Endpoint | With Gateway Endpoint | With Interface Endpoint | Savings |
|---|---|---|---|---|
| **S3** | $0.045/GB via NAT | FREE (Gateway EP) | — | 100% |
| **DynamoDB** | $0.045/GB via NAT | FREE (Gateway EP) | — | 100% |
| **ECR API** | $0.045/GB via NAT | — | $0.01/GB + $7.30/AZ/mo | ~78% |
| **ECR DKR** | $0.045/GB via NAT | — | $0.01/GB + $7.30/AZ/mo | ~78% |
| **SSM** | $0.045/GB via NAT | — | $0.01/GB + $7.30/AZ/mo | ~78% |
| **Secrets Manager** | $0.045/GB via NAT | — | $0.01/GB + $7.30/AZ/mo | ~78% |
| **STS** | $0.045/GB via NAT | — | $0.01/GB + $7.30/AZ/mo | ~78% |
| **CloudWatch Logs** | $0.045/GB via NAT | — | $0.01/GB + $7.30/AZ/mo | ~78% |

> ⚡ **Quick Win:** Creating S3 and DynamoDB Gateway Endpoints costs nothing and immediately eliminates all NAT Gateway charges for S3/DynamoDB traffic.

### Terraform: Create All Critical VPC Endpoints

```hcl
# terraform/modules/vpc-endpoints/main.tf

locals {
  # Gateway endpoints — FREE
  gateway_endpoints = {
    s3 = {
      service_name = "com.amazonaws.${var.region}.s3"
      route_table_ids = var.private_route_table_ids
    }
    dynamodb = {
      service_name = "com.amazonaws.${var.region}.dynamodb"
      route_table_ids = var.private_route_table_ids
    }
  }

  # Interface endpoints — $0.01/GB + $7.30/AZ/month
  # Only create if NAT GW cost > endpoint cost
  interface_endpoints = {
    ecr_api = {
      service_name = "com.amazonaws.${var.region}.ecr.api"
    }
    ecr_dkr = {
      service_name = "com.amazonaws.${var.region}.ecr.dkr"
    }
    ssm = {
      service_name = "com.amazonaws.${var.region}.ssm"
    }
    secrets_manager = {
      service_name = "com.amazonaws.${var.region}.secretsmanager"
    }
    sts = {
      service_name = "com.amazonaws.${var.region}.sts"
    }
    cloudwatch_logs = {
      service_name = "com.amazonaws.${var.region}.logs"
    }
    cloudwatch_monitoring = {
      service_name = "com.amazonaws.${var.region}.monitoring"
    }
  }
}

resource "aws_vpc_endpoint" "gateway" {
  for_each = local.gateway_endpoints

  vpc_id            = var.vpc_id
  service_name      = each.value.service_name
  vpc_endpoint_type = "Gateway"
  route_table_ids   = each.value.route_table_ids

  tags = merge(var.common_tags, {
    Name        = "vpce-${each.key}-${var.environment}"
    FinOps      = "cost-optimization"
    SavesNATGW  = "true"
  })
}

resource "aws_vpc_endpoint" "interface" {
  for_each = local.interface_endpoints

  vpc_id              = var.vpc_id
  service_name        = each.value.service_name
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(var.common_tags, {
    Name      = "vpce-${each.key}-${var.environment}"
    FinOps    = "cost-optimization"
  })
}

resource "aws_security_group" "vpc_endpoints" {
  name        = "vpc-endpoints-sg-${var.environment}"
  description = "Security group for VPC Interface Endpoints"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
    description = "Allow HTTPS from VPC CIDR"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.common_tags
}
```

---

## 🌍 Cross-Region Data Transfer Optimization

### Identifying Cross-Region Costs in CUR

```sql
-- Athena query: Find top cross-region data transfer charges
SELECT
    product_from_location AS source_region,
    product_to_location AS destination_region,
    line_item_resource_id,
    SUM(line_item_usage_amount) AS total_gb,
    SUM(line_item_unblended_cost) AS total_cost_usd
FROM
    "your_cur_database"."your_cur_table"
WHERE
    year = '2024'
    AND month = '06'
    AND line_item_usage_type LIKE '%DataTransfer-Regional%'
    OR line_item_usage_type LIKE '%DataTransfer-Out-Bytes%'
GROUP BY
    product_from_location,
    product_to_location,
    line_item_resource_id
ORDER BY
    total_cost_usd DESC
LIMIT 50;
```

### Inter-AZ Traffic Reduction Strategies

| Pattern | Anti-Pattern | Cost | Optimized Pattern | Saving |
|---|---|---|---|---|
| Microservices | Pods spread randomly across AZs | $0.02/GB | Topology Spread Constraints same-AZ | ~95% |
| Database Reads | Read replicas in different AZ from app | $0.02/GB | Same-AZ read replicas | ~95% |
| ElastiCache | Multi-AZ cluster, cross-AZ reads | $0.02/GB | Read from local AZ node | ~95% |
| ALB | ALB in us-east-1a, targets in 1b | $0.02/GB | Enable Zonal Shift / cross-zone LB off | 50% |

### Kubernetes Topology Constraints for Same-AZ Placement

```yaml
# Ensure pods prefer same AZ as their dependencies
spec:
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: DoNotSchedule
      labelSelector:
        matchLabels:
          app: payment-service
  affinity:
    podAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 100
          podAffinityTerm:
            labelSelector:
              matchLabels:
                app: payment-database
            topologyKey: topology.kubernetes.io/zone
```

---

## 📊 NAT Gateway Auditor Lambda

```python
# 25-Automation/lambda_functions/nat_gateway_auditor.py
"""
Detects idle NAT Gateways and those with anomalously high traffic.
Idle NAT GW: < 1GB processed in 7 days but still incurring hourly charges ($0.045/hr = $32.85/mo)
High traffic: Flags NAT GWs processing > 1TB/month for VPC endpoint review.
"""

import boto3
import os
import logging
import json
import urllib.request
from datetime import datetime, timezone, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DRY_RUN = os.environ.get('DRY_RUN', 'True').lower() == 'true'
IDLE_GB_THRESHOLD = float(os.environ.get('IDLE_GB_THRESHOLD', '1.0'))
HIGH_TRAFFIC_GB_THRESHOLD = float(os.environ.get('HIGH_TRAFFIC_GB_THRESHOLD', '1000.0'))
SLACK_WEBHOOK = os.environ.get('SLACK_WEBHOOK_URL', '')
NAT_HOURLY_COST = 0.045
NAT_DATA_COST_PER_GB = 0.045

def get_nat_metrics(cw, nat_id: str, metric_name: str, lookback_days: int) -> float:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    resp = cw.get_metric_statistics(
        Namespace='AWS/NATGateway',
        MetricName=metric_name,
        Dimensions=[{'Name': 'NatGatewayId', 'Value': nat_id}],
        StartTime=start, EndTime=end,
        Period=86400, Statistics=['Sum']
    )
    return sum(dp['Sum'] for dp in resp.get('Datapoints', []))

def lambda_handler(event, context):
    ec2_global = boto3.client('ec2', region_name='us-east-1')
    regions = [r['RegionName'] for r in ec2_global.describe_regions()['Regions']]

    idle_gateways = []
    high_traffic_gateways = []

    for region in regions:
        ec2 = boto3.client('ec2', region_name=region)
        cw = boto3.client('cloudwatch', region_name=region)

        nats = ec2.describe_nat_gateways(
            Filter=[{'Name': 'state', 'Values': ['available']}]
        ).get('NatGateways', [])

        for nat in nats:
            nat_id = nat['NatGatewayId']
            tags = {t['Key']: t['Value'] for t in nat.get('Tags', [])}

            if tags.get('FinOps:Retain', '').lower() == 'true':
                continue

            bytes_out = get_nat_metrics(cw, nat_id, 'BytesOutToDestination', 7)
            total_gb = bytes_out / (1024 ** 3)
            monthly_fixed_cost = NAT_HOURLY_COST * 730
            monthly_data_cost = total_gb * NAT_DATA_COST_PER_GB * (30 / 7)

            if total_gb < IDLE_GB_THRESHOLD:
                logger.warning(
                    f"IDLE NAT GATEWAY: {nat_id} in {region} | "
                    f"Traffic (7d): {total_gb:.3f} GB | Monthly fixed cost: ${monthly_fixed_cost:.2f}"
                )
                idle_gateways.append({
                    'nat_id': nat_id, 'region': region,
                    'traffic_gb_7d': round(total_gb, 3),
                    'monthly_cost_if_deleted': round(monthly_fixed_cost, 2),
                    'tags': tags
                })
            elif total_gb > HIGH_TRAFFIC_GB_THRESHOLD:
                logger.info(
                    f"HIGH TRAFFIC NAT: {nat_id} in {region} | "
                    f"Traffic (7d): {total_gb:.1f} GB | VPC endpoint review recommended"
                )
                high_traffic_gateways.append({
                    'nat_id': nat_id, 'region': region,
                    'traffic_gb_7d': round(total_gb, 1),
                    'estimated_monthly_data_cost': round(monthly_data_cost, 2),
                    'recommendation': 'Create VPC endpoints for S3/ECR/SSM to reduce traffic'
                })

    total_idle_savings = sum(g['monthly_cost_if_deleted'] for g in idle_gateways)

    if SLACK_WEBHOOK and (idle_gateways or high_traffic_gateways):
        msg = f"🌐 *NAT Gateway Audit Report*\n\n"
        if idle_gateways:
            msg += f"*{len(idle_gateways)} IDLE NAT Gateways* (potential savings: ${total_idle_savings:.2f}/mo):\n"
            for g in idle_gateways[:5]:
                msg += f"  • `{g['nat_id']}` in `{g['region']}` — {g['traffic_gb_7d']} GB/7d | ${g['monthly_cost_if_deleted']}/mo\n"
        if high_traffic_gateways:
            msg += f"\n*{len(high_traffic_gateways)} High-Traffic NAT Gateways* (VPC endpoint candidates):\n"
            for g in high_traffic_gateways[:5]:
                msg += f"  • `{g['nat_id']}` in `{g['region']}` — {g['traffic_gb_7d']} GB/7d | ${g['estimated_monthly_data_cost']}/mo\n"

        data = json.dumps({"text": msg}).encode('utf-8')
        req = urllib.request.Request(SLACK_WEBHOOK, data=data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req)

    return {
        'statusCode': 200,
        'idle_nat_gateways': len(idle_gateways),
        'high_traffic_nat_gateways': len(high_traffic_gateways),
        'estimated_idle_monthly_savings_usd': round(total_idle_savings, 2),
        'idle_details': idle_gateways,
        'high_traffic_details': high_traffic_gateways
    }
```

---

## ✅ Network Cost Optimization Checklist

### Immediate (No Code Required)
- [ ] Create S3 Gateway Endpoint in every VPC (FREE, immediate savings)
- [ ] Create DynamoDB Gateway Endpoint in every VPC (FREE)
- [ ] Enable CloudFront for any public-facing S3 or API traffic
- [ ] Review cross-region replication — is it all necessary?

### Short-Term
- [ ] Analyze NAT Gateway traffic by ENI using VPC Flow Logs
- [ ] Identify top-10 internet destinations from NAT GW (likely Docker Hub, GitHub, etc.)
- [ ] Migrate container image pulls to ECR (eliminates Docker Hub egress)
- [ ] Create Interface Endpoints for ECR, SSM, Secrets Manager

### Architecture Changes
- [ ] Implement same-AZ pod placement for microservices
- [ ] Configure ElastiCache read from local AZ node
- [ ] Review ALB cross-zone load balancing need
- [ ] Evaluate AWS Global Accelerator vs direct internet routing for global users

---

*Back: [11 — S3 Cost Optimization](../11-S3-Cost-Optimization/README.md) | Next: [13 — Storage Cost Optimization →](../13-Storage-Cost-Optimization/README.md)*
