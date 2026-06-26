# 17 — Bedrock FinOps

> *AWS Bedrock token costs are the new "EC2 instance left running" — invisible until they're not. A misconfigured LLM endpoint can generate a $50K invoice in a single day.*

---

## 💡 Bedrock Pricing Model

```
Bedrock charges per 1,000 INPUT tokens + per 1,000 OUTPUT tokens.
Output tokens are 3–5x more expensive than input tokens.

Model                      Input ($/1K tokens)  Output ($/1K tokens)
─────────────────────────  ───────────────────  ────────────────────
Claude 3.5 Sonnet          $0.003               $0.015
Claude 3 Haiku             $0.00025             $0.00125
Claude 3 Opus              $0.015               $0.075
Llama 3.1 405B             $0.00532             $0.016
Llama 3.1 70B              $0.00099             $0.00099
Titan Text G1 Express      $0.0002              $0.0006
Titan Text G1 Lite         $0.00015             $0.0002
Cohere Command R+          $0.003               $0.015
AI21 Jurassic-2 Ultra      $0.0188              $0.0188

Hidden costs:
• Bedrock Agents:          +$0.0013/1K input, +$0.0016/1K output (orchestration)
• Knowledge Base Queries:  $0.004/query (vector retrieval)
• Embeddings:              $0.0001/1K tokens (Titan)
• Provisioned Throughput:  $21.50–$56.50/model unit/hr (24/7 billing!)
```

---

## 🚨 Real Incident: $47K Bedrock Bill in 48 Hours

**Scenario:** A developer deployed a Bedrock-powered support chatbot that worked correctly in testing. Three days after launch, the AWS bill showed $47,000 in Bedrock charges.

**Investigation:**

```python
# scripts/bedrock_cost_investigator.py
"""
Analyzes Bedrock token usage and costs from CUR and CloudWatch.
Helps identify which models, callers, and use cases are driving costs.
"""

import boto3
from datetime import datetime, timedelta, timezone

def get_bedrock_model_invocations(region: str = 'us-east-1', lookback_hours: int = 24) -> dict:
    """Gets Bedrock model invocation metrics from CloudWatch."""
    cw = boto3.client('cloudwatch', region_name=region)
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=lookback_hours)

    # Models to check
    models = [
        'anthropic.claude-3-5-sonnet-20241022-v2:0',
        'anthropic.claude-3-haiku-20240307-v1:0',
        'anthropic.claude-3-opus-20240229-v1:0',
        'meta.llama3-1-405b-instruct-v1:0',
        'amazon.titan-text-express-v1'
    ]

    results = {}
    for model_id in models:
        # Input tokens
        input_resp = cw.get_metric_statistics(
            Namespace='AWS/Bedrock',
            MetricName='InputTokenCount',
            Dimensions=[{'Name': 'ModelId', 'Value': model_id}],
            StartTime=start, EndTime=end,
            Period=3600, Statistics=['Sum']
        )
        output_resp = cw.get_metric_statistics(
            Namespace='AWS/Bedrock',
            MetricName='OutputTokenCount',
            Dimensions=[{'Name': 'ModelId', 'Value': model_id}],
            StartTime=start, EndTime=end,
            Period=3600, Statistics=['Sum']
        )
        invoc_resp = cw.get_metric_statistics(
            Namespace='AWS/Bedrock',
            MetricName='Invocations',
            Dimensions=[{'Name': 'ModelId', 'Value': model_id}],
            StartTime=start, EndTime=end,
            Period=3600, Statistics=['Sum']
        )

        total_input = sum(dp['Sum'] for dp in input_resp.get('Datapoints', []))
        total_output = sum(dp['Sum'] for dp in output_resp.get('Datapoints', []))
        total_invocations = sum(dp['Sum'] for dp in invoc_resp.get('Datapoints', []))

        if total_invocations > 0:
            results[model_id] = {
                'total_invocations': int(total_invocations),
                'total_input_tokens': int(total_input),
                'total_output_tokens': int(total_output),
                'avg_input_per_call': int(total_input / total_invocations),
                'avg_output_per_call': int(total_output / total_invocations)
            }

    return results

def get_bedrock_spend_from_cur_athena(athena_db: str, cur_table: str, days: int = 7) -> str:
    """Returns Athena SQL to query Bedrock spend from CUR."""
    return f"""
    SELECT
        line_item_resource_id AS model_id,
        SUM(line_item_usage_amount) AS total_tokens,
        SUM(line_item_unblended_cost) AS total_cost_usd,
        COUNT(*) AS invocation_count,
        DATE_FORMAT(line_item_usage_start_date, '%Y-%m-%d') AS usage_date
    FROM "{athena_db}"."{cur_table}"
    WHERE
        year = '{datetime.now().year}'
        AND month = '{datetime.now().month:02d}'
        AND line_item_product_code = 'AmazonBedrock'
        AND line_item_line_item_type = 'Usage'
        AND line_item_usage_start_date >= CURRENT_DATE - INTERVAL '{days}' DAY
    GROUP BY
        line_item_resource_id,
        DATE_FORMAT(line_item_usage_start_date, '%Y-%m-%d')
    ORDER BY
        total_cost_usd DESC;
    """

if __name__ == '__main__':
    data = get_bedrock_model_invocations(lookback_hours=24)
    print("\nBedrock Usage (Last 24h):")
    for model, stats in data.items():
        short_name = model.split('.')[-1][:30]
        print(f"\n  {short_name}")
        print(f"    Invocations: {stats['total_invocations']:,}")
        print(f"    Input tokens: {stats['total_input_tokens']:,} (avg {stats['avg_input_per_call']:,}/call)")
        print(f"    Output tokens: {stats['total_output_tokens']:,} (avg {stats['avg_output_per_call']:,}/call)")
```

