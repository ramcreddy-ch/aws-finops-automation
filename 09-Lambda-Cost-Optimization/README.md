# 09 — Lambda Cost Optimization

> *Lambda is often perceived as "cheap because it's serverless." However, at enterprise scale (billions of invocations), over-provisioned memory, long cold starts, and architectural anti-patterns can make it more expensive than EC2.*

---

## 💡 Lambda Cost Drivers

Lambda pricing has two dimensions:
1. **Requests:** $0.20 per 1 million requests (generally negligible)
2. **Compute (GB-seconds):** $0.0000166667 for every GB-second

**The Trap:** Compute duration is billed in 1ms increments, multiplied by the allocated memory.
**If you allocate 2GB of memory but only use 128MB, you are paying 16x more than necessary.**

---

## 🛠️ The Power of PowerTuning

The relationship between memory and execution time is non-linear. Because AWS allocates CPU power proportionally to memory, **increasing memory can sometimes decrease cost** because the function runs much faster.

### AWS Lambda Power Tuning Integration

```bash
# Deploy the AWS Lambda Power Tuning state machine via SAM
sam deploy --guided \
  --template-file template.yaml \
  --stack-name lambda-power-tuning

# Execute it via CLI for a specific function
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:REGION:ACCOUNT:stateMachine:powerTuningStateMachine \
  --input '{
    "lambdaARN": "arn:aws:lambda:REGION:ACCOUNT:function:MyFunction",
    "powerValues": [128, 256, 512, 1024, 2048, 3072],
    "num": 50,
    "payload": {"test": "data"},
    "parallelInvocation": true,
    "strategy": "cost"
  }'
```
*Result: An execution graph showing the exact optimal memory size for lowest cost vs lowest latency.*

---

## 🤖 Lambda Rightsizing Automation

```python
# 25-Automation/lambda_functions/lambda_rightsizing.py
"""
Scans all Lambda functions to identify memory over-provisioning.
Uses CloudWatch Lambda Insights to find functions using < 50% of allocated memory.
"""
import boto3
import json
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_lambda_memory_usage(cw, function_name: str, lookback_days: int = 14) -> float:
    """Gets the max memory used by a Lambda function in the lookback period."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)

    try:
        resp = cw.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName='MemoryUtilization', # Requires Lambda Insights enabled
            Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
            StartTime=start, EndTime=end,
            Period=86400, Statistics=['Maximum']
        )
        datapoints = resp.get('Datapoints', [])
        if not datapoints:
            return 0.0
        return max(dp['Maximum'] for dp in datapoints)
    except Exception as e:
        logger.error(f"Failed to get metrics for {function_name}: {e}")
        return 0.0

def lambda_handler(event, context):
    lam = boto3.client('lambda', region_name='us-east-1')
    cw = boto3.client('cloudwatch', region_name='us-east-1')

    recommendations = []
    paginator = lam.get_paginator('list_functions')

    for page in paginator.paginate():
        for func in page['Functions']:
            name = func['FunctionName']
            allocated_mb = func['MemorySize']

            # Skip small functions
            if allocated_mb <= 256:
                continue

            max_used_pct = get_lambda_memory_usage(cw, name)

            if 0 < max_used_pct < 40.0:
                recommended_mb = int(allocated_mb * (max_used_pct / 100) * 1.5) # 50% buffer
                # Round to nearest standard size (128, 256, 512, 1024...)
                sizes = [128, 256, 512, 1024, 1536, 2048, 3072, 4096, 5120, 6144, 7168, 8192, 9216, 10240]
                recommended_mb = min([s for s in sizes if s >= recommended_mb], default=allocated_mb)

                if recommended_mb < allocated_mb:
                    savings_pct = (1 - (recommended_mb / allocated_mb)) * 100
                    recommendations.append({
                        'function': name,
                        'allocated_mb': allocated_mb,
                        'max_used_pct': round(max_used_pct, 1),
                        'recommended_mb': recommended_mb,
                        'potential_savings_pct': round(savings_pct, 1)
                    })

    recommendations.sort(key=lambda x: x['potential_savings_pct'], reverse=True)

    print(f"\nFound {len(recommendations)} over-provisioned Lambda functions:\n")
    for r in recommendations[:20]:
        print(f"{r['function'][:40]:<42} | Allocated: {r['allocated_mb']}MB | "
              f"Peak Usage: {r['max_used_pct']}% | "
              f"Recommend: {r['recommended_mb']}MB (Save {r['potential_savings_pct']}%)")

    return recommendations
```

---

## 🚨 Anti-Patterns & Solutions

### 1. The Wait-and-Pay Pattern
**Anti-pattern:** Lambda calling another API (or another Lambda) and sitting idle waiting for a response. You are paying for the compute time while the function sleeps.
**Fix:** Use Step Functions Direct Integrations or SQS. Let Step Functions handle the wait state (you don't pay for wait time in standard workflows).

### 2. Large Deployment Packages
**Anti-pattern:** Including massive SDKs (like full `boto3` when you only need `s3`) or ML models in the deployment package. Increases cold start time significantly.
**Fix:** Use Lambda Layers, minimal SDKs (e.g., `boto3-minimal`), or EFS for large ML models.

### 3. Provisioned Concurrency Abuse
**Anti-pattern:** Setting high Provisioned Concurrency (PC) on functions with spiky traffic. PC costs $0.015/GB-hour just to keep it warm, even if unused.
**Fix:** Use PC Auto Scaling. Scale it down to 0 at night if the app is B2B.

---

## ✅ Lambda Optimization Checklist
- [ ] Run AWS Compute Optimizer for Lambda (free) every quarter
- [ ] Integrate Lambda Power Tuning into CI/CD for critical paths
- [ ] Identify functions with >3s average duration and analyze for API wait times
- [ ] Migrate x86 functions to ARM64 (Graviton2) — immediate **20% cost reduction**
- [ ] Check CloudWatch Logs for recursive invocation patterns
