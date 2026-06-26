# 05 — AWS Budgets & Forecasting

> *AWS Budgets are your first line of defense against bill shock. If you wait for the monthly invoice to realize you overspent, you have already failed.*

---

## 🛡️ AWS Budgets Architecture

An enterprise should not have just one master budget. You need a hierarchy of budgets mapped to your organization.

1. **The Global Budget:** Set at 100% of projected monthly spend. Alerts the VP/Director level.
2. **Account Budgets:** Set on every individual AWS account.
3. **Team/Tag Budgets:** Set based on the `Team` or `CostCenter` tag.

---

## 🔔 Best Practices for Alerts

**Do not alert at 100%.** By the time you hit 100%, the month isn't over, and you are guaranteed to overspend.

**Recommended Alert Thresholds:**
- **Forecasted to exceed 100%:** Alert FinOps via Slack.
- **Actuals > 80%:** Alert the Engineering Manager (usually happens around day 24).
- **Actuals > 100%:** Alert Director/VP and trigger automated cost containment (e.g., stop dev instances).

---

## 🏗️ Terraform: Automated Budget Creation

Use Terraform to automatically create a budget whenever a new AWS account or team is onboarded.

```hcl
resource "aws_budgets_budget" "team_budget" {
  name              = "${var.team_name}-monthly-budget"
  budget_type       = "COST"
  limit_amount      = var.monthly_budget_usd
  limit_unit        = "USD"
  time_unit         = "MONTHLY"
  time_period_start = "2024-01-01_00:00"

  cost_filters {
    name = "TagKeyValue"
    values = [
      "user:Team$${var.team_name}"
    ]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.team_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_sns_topic_arns  = [aws_sns_topic.finops_alerts.arn]
  }
}
```

---

## 🔮 Forecasting

Forecasting cloud spend is notoriously difficult due to variable usage.
- **Run Rate:** (Spend so far this month / days elapsed) * days in month.
- **Seasonality:** Does your app see massive spikes on Black Friday?
- **Organic Growth:** Factor in user growth (e.g., +5% compute month-over-month).
- **New Projects:** Add manual bumps for new services going live.

*FinOps Pro-Tip: AWS Cost Explorer forecasting is simple linear regression. For accurate enterprise forecasting, export CUR data to SageMaker and train an ML model on historical trends and business metrics.*