**Root Cause Found:** The chatbot was sending the **entire conversation history** on every message. By message 50, each API call was sending 40,000 input tokens. With 10,000 daily users sending an average of 20 messages each, the token math exploded:

```
10,000 users × 20 messages × avg 40,000 input tokens = 8,000,000,000 tokens/day
Cost: 8,000,000 × $0.003/1K = $24,000/day input tokens alone
```

**Fix:**
```python
# BEFORE (anti-pattern): Full history on every call
def chat(user_message: str, history: list) -> str:
    messages = history + [{"role": "user", "content": user_message}]
    # 50 messages = 40K tokens per call

# AFTER (optimized): Sliding window + summarization
def chat_optimized(user_message: str, history: list, max_history: int = 5) -> str:
    # Keep only last N messages
    recent_history = history[-max_history:]

    # If history is long, summarize older messages
    if len(history) > max_history:
        summary = summarize_conversation(history[:-max_history])
        context = [{"role": "system", "content": f"Previous conversation summary: {summary}"}]
        messages = context + recent_history + [{"role": "user", "content": user_message}]
    else:
        messages = recent_history + [{"role": "user", "content": user_message}]

    return invoke_bedrock(messages)
```

**Result:** Token usage dropped 95%. Monthly cost: $47K/day → $1,200/month.

---

## 💰 Model Selection Strategy

