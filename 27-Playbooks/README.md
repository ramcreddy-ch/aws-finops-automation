# 27 — FinOps Playbooks

> *When costs spike, you have minutes to diagnose and hours to resolve. These playbooks are your production runbooks — battle-tested investigation paths used at scale.*

---

## 📋 Index of Playbooks

| # | Playbook | Trigger | Typical Time to Resolve |
|---|---|---|---|
| P1 | [AWS Bill Increased 40% This Month](#p1) | Finance alert / Budget breach | 2–8 hours investigation |
| P2 | [EKS Cluster Cost Doubled Overnight](#p2) | CloudWatch alarm | 1–4 hours |
| P3 | [NAT Gateway Cost > EC2 Cost](#p3) | Cost Explorer anomaly | 4–16 hours |
| P4 | [CloudWatch Logs at $30K/month](#p4) | Budget alert | 2–4 hours |
| P5 | [GPU Instance Left Running](#p5) | Anomaly detection alert | 30 minutes |
| P6 | [Lambda Recursive Invocation Explosion](#p6) | Cost + error alarms | 15 minutes (critical) |
| P7 | [S3 Egress Costs Unexpectedly High](#p7) | Budget alert | 2–6 hours |
| P8 | [Bedrock Token Costs Spiked](#p8) | Real-time alert | 1–2 hours |
| P9 | [Cross-Region Data Transfer Explosion](#p9) | CUR anomaly | 4–12 hours |
| P10 | [RDS Instance Running 24/7 for Dev](#p10) | Weekly waste scan | 1 hour |

---

## P1: AWS Bill Increased 40% This Month {#p1}

### Symptoms
- Finance team flags unexpectedly high invoice
- AWS Budgets alert fires
- Month-over-month cost comparison shows 40%+ increase

### Investigation Steps

```bash
# Step 1: Get month-over-month service breakdown (AWS CLI)
aws ce get-cost-and-usage \
  --time-period Start=2024-05-01,End=2024-06-01 \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --query 'ResultsByTime[*].Groups[*].{Service:Keys[0],Cost:Metrics.UnblendedCost.Amount}' \
  --output table

# Step 2: Identify what changed using Cost Explorer anomaly detection
aws ce get-anomalies \
  --anomaly-monitor-arn "arn:aws:ce::123456789012:anomalymonitor/MONITOR_ID" \
  --date-interval StartDate=2024-06-01,EndDate=2024-06-30 \
  --total-impact Filter="{\"NumericOperator\":\"GREATER_THAN\",\"StartValue\":100}"

# Step 3: Check for new resource creation (CloudTrail)
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=RunInstances \
  --start-time 2024-06-01T00:00:00Z \
  --end-time 2024-06-30T00:00:00Z \
  --query 'Events[*].{Time:EventTime,User:Username,Resources:Resources[*].ResourceName}' \
  --output table
```

```sql
-- Step 4: Athena CUR query — find the spike by day
SELECT
    DATE(line_item_usage_start_date) AS day,
    line_item_product_code AS service,
    SUM(line_item_unblended_cost) AS daily_cost,
    LAG(SUM(line_item_unblended_cost), 7) OVER (
        PARTITION BY line_item_product_code
        ORDER BY DATE(line_item_usage_start_date)
    ) AS cost_7d_ago,
    SUM(line_item_unblended_cost) - LAG(SUM(line_item_unblended_cost), 7) OVER (
        PARTITION BY line_item_product_code
        ORDER BY DATE(line_item_usage_start_date)
    ) AS delta_usd
FROM "athenacurcfn"."finops_cur_hourly"
WHERE year = '2024' AND month IN ('05', '06')
GROUP BY DATE(line_item_usage_start_date), line_item_product_code
HAVING delta_usd > 100
ORDER BY delta_usd DESC;
```

### Common Root Causes

| Root Cause | Investigation | Resolution |
|---|---|---|
| New large instance types launched | CloudTrail RunInstances | Terminate or rightsize |
| RI/SP expired | Cost Explorer RI report | Renew or convert to Compute SP |
| NAT Gateway traffic spike | VPC Flow Logs | Add VPC endpoints |
| S3 data transfer increase | S3 Storage Lens | Add CloudFront, review lifecycle |
| CloudWatch log ingestion | CW Log groups | Set retention, add filters |
| Cross-region replication | CUR transfer charges | Review replication scope |
| Forgotten dev environment | Resource inventory | Terminate and tag properly |

### Resolution Checklist
- [ ] Identify the service causing the spike
- [ ] Identify the account and team responsible
- [ ] Communicate to team with specific resource IDs
- [ ] Apply immediate remediation (stop/delete waste)
- [ ] Set up anomaly detection to catch this earlier next time
- [ ] Run post-mortem and document in case studies

---

## P2: EKS Cluster Cost Doubled Overnight {#p2}

### Symptoms
- CloudWatch alarm: EC2 spend > threshold
- Karpenter launched 50+ new nodes unexpectedly
- Namespace-level cost (OpenCost/Kubecost) shows spike

### Investigation

```bash
# Step 1: Check how many nodes Karpenter launched and when
kubectl logs -n karpenter -l app.kubernetes.io/name=karpenter \
  --since=24h | grep "launched node" | awk '{print $1, $2, $NF}' | sort

# Step 2: Find what caused scale-out — what pods couldn't schedule?
kubectl get events --all-namespaces \
  --field-selector reason=FailedScheduling \
  --sort-by='.lastTimestamp' | tail -50

# Step 3: Find deployments with no resource limits (top offenders)
kubectl get pods --all-namespaces -o json | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'{'Namespace':<30} {'Pod':<50} {'Container':<30} Issue')
print('-' * 120)
for pod in data['items']:
    ns = pod['metadata']['namespace']
    pod_name = pod['metadata']['name']
    for c in pod['spec']['containers']:
        resources = c.get('resources', {})
        issues = []
        if 'limits' not in resources:
            issues.append('NO LIMITS')
        if 'requests' not in resources:
            issues.append('NO REQUESTS')
        if issues:
            print(f'{ns:<30} {pod_name:<50} {c[\"name\"]:<30} {\" | \".join(issues)}')
"

# Step 4: Check for runaway HPA or replica count
kubectl get hpa --all-namespaces
kubectl get deployments --all-namespaces -o json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for d in data['items']:
    replicas = d.get('spec', {}).get('replicas', 0)
    if replicas > 20:
        print(f'{d[\"metadata\"][\"namespace\"]}/{d[\"metadata\"][\"name\"]}: {replicas} replicas')
" | sort -t: -k2 -n -r | head -20
```

### Resolution
1. Identify the deployment/job with abnormal replica count
2. Scale down to correct value: `kubectl scale deployment/NAME --replicas=CORRECT_COUNT -n NAMESPACE`
3. Apply LimitRange to the namespace to prevent recurrence
4. Drain and terminate orphaned Karpenter nodes

---

## P3: NAT Gateway Cost > EC2 Cost {#p3}

### Symptoms
- Cost Explorer shows NAT Gateway line item exceeding EC2
- Typically means 1TB+ of data being processed through NAT

### Investigation

```bash
# Step 1: Find which NAT GWs are processing the most traffic
python3 12-Network-Cost-Optimization/scripts/nat_gateway_analyzer.py

# Step 2: Enable VPC Flow Logs if not already enabled
aws ec2 create-flow-logs \
  --resource-type VPC \
  --resource-ids vpc-XXXXXXXX \
  --traffic-type ALL \
  --log-destination-type s3 \
  --log-destination arn:aws:s3:::your-flow-logs-bucket/vpc-flow-logs/

# Step 3: Athena query to find top internet destinations
# (Run after flow logs are in S3)
```

```sql
-- Find top destinations from NAT Gateway (what is the traffic going to?)
SELECT
    dstaddr AS destination_ip,
    COUNT(*) AS connection_count,
    SUM(bytes) / 1073741824.0 AS total_gb
FROM vpc_flow_logs
WHERE action = 'ACCEPT'
  AND dstaddr NOT IN (
    -- Exclude internal RFC1918 ranges
    SELECT dstaddr FROM vpc_flow_logs WHERE dstaddr LIKE '10.%'
    UNION SELECT dstaddr FROM vpc_flow_logs WHERE dstaddr LIKE '172.16.%'
    UNION SELECT dstaddr FROM vpc_flow_logs WHERE dstaddr LIKE '192.168.%'
  )
GROUP BY dstaddr
ORDER BY total_gb DESC
LIMIT 30;
```

### Resolution Priority
1. **S3 traffic → Gateway VPC Endpoint** (FREE, immediate savings)
2. **ECR/Docker Hub → ECR Interface Endpoint** (eliminates image pull costs)
3. **GitHub/npm/pip → CodeArtifact or NAT per-AZ consolidation**
4. **Consolidate NAT GWs** (if multiple AZs, each costs $32/mo even idle)

---

## P5: GPU Instance Left Running {#p5}

### Symptoms
- Anomaly detection alert for EC2 P-series instance
- Single p3.8xlarge = $12.24/hr = $8,935/month

### Investigation

```bash
# Find all GPU instances running
aws ec2 describe-instances \
  --filters "Name=instance-type,Values=p2.*,p3.*,p4.*,g4dn.*,g5.*,trn1.*" \
             "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].{
    ID:InstanceId,
    Type:InstanceType,
    LaunchTime:LaunchTime,
    Name:Tags[?Key==`Name`].Value|[0],
    Owner:Tags[?Key==`owner`].Value|[0]
  }' \
  --output table

# Check GPU utilization (requires CloudWatch GPU metrics or DCGM)
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name GPUUtilization \
  --dimensions Name=InstanceId,Value=i-XXXXXXXXXX \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 3600 \
  --statistics Average
```

### Immediate Resolution
```bash
# Stop (not terminate) if unsure about data
aws ec2 stop-instances --instance-ids i-XXXXXXXXXX

# Notify owner (get from tag)
OWNER=$(aws ec2 describe-instances --instance-ids i-XXXXXXXXXX \
  --query 'Reservations[0].Instances[0].Tags[?Key==`owner`].Value' --output text)
echo "Email $OWNER about stopped GPU instance"
```

### Prevention
```python
# Add this check to the idle_ec2_detector.py — special GPU alert
GPU_INSTANCE_FAMILIES = ['p2', 'p3', 'p4', 'g4dn', 'g4ad', 'g5', 'g5g', 'trn1', 'inf1', 'inf2']

def is_gpu_instance(instance_type: str) -> bool:
    family = instance_type.split('.')[0]
    return family in GPU_INSTANCE_FAMILIES

# For GPU instances, alert immediately (don't wait for 14-day lookback)
# Any GPU with CPU < 5% for 24h is almost certainly wasted
```

---

## P6: Lambda Recursive Invocation Explosion {#p6}

### Symptoms (CRITICAL — Can hit $10K+ in minutes)
- Lambda invocation count goes from 100/min to 1M/min
- Cost Explorer shows Lambda line item growing by second
- SQS queue depth growing exponentially

### Immediate Containment (< 5 minutes)

```bash
# IMMEDIATELY throttle the Lambda function
aws lambda put-function-concurrency \
  --function-name FUNCTION_NAME \
  --reserved-concurrent-executions 0

# This sets concurrency to 0 = no new invocations
# Already-running invocations will complete

# Check current invocations
aws lambda get-function-concurrency --function-name FUNCTION_NAME

# Purge the SQS queue if Lambda was triggered by SQS
aws sqs purge-queue --queue-url https://sqs.REGION.amazonaws.com/ACCOUNT/QUEUE_NAME
```

### Root Cause Investigation

```python
# scripts/lambda_recursive_detector.py
"""
Detects potentially recursive Lambda invocations.
Checks if a Lambda function is also an event source for itself.
AWS added native recursion detection in 2023, but this checks older patterns.
"""
import boto3

def detect_recursive_lambdas(region: str = 'us-east-1') -> list:
    lam = boto3.client('lambda', region_name=region)
    sqs = boto3.client('sqs', region_name=region)
    sns = boto3.client('sns', region_name=region)

    suspicious = []
    paginator = lam.get_paginator('list_functions')

    for page in paginator.paginate():
        for func in page['Functions']:
            func_name = func['FunctionName']

            # Check event source mappings
            esm_resp = lam.list_event_source_mappings(FunctionName=func_name)
            for esm in esm_resp.get('EventSourceMappings', []):
                source_arn = esm.get('EventSourceArn', '')

                # Check if the function writes to its own event source
                env_vars = func.get('Environment', {}).get('Variables', {})
                for key, value in env_vars.items():
                    if source_arn and (source_arn in value or func_name in value):
                        suspicious.append({
                            'function': func_name,
                            'event_source': source_arn,
                            'env_var': f"{key}={value}",
                            'risk': 'POTENTIAL RECURSIVE INVOCATION'
                        })

    return suspicious
```

### Resolution
1. Set reserved concurrency to 0 (immediate throttle)
2. Identify the circular trigger chain
3. Break the loop (remove SQS/SNS trigger, or fix the Lambda logic)
4. Re-enable concurrency gradually (10 → 50 → 100 → normal)
5. Enable AWS native recursion detection (2023 feature)

---

## P8: Bedrock Token Costs Spiked {#p8}

### Symptoms
- Bedrock line item on Cost Explorer > $1K/day unexpectedly
- CloudWatch shows InputTokenCount in billions
- Real-time alert from `bedrock_cost_guard.py`

### Investigation

```python
# Quick diagnosis
import boto3
from datetime import datetime, timedelta, timezone

cw = boto3.client('cloudwatch')
end = datetime.now(timezone.utc)
start = end - timedelta(hours=1)

for model in ['anthropic.claude-3-5-sonnet-20241022-v2:0', 'anthropic.claude-3-opus-20240229-v1:0']:
    resp = cw.get_metric_statistics(
        Namespace='AWS/Bedrock', MetricName='Invocations',
        Dimensions=[{'Name': 'ModelId', 'Value': model}],
        StartTime=start, EndTime=end, Period=300, Statistics=['Sum']
    )
    for dp in sorted(resp['Datapoints'], key=lambda x: x['Timestamp']):
        print(f"{dp['Timestamp']} | {model.split('.')[-1][:20]}: {dp['Sum']:.0f} invocations/5min")
```

### Resolution
1. Set `reserved-concurrent-executions = 0` on the calling Lambda
2. Identify which service/endpoint is calling Bedrock
3. Check for missing conversation windowing (P1 root cause)
4. Check for infinite retry loops in the calling code
5. Re-enable with conversation history limits enforced

---

*See all playbooks in the [full runbook library](../28-Case-Studies/README.md)*
