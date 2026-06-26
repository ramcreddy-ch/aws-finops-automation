# 18 — Observability Cost Optimization

> *CloudWatch is one of the most consistently underestimated AWS cost categories. Teams monitoring their production environment pay more for the monitoring than some of their services. $30K/month CloudWatch bills are real.*

---

## 📊 CloudWatch Pricing Breakdown

```
CloudWatch Cost Components:

Metrics:
  First 10 metrics:              FREE
  10K metrics:                   $0.30/metric/month
  Custom High-Resolution:        $0.02/metric/month extra

Logs:
  Ingestion:                     $0.50/GB
  Storage:                       $0.03/GB/month
  Insights queries:              $0.005/GB scanned
  Live Tail:                     $0.01/min/viewer

Dashboards:
  First 3 dashboards:            FREE
  Additional:                    $3/dashboard/month

Alarms:
  Standard:                      $0.10/alarm/month
  High-Resolution:               $0.30/alarm/month (10-second)
  Composite:                     $0.50/alarm/month

Contributor Insights:            $0.02/rule/hour + $0.02/1M events
Synthetics Canaries:             $0.0012/run (5-min interval = $526/year/canary)
```

---

## 🚨 Real Incident: $30K/Month CloudWatch Log Bill

**The Pattern:** A startup started with 5 engineers, each instrumenting their services with verbose DEBUG-level logging. CloudWatch log ingestion scaled linearly with traffic. Nobody set retention policies.

**Investigation: Find Your Top Log Cost Offenders**

```python
# scripts/cloudwatch_log_cost_analyzer.py
"""
Analyzes CloudWatch Log Groups by size, ingestion rate, and retention policy.
Identifies the top cost offenders and recommends optimization actions.
"""

import boto3
from datetime import datetime, timezone, timedelta
from typing import List, Dict

def analyze_log_groups(region: str = 'us-east-1') -> List[Dict]:
    logs = boto3.client('logs', region_name=region)
    cw = boto3.client('cloudwatch', region_name=region)

    log_groups = []
    paginator = logs.get_paginator('describe_log_groups')

    LOG_INGESTION_COST_PER_GB = 0.50
    LOG_STORAGE_COST_PER_GB_MONTH = 0.03

    for page in paginator.paginate():
        for lg in page['logGroups']:
            name = lg['logGroupName']
            stored_bytes = lg.get('storedBytes', 0)
            stored_gb = stored_bytes / (1024 ** 3)
            retention_days = lg.get('retentionInDays', None)

            # Get incoming bytes over last 7 days
            now = datetime.now(timezone.utc)
            week_ago = now - timedelta(days=7)
            ingestion_resp = cw.get_metric_statistics(
                Namespace='AWS/Logs',
                MetricName='IncomingBytes',
                Dimensions=[{'Name': 'LogGroupName', 'Value': name}],
                StartTime=week_ago, EndTime=now,
                Period=604800, Statistics=['Sum']
            )
            weekly_ingestion_bytes = sum(dp['Sum'] for dp in ingestion_resp.get('Datapoints', []))
            weekly_ingestion_gb = weekly_ingestion_bytes / (1024 ** 3)
            monthly_ingestion_gb = weekly_ingestion_gb * (30 / 7)

            monthly_ingestion_cost = monthly_ingestion_gb * LOG_INGESTION_COST_PER_GB
            monthly_storage_cost = stored_gb * LOG_STORAGE_COST_PER_GB_MONTH
            total_monthly_cost = monthly_ingestion_cost + monthly_storage_cost

            log_groups.append({
                'name': name,
                'stored_gb': round(stored_gb, 3),
                'monthly_ingestion_gb': round(monthly_ingestion_gb, 3),
                'retention_days': retention_days or 'NEVER EXPIRES ⚠️',
                'monthly_ingestion_cost_usd': round(monthly_ingestion_cost, 2),
                'monthly_storage_cost_usd': round(monthly_storage_cost, 2),
                'total_monthly_cost_usd': round(total_monthly_cost, 2)
            })

    return sorted(log_groups, key=lambda x: x['total_monthly_cost_usd'], reverse=True)

def set_retention_policies(log_groups: List[Dict], default_retention_days: int = 30,
                            dry_run: bool = True, region: str = 'us-east-1'):
    """Sets retention policies on log groups that have NEVER EXPIRES."""
    logs = boto3.client('logs', region_name=region)

    for lg in log_groups:
        if lg['retention_days'] == 'NEVER EXPIRES ⚠️':
            print(f"{'[DRY RUN] ' if dry_run else ''}Setting {default_retention_days}d retention: {lg['name']}")
            if not dry_run:
                logs.put_retention_policy(
                    logGroupName=lg['name'],
                    retentionInDays=default_retention_days
                )

if __name__ == '__main__':
    print("Analyzing CloudWatch Log Groups...\n")
    groups = analyze_log_groups()

    total_cost = sum(g['total_monthly_cost_usd'] for g in groups)
    no_retention = [g for g in groups if g['retention_days'] == 'NEVER EXPIRES ⚠️']

    print(f"{'Log Group':<60} {'Stored GB':<12} {'Ingest GB/mo':<14} {'Retention':<20} {'Cost/mo'}")
    print("-" * 130)
    for g in groups[:20]:
        print(f"{g['name'][:58]:<60} {g['stored_gb']:<12} {g['monthly_ingestion_gb']:<14} "
              f"{str(g['retention_days']):<20} ${g['total_monthly_cost_usd']}")

    print(f"\nTotal estimated monthly cost: ${total_cost:,.2f}")
    print(f"Log groups with NO retention policy: {len(no_retention)}")
    print(f"\nEstimated savings from setting 30-day retention on all: "
          f"${sum(g['monthly_storage_cost_usd'] * 0.9 for g in no_retention):,.2f}/mo")
```

