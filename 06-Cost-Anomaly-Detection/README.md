# 06 — Cost Anomaly Detection

> *Budgets tell you when a team overspends for the month. Anomaly Detection tells you when a developer accidentally creates an infinite loop in Lambda today.*

---

## 🚨 Why Budgets Aren't Enough

If your monthly budget is $100,000, and on Day 2 someone spins up a massive GPU cluster that costs $5,000/day, your AWS Budget won't alert you until Day 16 (when you hit $80k). By then, you've wasted $75,000.

**AWS Cost Anomaly Detection** uses Machine Learning to learn your normal spend patterns and alerts you within 24 hours of a spike, regardless of your total budget.

---

## 🏗️ Setting Up AWS Cost Anomaly Detection

You should configure multiple anomaly monitors to reduce noise and route alerts to the right teams.

### 1. The Global Monitor
- **Type:** AWS Services
- **Scope:** All services, all accounts
- **Alert Threshold:** > $100 expected impact
- **Destination:** `#finops-alerts` Slack channel

### 2. The Team Monitors
- **Type:** Linked Account (or Cost Allocation Tag)
- **Scope:** Specific team's account or tag
- **Alert Threshold:** > $50 expected impact
- **Destination:** `#team-backend-alerts` Slack channel

---

## 🛠️ Terraform Implementation

```hcl
# Create the monitor for the whole organization
resource "aws_ce_anomaly_monitor" "global_services" {
  name              = "Global-Service-Monitor"
  monitor_type      = "DIMENSIONAL"
  monitor_dimension = "SERVICE"
}

# Create the alert subscription
resource "aws_ce_anomaly_subscription" "finops_slack" {
  name             = "FinOps-Slack-Alerts"
  frequency        = "IMMEDIATE" # Options: DAILY, IMMEDIATE, WEEKLY
  monitor_arn_list = [aws_ce_anomaly_monitor.global_services.arn]

  subscriber {
    type    = "SNS"
    address = aws_sns_topic.cost_alerts_topic.arn
  }

  threshold_expression {
    dimension {
      key            = "ANOMALY_TOTAL_IMPACT_ABSOLUTE"
      match_options  = ["GREATER_THAN_OR_EQUAL"]
      values         = ["100"] # Alert if spike is > $100
    }
  }
}
```

---

## 🔎 Investigating an Anomaly

When an anomaly fires, follow the **Playbooks** (see [27-Playbooks](../27-Playbooks/README.md)). 

Basic investigation steps:
1. Identify the Service (e.g., `AmazonEC2`).
2. Identify the Usage Type in Cost Explorer (e.g., `DataTransfer-Out-Bytes`).
3. Identify the Resource ID.
4. Check CloudTrail for `RunInstances`, `CreateBucket`, or configuration changes in the 24 hours prior.
5. Remediate.
