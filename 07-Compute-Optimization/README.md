# 07 — Compute Optimization

> *EC2 and compute are typically 35–55% of total AWS spend. This section covers the full optimization stack: rightsizing, Spot, Reserved Instances, Savings Plans, and Auto Scaling.*

---

## 🏗️ Compute Cost Optimization Hierarchy

```
Priority  Strategy                     Effort    Savings Potential
────────  ───────────────────────────  ────────  ─────────────────
1st       Terminate unused instances   Low       100% of wasted spend
2nd       Rightsize over-provisioned   Medium    30–60% of instance cost
3rd       Spot Instances (stateless)   Medium    60–90% vs On-Demand
4th       Savings Plans (compute-wide) Low       Up to 66% discount
5th       Reserved Instances (stable)  Medium    Up to 72% discount
6th       Graviton (ARM) migration     Medium    20–40% vs x86
7th       Auto Scaling + warm pools    High      Pay only for what you use
```

---

## 🔍 Idle EC2 Detection

### What Makes an Instance "Idle"?

An EC2 instance is considered idle if:
- **CPU utilization** < 5% average over 14 days
- **Network I/O** < 5 MB/hour average
- **Disk I/O** < 1 IOPS average

These thresholds are conservative to avoid false positives.

### Automation: `idle_ec2_detector.py`