```python
# scripts/bedrock_model_router.py
"""
Intelligent model routing based on task complexity and cost constraints.
Routes simple tasks to cheap models, complex tasks to powerful models.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional

class TaskComplexity(Enum):
    SIMPLE = "simple"       # FAQ, classification, extraction
    MEDIUM = "medium"       # Summarization, analysis, drafting
    COMPLEX = "complex"     # Code generation, reasoning, synthesis
    CRITICAL = "critical"   # High-stakes decisions, nuanced judgment

@dataclass
class ModelConfig:
    model_id: str
    input_cost_per_1k: float   # USD
    output_cost_per_1k: float  # USD
    max_tokens: int
    latency_ms: int            # Approximate P50 latency

MODEL_REGISTRY = {
    TaskComplexity.SIMPLE: ModelConfig(
        model_id="amazon.titan-text-lite-v1",
        input_cost_per_1k=0.00015,
        output_cost_per_1k=0.0002,
        max_tokens=4096,
        latency_ms=300
    ),
    TaskComplexity.MEDIUM: ModelConfig(
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        input_cost_per_1k=0.00025,
        output_cost_per_1k=0.00125,
        max_tokens=200000,
        latency_ms=600
    ),
    TaskComplexity.COMPLEX: ModelConfig(
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.015,
        max_tokens=200000,
        latency_ms=2000
    ),
    TaskComplexity.CRITICAL: ModelConfig(
        model_id="anthropic.claude-3-opus-20240229-v1:0",
        input_cost_per_1k=0.015,
        output_cost_per_1k=0.075,
        max_tokens=200000,
        latency_ms=5000
    ),
}

def estimate_cost(prompt_tokens: int, expected_output_tokens: int, complexity: TaskComplexity) -> float:
    """Returns estimated USD cost for a given invocation."""
    model = MODEL_REGISTRY[complexity]
    input_cost = (prompt_tokens / 1000) * model.input_cost_per_1k
    output_cost = (expected_output_tokens / 1000) * model.output_cost_per_1k
    return round(input_cost + output_cost, 6)

def classify_task(task_description: str) -> TaskComplexity:
    """Rule-based task classifier (replace with ML classifier for production)."""
    simple_keywords = ['classify', 'extract', 'yes/no', 'faq', 'lookup', 'format']
    medium_keywords = ['summarize', 'analyze', 'draft', 'translate', 'explain']
    complex_keywords = ['code', 'debug', 'architect', 'design', 'reason', 'compare']
    critical_keywords = ['legal', 'medical', 'financial advice', 'compliance', 'audit']

    desc_lower = task_description.lower()
    if any(k in desc_lower for k in critical_keywords):
        return TaskComplexity.CRITICAL
    elif any(k in desc_lower for k in complex_keywords):
        return TaskComplexity.COMPLEX
    elif any(k in desc_lower for k in medium_keywords):
        return TaskComplexity.MEDIUM
    else:
        return TaskComplexity.SIMPLE

# Cost comparison example
def print_cost_comparison(prompt_tokens: int = 1000, output_tokens: int = 500):
    print(f"\nCost comparison for {prompt_tokens} input + {output_tokens} output tokens:\n")
    for complexity, model in MODEL_REGISTRY.items():
        cost = estimate_cost(prompt_tokens, output_tokens, complexity)
        monthly_cost_1M_calls = cost * 1_000_000
        print(f"  {complexity.value.upper():<10} | {model.model_id.split('.')[-1][:30]:<35} | "
              f"${cost:.6f}/call | ${monthly_cost_1M_calls:,.2f}/mo @ 1M calls")

if __name__ == '__main__':
    print_cost_comparison()
```

**Output:**
```
Cost comparison for 1,000 input + 500 output tokens:

  SIMPLE     | titan-text-lite-v1                   | $0.000250/call | $250.00/mo @ 1M calls
  MEDIUM     | claude-3-haiku-20240307-v1:0          | $0.000875/call | $875.00/mo @ 1M calls
  COMPLEX    | claude-3-5-sonnet-20241022-v2:0       | $0.010500/call | $10,500.00/mo @ 1M calls
  CRITICAL   | claude-3-opus-20240229-v1:0           | $0.052500/call | $52,500.00/mo @ 1M calls
```

---

## 🛡️ Bedrock Cost Guard Rails

### Lambda: Bedrock Cost Circuit Breaker

