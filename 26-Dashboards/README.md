# 26 — Dashboards & Visibility

> *If engineering teams can't see their costs where they already work, they won't optimize. Sending spreadsheets via email is a Level 1 FinOps anti-pattern.*

---

## 📊 Dashboard Personas

You need three different dashboards for three different audiences:

### 1. The Executive Dashboard (QuickSight)
- **Audience:** CFO, VP of Engineering, CTO.
- **Metrics:** Total Monthly Spend, Forecast vs Budget, Effective Savings Rate (ESR), RI/SP Coverage %, Unit Cost Trends.
- **Focus:** Are we spending efficiently at a macro level?

### 2. The Engineering Manager Dashboard (QuickSight / Grafana)
- **Audience:** Directors, Engineering Managers.
- **Metrics:** Spend by Team (Chargeback), Top 5 Cost Drivers, MoM Cost Anomalies, Waste Metrics (Idle resources).
- **Focus:** Is my team staying within budget? Where is our waste?

### 3. The Developer Dashboard (Grafana / Datadog)
- **Audience:** Software Engineers, DevOps.
- **Metrics:** Cost per API call, EKS pod cost, Lambda duration costs, NAT Gateway data transfer per service.
- **Focus:** How does the code I shipped yesterday impact our cloud bill today?

---

## 🛠️ AWS QuickSight (The Enterprise Standard)

AWS QuickSight is the native BI tool of choice for FinOps because it integrates seamlessly with the Cost and Usage Report (CUR) via Amazon Athena.

**Architecture:**
CUR (S3) ➡️ Athena ➡️ QuickSight SPICE (In-memory engine) ➡️ Dashboards

**QuickSight Cost Intelligence Dashboard (CID):**
AWS provides a free, pre-built suite of QuickSight dashboards called the Cloud Intelligence Dashboards (CID). Do not build from scratch; deploy the CID framework via CloudFormation. It provides 100+ pre-built visuals for FinOps.

---

## 📈 Grafana (The Developer Standard)

Developers do not want to log into QuickSight. They want cost data next to their latency and error metrics in Grafana.

**Integration:**
1. Install the Athena data source plugin in Grafana.
2. Query the CUR directly from Grafana.
3. Add a "Cost" row to every standard service dashboard.

```sql
-- Grafana Athena Query Example: Daily cost for a specific microservice
SELECT 
  $__timeGroup(line_item_usage_start_date, '1d') AS time,
  SUM(line_item_unblended_cost) AS cost
FROM "athenacurcfn"."finops_cur_hourly"
WHERE resource_tags_user_service = 'payment-api'
  AND $__timeFilter(line_item_usage_start_date)
GROUP BY 1
ORDER BY 1
```

---

## ✅ Dashboard Checklist
- [ ] Deploy the AWS Cloud Intelligence Dashboards (CID) framework.
- [ ] Implement Row-Level Security (RLS) in QuickSight so teams only see their own data.
- [ ] Embed cost panels into your primary engineering observability tool (Grafana/Datadog).
- [ ] Ensure dashboards refresh at least daily (CUR updates 3x a day).