```python
"""
idle_ec2_detector.py

Detects idle EC2 instances using CloudWatch metrics.
Sends a Slack report with projected monthly savings.
Defaults to DRY_RUN=True — never terminates without explicit action.

Author: FinOps Automation Suite
Schedule: Weekly (Sunday midnight)
"""

import boto3
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
CPU_THRESHOLD = float(os.environ.get('CPU_THRESHOLD', '5.0'))  # percent
NETWORK_THRESHOLD_MB = float(os.environ.get('NETWORK_THRESHOLD_MB', '5.0'))
LOOKBACK_DAYS = int(os.environ.get('LOOKBACK_DAYS', '14'))
DRY_RUN = os.environ.get('DRY_RUN', 'True').lower() == 'true'
SLACK_WEBHOOK = os.environ.get('SLACK_WEBHOOK_URL', '')

# EC2 On-Demand pricing (simplified — use Price List API for production)
INSTANCE_HOURLY_COST = {
    't3.micro': 0.0104, 't3.small': 0.0208, 't3.medium': 0.0416,
    't3.large': 0.0832, 't3.xlarge': 0.1664, 't3.2xlarge': 0.3328,
    'm5.large': 0.096, 'm5.xlarge': 0.192, 'm5.2xlarge': 0.384,
    'm5.4xlarge': 0.768, 'm5.8xlarge': 1.536,
    'r5.large': 0.126, 'r5.xlarge': 0.252, 'r5.2xlarge': 0.504,
    'c5.large': 0.085, 'c5.xlarge': 0.17, 'c5.2xlarge': 0.34,
    'p3.2xlarge': 3.06, 'p3.8xlarge': 12.24, 'p3.16xlarge': 24.48,
    'g4dn.xlarge': 0.526, 'g4dn.2xlarge': 0.752,
}

def get_cloudwatch_avg(cw_client, instance_id: str, metric_name: str, namespace: str,
                        stat: str, lookback_days: int) -> float:
    """Gets average CloudWatch metric value over lookback period."""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=lookback_days)

    response = cw_client.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric_name,
        Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
        StartTime=start_time,
        EndTime=end_time,
        Period=86400,  # 1 day buckets
        Statistics=[stat]
    )

    datapoints = response.get('Datapoints', [])
    if not datapoints:
        return 0.0
    return sum(dp[stat] for dp in datapoints) / len(datapoints)

def estimate_monthly_cost(instance_type: str) -> float:
    """Estimates monthly On-Demand cost for an instance type."""
    hourly = INSTANCE_HOURLY_COST.get(instance_type, 0.1)  # Default $0.10/hr
    return hourly * 730  # 730 hours/month

def scan_region(region: str) -> List[Dict[str, Any]]:
    """Scans a single region for idle EC2 instances."""
    ec2 = boto3.client('ec2', region_name=region)
    cw = boto3.client('cloudwatch', region_name=region)
    idle_instances = []

    paginator = ec2.get_paginator('describe_instances')
    filters = [{'Name': 'instance-state-name', 'Values': ['running']}]

    for page in paginator.paginate(Filters=filters):
        for reservation in page['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']
                instance_type = instance['InstanceType']
                tags = {t['Key']: t['Value'] for t in instance.get('Tags', [])}
                name = tags.get('Name', instance_id)

                # Skip instances explicitly marked to retain
                if tags.get('FinOps:Retain', '').lower() == 'true':
                    logger.info(f"Skipping retained instance: {instance_id}")
                    continue

                # Get CPU utilization
                avg_cpu = get_cloudwatch_avg(
                    cw, instance_id, 'CPUUtilization', 'AWS/EC2', 'Average', LOOKBACK_DAYS
                )

                # Get Network out (bytes → MB)
                avg_network_bytes = get_cloudwatch_avg(
                    cw, instance_id, 'NetworkOut', 'AWS/EC2', 'Average', LOOKBACK_DAYS
                )
                avg_network_mb = avg_network_bytes / (1024 * 1024)

                if avg_cpu < CPU_THRESHOLD and avg_network_mb < NETWORK_THRESHOLD_MB:
                    monthly_cost = estimate_monthly_cost(instance_type)
                    logger.warning(
                        f"IDLE INSTANCE: {instance_id} ({name}) [{instance_type}] in {region} "
                        f"| CPU: {avg_cpu:.1f}% | Net: {avg_network_mb:.2f} MB/hr "
                        f"| Est. monthly waste: ${monthly_cost:.2f}"
                    )
                    idle_instances.append({
                        'instance_id': instance_id,
                        'name': name,
                        'instance_type': instance_type,
                        'region': region,
                        'avg_cpu_pct': round(avg_cpu, 2),
                        'avg_network_mb': round(avg_network_mb, 2),
                        'estimated_monthly_cost_usd': round(monthly_cost, 2),
                        'owner': tags.get('owner', tags.get('team', 'UNKNOWN')),
                        'tags': tags
                    })

    return idle_instances

def send_slack_report(idle_instances: List[Dict], total_waste: float):
    """Sends Slack summary of idle instances."""
    if not SLACK_WEBHOOK:
        return

    lines = [f"• `{i['instance_id']}` ({i['name']}) — `{i['instance_type']}` in `{i['region']}` "
             f"| CPU: {i['avg_cpu_pct']}% | Owner: {i['owner']} | "
             f"Waste: **${i['estimated_monthly_cost_usd']}/mo**"
             for i in idle_instances[:15]]

    payload = {
        "text": f"🛑 *Idle EC2 Report* — {len(idle_instances)} idle instances found\n"
                f"*Total estimated monthly waste: ${total_waste:,.2f}*\n\n" + "\n".join(lines)
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(SLACK_WEBHOOK, data=data, headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req)

def lambda_handler(event, context):
    ec2_global = boto3.client('ec2', region_name='us-east-1')
    regions = [r['RegionName'] for r in ec2_global.describe_regions()['Regions']]

    all_idle = []
    for region in regions:
        logger.info(f"Scanning region: {region}")
        try:
            idle = scan_region(region)
            all_idle.extend(idle)
        except Exception as e:
            logger.error(f"Error scanning {region}: {e}")

    total_waste = sum(i['estimated_monthly_cost_usd'] for i in all_idle)
    total_annual = total_waste * 12

    logger.info(f"=== IDLE EC2 SUMMARY ===")
    logger.info(f"Total idle instances: {len(all_idle)}")
    logger.info(f"Monthly waste estimate: ${total_waste:,.2f}")
    logger.info(f"Annual waste estimate: ${total_annual:,.2f}")

    if all_idle:
        send_slack_report(all_idle, total_waste)

    return {
        'statusCode': 200,
        'idle_instance_count': len(all_idle),
        'estimated_monthly_waste_usd': round(total_waste, 2),
        'estimated_annual_waste_usd': round(total_annual, 2),
        'instances': all_idle
    }
```