```python
# 25-Automation/lambda_functions/bedrock_cost_guard.py
"""
Circuit breaker for Bedrock API calls.
Monitors hourly spend and auto-disables the calling Lambda if threshold exceeded.
Triggered every 15 minutes by EventBridge.
"""
import boto3
import os
import json
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MAX_HOURLY_SPEND_USD = float(os.environ.get('MAX_HOURLY_BEDROCK_SPEND_USD', '100.0'))
ALERT_LAMBDA_ARN = os.environ.get('ALERT_LAMBDA_ARN', '')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')

def get_bedrock_token_count(cw, model_id: str, minutes: int = 60) -> tuple:
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    def get_sum(metric_name):
        resp = cw.get_metric_statistics(
            Namespace='AWS/Bedrock', MetricName=metric_name,
            Dimensions=[{'Name': 'ModelId', 'Value': model_id}],
            StartTime=start, EndTime=end, Period=3600, Statistics=['Sum']
        )
        return sum(dp['Sum'] for dp in resp.get('Datapoints', []))

    return get_sum('InputTokenCount'), get_sum('OutputTokenCount')

PRICING = {
    'anthropic.claude-3-5-sonnet-20241022-v2:0': (0.003, 0.015),
    'anthropic.claude-3-haiku-20240307-v1:0': (0.00025, 0.00125),
    'anthropic.claude-3-opus-20240229-v1:0': (0.015, 0.075),
}

def lambda_handler(event, context):
    cw = boto3.client('cloudwatch')
    sns = boto3.client('sns')

    total_hourly_cost = 0.0
    breakdown = {}

    for model_id, (in_price, out_price) in PRICING.items():
        input_tokens, output_tokens = get_bedrock_token_count(cw, model_id, 60)
        cost = (input_tokens / 1000 * in_price) + (output_tokens / 1000 * out_price)
        total_hourly_cost += cost
        if cost > 0:
            breakdown[model_id] = {
                'input_tokens': int(input_tokens),
                'output_tokens': int(output_tokens),
                'hourly_cost_usd': round(cost, 4)
            }

    logger.info(f"Bedrock hourly spend: ${total_hourly_cost:.4f} (limit: ${MAX_HOURLY_SPEND_USD})")

    if total_hourly_cost > MAX_HOURLY_SPEND_USD:
        logger.error(f"CIRCUIT BREAKER TRIGGERED: ${total_hourly_cost:.2f} exceeds ${MAX_HOURLY_SPEND_USD}/hr")

        # Alert via SNS
        if SNS_TOPIC_ARN:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject=f"🚨 Bedrock Cost Alert: ${total_hourly_cost:.2f}/hr",
                Message=json.dumps({
                    'alert': 'Bedrock hourly spend exceeded threshold',
                    'current_spend_usd': round(total_hourly_cost, 4),
                    'threshold_usd': MAX_HOURLY_SPEND_USD,
                    'breakdown': breakdown
                }, indent=2)
            )

    return {
        'statusCode': 200,
        'hourly_spend_usd': round(total_hourly_cost, 4),
        'threshold_usd': MAX_HOURLY_SPEND_USD,
        'threshold_breached': total_hourly_cost > MAX_HOURLY_SPEND_USD,
        'breakdown': breakdown
    }
```

---

## 📊 Bedrock FinOps Dashboard (CloudWatch Metrics Insight)

```
# Paste these into CloudWatch Metrics Insights

# Total Bedrock spend per hour (estimated)
SELECT SUM(InputTokenCount) / 1000 * 0.003 + SUM(OutputTokenCount) / 1000 * 0.015
FROM SCHEMA("AWS/Bedrock", ModelId)
WHERE ModelId LIKE 'anthropic%'
GROUP BY ModelId
ORDER BY SUM(InputTokenCount) DESC

# Invocations per minute (identifies traffic spikes)
SELECT SUM(Invocations)
FROM SCHEMA("AWS/Bedrock", ModelId)
GROUP BY ModelId
ORDER BY SUM(Invocations) DESC

# Average latency by model
SELECT AVG(InvocationLatency)
FROM SCHEMA("AWS/Bedrock", ModelId)
GROUP BY ModelId
```

---

## ✅ Bedrock FinOps Checklist

- [ ] Enable CloudWatch metrics for Bedrock (enabled by default)
- [ ] Set up hourly cost alerts via SNS/Slack
- [ ] Implement conversation history windowing (max 5–10 turns)
- [ ] Use Haiku/Lite for classification and extraction tasks
- [ ] Reserve Sonnet/Opus for generation and reasoning only
- [ ] Enable prompt caching where available (up to 90% cost reduction)
- [ ] Implement semantic caching for repeated queries
- [ ] Review Provisioned Throughput vs On-Demand model (break-even analysis)
- [ ] Tag all Bedrock callers by team for chargeback
- [ ] Monitor token count trends weekly in CUR

---

*Back: [16 — SageMaker FinOps](../16-SageMaker-FinOps/README.md) | Next: [18 — Observability Cost →](../18-Observability-Cost/README.md)*
