# 10 — RDS Cost Optimization

> *Databases are usually the largest single line item after EC2. Because they hold state, teams are terrified to touch them. Consequently, they remain vastly over-provisioned for years.*

---

## 💡 The RDS Cost Hierarchy

1. **Instance Class (Compute/RAM):** 50-70% of cost.
2. **Storage Type & Size:** 20-40% of cost (gp2/gp3 vs io1/io2).
3. **Multi-AZ:** 2x cost multiplier.
4. **Data Transfer:** Cross-AZ replication is free, but cross-region is not.
5. **Snapshots/Backups:** Often ignored, but retained manual snapshots grow forever.

---

## 🤖 RDS Rightsizing Intelligence

```python
# 25-Automation/lambda_functions/rds_rightsizing.py
"""
Analyzes RDS instances to find over-provisioned compute and memory.
Identifies candidates for downscaling or migration to Graviton/Serverless.
"""
import boto3
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def analyze_rds_instances(region: str = 'us-east-1', lookback_days: int = 14):
    rds = boto3.client('rds', region_name=region)
    cw = boto3.client('cloudwatch', region_name=region)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)

    instances = rds.describe_db_instances()['DBInstances']
    recommendations = []

    for db in instances:
        db_id = db['DBInstanceIdentifier']
        instance_class = db['DBInstanceClass']
        engine = db['Engine']
        multi_az = db['MultiAZ']
        status = db['DBInstanceStatus']

        if status != 'available':
            continue

        # Get CPU Utilization
        cpu_metrics = cw.get_metric_statistics(
            Namespace='AWS/RDS', MetricName='CPUUtilization',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
            StartTime=start, EndTime=end, Period=86400, Statistics=['Average', 'Maximum']
        )

        # Get Database Connections
        conn_metrics = cw.get_metric_statistics(
            Namespace='AWS/RDS', MetricName='DatabaseConnections',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
            StartTime=start, EndTime=end, Period=86400, Statistics=['Maximum']
        )

        avg_cpu = sum(dp['Average'] for dp in cpu_metrics.get('Datapoints', [{'Average': 0}])) / max(len(cpu_metrics.get('Datapoints', [])), 1)
        max_cpu = max((dp['Maximum'] for dp in cpu_metrics.get('Datapoints', [])), default=0)
        max_conn = max((dp['Maximum'] for dp in conn_metrics.get('Datapoints', [])), default=0)

        # Evaluation Logic
        findings = []
        if max_cpu < 20.0:
            findings.append("Significantly over-provisioned CPU")
        if max_conn == 0:
            findings.append("ZOMBIE DATABASE (0 connections in 14 days)")

        if engine in ['aurora-postgresql', 'aurora-mysql'] and avg_cpu < 10.0 and max_cpu < 30.0:
            findings.append("Candidate for Aurora Serverless v2")

        if 'g' not in instance_class and engine in ['postgres', 'mysql', 'aurora-postgresql']:
            findings.append("Migrate to Graviton (e.g., db.r6g) for 10% lower cost")

        if findings:
            recommendations.append({
                'id': db_id,
                'class': instance_class,
                'env': 'Multi-AZ' if multi_az else 'Single-AZ',
                'max_cpu': round(max_cpu, 1),
                'max_conn': max_conn,
                'recommendations': findings
            })

    print(f"\nRDS Rightsizing Report ({region})")
    print("-" * 100)
    for r in sorted(recommendations, key=lambda x: x['max_cpu']):
        print(f"DB: {r['id'][:20]:<22} | {r['class']:<15} | {r['env']:<10} | Max CPU: {r['max_cpu']}% | Conns: {r['max_conn']}")
        for f in r['recommendations']:
            print(f"  ↳ {f}")

if __name__ == '__main__':
    analyze_rds_instances()
```

---

## 💾 Storage: The gp2 to gp3 Migration

AWS introduced `gp3` storage which is **20% cheaper** than `gp2` and provides baseline performance of 3,000 IOPS and 125 MBps regardless of volume size.

**There is zero reason to use `gp2` in 2024.**

```bash
# Find all RDS instances using gp2
aws rds describe-db-instances \
  --query 'DBInstances[?StorageType==`gp2`].[DBInstanceIdentifier,AllocatedStorage]' \
  --output table

# Convert to gp3 (Zero downtime, online operation)
aws rds modify-db-instance \
  --db-instance-identifier YOUR_DB_ID \
  --storage-type gp3 \
  --apply-immediately
```

---

## 💤 Dev/Test Database Scheduling

Development databases running 24/7 waste exactly 73% of their cost (168 hours in a week, used for 45 hours).

### Terraform: AWS Instance Scheduler Integration

Instead of custom lambdas, use the official AWS Instance Scheduler.

```hcl
# Tag your RDS instances for the scheduler
resource "aws_db_instance" "dev_db" {
  identifier        = "dev-backend-db"
  instance_class    = "db.t4g.medium"
  engine            = "postgres"
  # ... other config ...

  tags = {
    Environment = "dev"
    Schedule    = "uk-office-hours" # Matches schedule configured in AWS Instance Scheduler
  }
}
```

---

## 📈 Aurora Serverless v2 vs Provisioned

Aurora Serverless v2 scales in milliseconds, but **1 ACU (Aurora Capacity Unit) costs twice as much as the equivalent provisioned compute.**

**The Break-Even Math:**
- If your database utilization is spiky and averages **< 40%** of its peak, Serverless v2 is cheaper.
- If your database runs at steady utilization > 50%, Provisioned is cheaper.

**Migration path:**
1. Add a Serverless v2 reader to your provisioned cluster.
2. Monitor its ACU scaling behavior in CloudWatch for 1 week.
3. If ACU average cost < Provisioned cost, failover to the Serverless instance.

---

## ✅ RDS Optimization Checklist

- [ ] Ensure ZERO databases are using `gp2` storage (migrate to `gp3`).
- [ ] Migrate open-source engines (MySQL/PG) to Graviton instance classes (`db.m6g`, `db.r6g`).
- [ ] Tag all non-production DBs and enforce start/stop schedules (save 70%).
- [ ] Identify Zombie databases (0 connections in 14 days) -> Snapshot and terminate.
- [ ] Review Provisioned IOPS (`io1`/`io2`) — many can run on `gp3` with purchased IOPS for much less.
- [ ] Delete manual snapshots older than 90 days.