---

## 💸 Reserved Instances vs Savings Plans Decision Framework

```
Question: Should I buy RIs or Savings Plans?

START
  │
  ▼
Is your workload 100% on EC2 in a single region?
  │
  ├── YES ──▶ Is the instance family and size fixed?
  │              │
  │              ├── YES ──▶ Standard Reserved Instance (highest discount, up to 72%)
  │              │            Lock: 1–3 years, specific AZ/region
  │              │
  │              └── NO ──▶  Convertible Reserved Instance (flexibility, up to 66%)
  │                           Can exchange for other instance types
  │
  └── NO ──▶ Do you use Lambda or Fargate in addition to EC2?
               │
               ├── YES ──▶ Compute Savings Plan (most flexible, up to 66%)
               │            Covers EC2, Lambda, Fargate automatically
               │
               └── NO ──▶  EC2 Instance Savings Plan (higher discount, less flex, up to 72%)
                             Locks to instance family, any size/OS/tenancy
```

### Break-Even Analysis Template

| | On-Demand | 1-yr No-Upfront RI | 1-yr All-Upfront RI | 3-yr All-Upfront RI |
|---|---|---|---|---|
| **m5.xlarge hourly** | $0.192 | $0.131 | $0.115 | $0.083 |
| **Monthly cost** | $140.16 | $95.63 | $83.95 | $60.59 |
| **Annual cost** | $1,682 | $1,148 | $1,007 | $727 |
| **Savings vs OD** | — | 32% | 40% | 57% |
| **Break-even (months)** | — | Immediate | 6 months | 18 months |

> **Rule of thumb:** If an workload runs > 70% of the time, Reserved Instances or Savings Plans will be cheaper than On-Demand.

---

## 🚀 Spot Instance Strategy

### Instance Interruption Rates (2024 Reference)

| Interruption Frequency | Instance Types | Best For |
|---|---|---|
| < 5% (lowest risk) | m5, r5, c5 in most AZs | Batch, CI/CD, dev |
| 5–10% (low risk) | m4, c4, r4 | ML training, video processing |
| 10–15% (medium) | p2, g3 | GPU workloads with checkpointing |
| 15–20% (higher) | Latest gen GPU in peak AZs | Experimental only |

### Spot Best Practices

```python
# Example: EC2 Auto Scaling with Spot diversification (Terraform-style Python)
# Never use a single instance type for Spot — diversify across families

SPOT_DIVERSIFICATION_CONFIG = {
    "mixed_instances_policy": {
        "launch_template": {"launch_template_id": "lt-xxx"},
        "instances_distribution": {
            "on_demand_percentage_above_base_capacity": 20,  # 20% On-Demand baseline
            "spot_allocation_strategy": "capacity-optimized-prioritized",
            "spot_instance_pools": 0  # Not used with capacity-optimized
        },
        "overrides": [
            {"instance_type": "m5.xlarge"},
            {"instance_type": "m5a.xlarge"},
            {"instance_type": "m4.xlarge"},
            {"instance_type": "r5.large"},
            {"instance_type": "c5.xlarge"}
        ]
    }
}
```

### Handling Spot Interruptions

```python
# scripts/spot_interruption_handler.py
"""
Handles EC2 Spot interruption notices via EventBridge.
Drains application gracefully before the instance is reclaimed.
"""
import boto3
import logging
import json

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Triggered by EventBridge rule: aws.ec2 / EC2 Spot Instance Interruption Warning
    You have ~2 minutes to drain traffic before the instance is reclaimed.
    """
    detail = event.get('detail', {})
    instance_id = detail.get('instance-id')
    action = detail.get('instance-action')

    logger.warning(f"SPOT INTERRUPTION: Instance {instance_id} will be {action}")

    # 1. Remove from load balancer target group
    elbv2 = boto3.client('elbv2')
    # Get target groups (implement your lookup logic)
    # elbv2.deregister_targets(TargetGroupArn='...', Targets=[{'Id': instance_id}])

    # 2. Trigger scale-out of ASG to replace
    asg = boto3.client('autoscaling')
    # asg.set_instance_health(InstanceId=instance_id, HealthStatus='Unhealthy')

    # 3. Alert on-call
    sns = boto3.client('sns')
    sns.publish(
        TopicArn=f"arn:aws:sns:us-east-1:ACCOUNT:finops-alerts",
        Subject=f"Spot Interruption: {instance_id}",
        Message=json.dumps({'instance_id': instance_id, 'action': action})
    )

    return {'statusCode': 200}
```