---

## 🔧 Log Optimization Strategies

### Strategy 1: Retention Policies (Immediate, No Code Changes)

```bash
# Set 30-day retention on ALL log groups with no policy (AWS CLI)
aws logs describe-log-groups \
  --query 'logGroups[?!retentionInDays].logGroupName' \
  --output text | tr '\t' '\n' | while read lg; do
    echo "Setting retention: $lg"
    aws logs put-retention-policy \
      --log-group-name "$lg" \
      --retention-in-days 30
done

# Recommended retention by log type:
# Application DEBUG logs:   7 days
# Application INFO logs:    30 days
# Application ERROR logs:   90 days
# Access logs (ALB/CF):     30 days
# VPC Flow Logs:            14 days
# CloudTrail:               365 days (compliance)
# RDS logs:                 7 days
```

### Strategy 2: Filter Before Ingestion

```python
# Lambda subscription filter: Drop DEBUG logs before CloudWatch ingestion
# This eliminates ingestion costs for verbose logs

import json
import base64
import gzip

def lambda_handler(event, context):
    """
    CloudWatch Logs subscription filter Lambda.
    Drops DEBUG/TRACE level logs to save $0.50/GB ingestion cost.
    Forward only ERROR and WARN to a separate high-priority log group.
    """
    # Decode the CloudWatch Logs data
    compressed = base64.b64decode(event['awslogs']['data'])
    payload = json.loads(gzip.decompress(compressed))

    log_group = payload['logGroup']
    log_events = payload['logEvents']

    kept_events = 0
    dropped_events = 0

    for event_data in log_events:
        message = event_data.get('message', '')

        # Drop verbose log levels
        if any(level in message.upper() for level in ['[DEBUG]', '[TRACE]', 'DEBUG:', 'TRACE:']):
            dropped_events += 1
            continue

        kept_events += 1

    print(f"Log filter: kept={kept_events}, dropped={dropped_events} from {log_group}")
    return {'statusCode': 200}
```

### Strategy 3: Move to S3 + Athena for Cheap Long-Term Storage

```python
# scripts/export_logs_to_s3.py
"""
Exports CloudWatch Logs to S3 for long-term storage.
S3 storage: $0.023/GB vs CloudWatch: $0.03/GB + $0.50/GB ingestion
After export, delete from CloudWatch.
"""
import boto3
import time

def export_log_group_to_s3(log_group_name: str, s3_bucket: str,
                             prefix: str, region: str = 'us-east-1') -> str:
    logs = boto3.client('logs', region_name=region)

    task = logs.create_export_task(
        logGroupName=log_group_name,
        fromTime=0,  # Beginning of time
        to=int(time.time() * 1000),
        destination=s3_bucket,
        destinationPrefix=f"{prefix}/{log_group_name.lstrip('/')}"
    )

    task_id = task['taskId']
    print(f"Export task created: {task_id} for {log_group_name} → s3://{s3_bucket}/{prefix}/")

    # Poll for completion
    while True:
        result = logs.describe_export_tasks(taskId=task_id)
        status = result['exportTasks'][0]['status']['code']
        if status == 'COMPLETED':
            print(f"Export complete: {task_id}")
            break
        elif status == 'FAILED':
            print(f"Export FAILED: {task_id}")
            break
        time.sleep(30)

    return task_id
```

