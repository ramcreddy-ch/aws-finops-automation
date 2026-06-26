# 04 — Cost Allocation & Chargeback

> *Without accurate cost allocation, FinOps is just playing whack-a-mole with cloud bills. True FinOps requires a culture of accountability where teams own their cloud spend like they own their uptime.*

---

## 🎯 Showback vs Chargeback

- **Showback:** Providing teams with visibility into their costs (e.g., "Team A, you spent $50k this month"). This builds awareness without financial friction.
- **Chargeback:** Actually deducting the cloud spend from the team's operating budget. This drives real behavioral change.

*Rule: Always run Showback for 3-6 months before enabling Chargeback to resolve tagging gaps and build trust.*

---

## 🏗️ The Allocation Strategy

### 1. Account-Based Allocation (The Easy Way)
The easiest way to allocate costs is to give every team/product their own AWS accounts.
- `Acme-Payments-Prod`
- `Acme-Payments-Dev`
**Pros:** 100% accurate allocation at the AWS bill level. No tagging required for basic chargeback.
**Cons:** Account sprawl, complex networking.

### 2. Tag-Based Allocation (The Hard Way)
If multiple teams share an account, you must rely on tags.
**Pros:** Fewer accounts to manage.
**Cons:** Requires perfect tagging discipline. Untagged resources become "orphan costs" that IT usually has to eat.

### 3. The Hybrid Approach (Enterprise Standard)
Use Account-Based allocation for environments (Prod vs Dev) and products, but use Tag-Based allocation within those accounts to separate features or components.

---

## 🔪 Slicing Shared Costs

How do you chargeback a Transit Gateway, a shared Kubernetes cluster, or Enterprise Support?

**Method 1: Proportional Split**
If Team A uses 60% of total compute, they pay 60% of the shared network/support costs.

**Method 2: Fixed Tax**
Apply a flat 15% "Platform Tax" to all team bills to cover shared services.

**Method 3: Usage-Based (Advanced)**
For EKS, allocate costs based on namespace CPU/Memory requests using OpenCost or Kubecost.

---

## 📊 CUR Query: Finding Untagged Waste

When running chargeback, you must find out who owns the untagged resources.

```sql
-- Find all resources costing > $10/month that lack a 'Team' tag
SELECT 
    line_item_usage_account_id AS account,
    line_item_product_code AS service,
    line_item_resource_id AS resource,
    SUM(line_item_unblended_cost) AS cost
FROM "athenacurcfn"."finops_cur_hourly"
WHERE year = '2024' AND month = '06'
  AND (resource_tags_user_team IS NULL OR resource_tags_user_team = '')
  AND line_item_unblended_cost > 10
GROUP BY 1, 2, 3
ORDER BY cost DESC;
```