---

## 🦾 Graviton Migration Guide

### Cost vs Performance Comparison

| Workload Type | x86 Instance | Graviton Equivalent | Price Reduction | Perf Change |
|---|---|---|---|---|
| Web / API | m5.xlarge ($0.192/hr) | m6g.xlarge ($0.154/hr) | **-20%** | +10–20% |
| Database | r5.2xlarge ($0.504/hr) | r6g.2xlarge ($0.403/hr) | **-20%** | +10–15% |
| Batch Processing | c5.4xlarge ($0.68/hr) | c6g.4xlarge ($0.544/hr) | **-20%** | +15–40% |
| ML Training | m5.8xlarge ($1.536/hr) | m6g.8xlarge ($1.229/hr) | **-20%** | Varies |

### Migration Checklist
- [ ] Validate application supports ARM64 (most languages do)
- [ ] Rebuild Docker images with `--platform linux/arm64`
- [ ] Test native dependencies (some C extensions need recompilation)
- [ ] Run A/B performance benchmark before switching
- [ ] Update Auto Scaling launch templates to include Graviton instance types
- [ ] Monitor latency and error rates for 48h after migration

---

## 📊 Compute Optimizer Integration

```python
# scripts/compute_optimizer_report.py
"""
Pulls Compute Optimizer recommendations and formats them into a
prioritized rightsizing report sorted by projected monthly savings.
"""
import boto3
import csv
import io
from datetime import datetime

def get_ec2_recommendations(region: str = 'us-east-1') -> list:
    co = boto3.client('compute-optimizer', region_name=region)
    recs = []

    paginator = co.get_paginator('get_ec2_instance_recommendations')
    for page in paginator.paginate():
        for rec in page.get('instanceRecommendations', []):
            if rec['finding'] in ['OVER_PROVISIONED', 'UNDER_PROVISIONED']:
                current = rec['currentInstanceType']
                for option in rec['recommendationOptions'][:1]:  # Top recommendation
                    recs.append({
                        'instance_id': rec['instanceArn'].split('/')[-1],
                        'account_id': rec['accountId'],
                        'current_type': current,
                        'recommended_type': option['instanceType'],
                        'finding': rec['finding'],
                        'cpu_utilization': rec['utilizationMetrics'][0]['value'] if rec.get('utilizationMetrics') else 'N/A',
                        'projected_monthly_savings': option.get('projectedUtilizationMetrics', [{}])[0].get('value', 0),
                        'performance_risk': option.get('performanceRisk', 'N/A')
                    })
    return sorted(recs, key=lambda x: float(x['projected_monthly_savings'] or 0), reverse=True)

if __name__ == '__main__':
    recs = get_ec2_recommendations()
    print(f"Found {len(recs)} Compute Optimizer recommendations\n")
    print(f"{'Instance ID':<20} {'Current':<15} {'Recommended':<15} {'Finding':<20} {'CPU%':<8}")
    print("-" * 85)
    for r in recs[:20]:
        print(f"{r['instance_id']:<20} {r['current_type']:<15} {r['recommended_type']:<15} "
              f"{r['finding']:<20} {str(r['cpu_utilization']):<8}")
```

---

*Back: [06 — Cost Anomaly Detection](../06-Cost-Anomaly-Detection/README.md) | Next: [08 — EKS Cost Optimization →](../08-EKS-Cost-Optimization/README.md)*