---

## 📈 CloudWatch Metrics Optimization

### Eliminate High-Cardinality Custom Metrics

```python
# ANTI-PATTERN: Creates one metric per user (high cardinality = $$$)
cw.put_metric_data(
    Namespace='MyApp',
    MetricData=[{
        'MetricName': 'APILatency',
        'Dimensions': [
            {'Name': 'UserId', 'Value': user_id},  # ⚠️ HIGH CARDINALITY
            {'Name': 'Endpoint', 'Value': endpoint}
        ],
        'Value': latency_ms,
        'Unit': 'Milliseconds'
    }]
)
# With 100K users × 50 endpoints = 5M dimensions = $1,500/month

# BETTER PATTERN: Aggregate at the endpoint level only
cw.put_metric_data(
    Namespace='MyApp',
    MetricData=[{
        'MetricName': 'APILatency',
        'Dimensions': [
            {'Name': 'Endpoint', 'Value': endpoint},  # ✅ Low cardinality
            {'Name': 'StatusCode', 'Value': str(status_code)}
        ],
        'Value': latency_ms,
        'Unit': 'Milliseconds'
    }]
)
# 50 endpoints × 5 status codes = 250 dimensions = $75/month
```

### Use Embedded Metrics Format (EMF) — Free Custom Metrics from Lambda

```python
# EMF: Metrics embedded in CloudWatch Logs — no separate PutMetricData charge
# Just pay for log ingestion, get metrics FREE

import json
import time

def lambda_handler(event, context):
    start = time.time()

    # ... your business logic ...

    latency = (time.time() - start) * 1000

    # EMF format — automatically parsed into CloudWatch metrics
    print(json.dumps({
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": "MyApp",
                "Dimensions": [["FunctionName", "Environment"]],
                "Metrics": [
                    {"Name": "ProcessingLatency", "Unit": "Milliseconds"},
                    {"Name": "ItemsProcessed", "Unit": "Count"}
                ]
            }]
        },
        "FunctionName": context.function_name,
        "Environment": "production",
        "ProcessingLatency": latency,
        "ItemsProcessed": 42
    }))
```

---

## 🔍 Athena: Replace CloudWatch Insights (90% Cheaper)

```sql
-- CloudWatch Insights query costs $0.005/GB scanned
-- Same query on S3 via Athena: $0.005/TB scanned = 1000x cheaper

-- Step 1: Export logs to S3 with Glue table
-- Step 2: Query with Athena

-- Example: Find top error messages (same as CW Insights but ~free)
SELECT
    error_type,
    COUNT(*) AS occurrences,
    MAX(timestamp) AS last_seen
FROM
    "app_logs_db"."application_logs"
WHERE
    dt = '2024-06'
    AND level = 'ERROR'
GROUP BY
    error_type
ORDER BY
    occurrences DESC
LIMIT 20;
```

---

## ✅ Observability Cost Checklist

### Immediate
- [ ] Set retention policies on ALL CloudWatch Log Groups (max 90 days for most)
- [ ] Audit Synthetics canaries — each 5-min canary costs $526/year
- [ ] Count high-resolution alarms — replace 10-second with 1-minute where possible
- [ ] Identify log groups with > 1GB stored and no retention policy

### Short-Term
- [ ] Switch Lambda logging to Embedded Metrics Format (free custom metrics)
- [ ] Set up CloudWatch Logs subscription filter to drop DEBUG logs
- [ ] Export old logs (> 90 days) to S3 Glacier Instant Retrieval
- [ ] Migrate CloudWatch Insights queries for historical analysis to Athena

### Strategic
- [ ] Evaluate OpenTelemetry Collector for metrics — ship to Prometheus/Grafana (cheaper at scale)
- [ ] Use CloudWatch Metric Streams → Firehose → S3 for cost-efficient metric storage
- [ ] Implement structured logging (JSON) to enable better filtering and reduce log volume

---

*Back: [17 — Bedrock FinOps](../17-Bedrock-FinOps/README.md) | Next: [19 — Multi-Account FinOps →](../19-Multi-Account-FinOps/README.md)*
