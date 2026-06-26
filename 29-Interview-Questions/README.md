# 29 — AWS FinOps Interview Questions

> *100+ scenario-based, architecture-level, and leadership-focused FinOps interview questions with expert answers. Designed for Principal FinOps Architect, Cloud Economist, and Platform Engineering leadership roles.*

---

## 🎯 Question Categories

| Domain | Questions | Difficulty |
|---|---|---|
| [FinOps Foundations](#foundations) | Q1–Q10 | ⭐⭐ |
| [AWS Billing & Cost Management](#billing) | Q11–Q25 | ⭐⭐⭐ |
| [Compute Optimization](#compute) | Q26–Q40 | ⭐⭐⭐ |
| [Kubernetes FinOps](#k8s) | Q41–Q55 | ⭐⭐⭐⭐ |
| [AI/ML & GPU Costs](#ai) | Q56–Q65 | ⭐⭐⭐⭐ |
| [Enterprise Governance](#enterprise) | Q66–Q75 | ⭐⭐⭐⭐ |
| [Cloud Economics](#economics) | Q76–Q85 | ⭐⭐⭐⭐⭐ |
| [Architecture Scenarios](#architecture) | Q86–Q100 | ⭐⭐⭐⭐⭐ |

---

## FinOps Foundations {#foundations}

### Q1: What is the difference between FinOps, Cloud Cost Management, and Cloud Economics?

**Expert Answer:**

These are often used interchangeably but have distinct meanings:

- **Cloud Cost Management** is *tactical*: tools and processes to track, report, and reduce cloud spending. It's reactive — you look at the bill and find waste.

- **FinOps** is *cultural and operational*: it's the practice of bringing financial accountability to the variable-cost model of cloud. It involves people, process, and technology. The key distinction is that FinOps aligns *business value* with cloud spend, not just cost reduction. You might deliberately spend more if it accelerates time-to-market.

- **Cloud Economics** is *strategic*: it's about business model design around cloud costs. Unit economics, pricing models, how cloud spend maps to product revenue, build vs buy decisions, and the financial ROI of cloud adoption vs on-premises.

**Real production example:** At a financial services firm, Cloud Cost Management said "shut down the dev cluster overnight." FinOps said "let's calculate the developer productivity cost of slow build environments vs the savings." Cloud Economics said "should we own our own hardware for the batch workloads that run 80% of the time?"

**Common Mistake:** Treating FinOps as a cost-cutting exercise. A FinOps team that says "we saved $2M" is doing it wrong. A FinOps team that says "we enabled the product team to ship 40% faster while keeping cost-per-transaction below $0.001" is doing it right.

---

### Q2: Describe the FinOps maturity model. Where is your current organization?

**Expert Answer:**

The FinOps Foundation defines three phases — Crawl, Walk, Run — but in practice I use a 5-level model:

```
Level 1 — Awareness: Someone looks at the AWS bill monthly. No allocation.
Level 2 — Visibility: Teams can see their own costs. Basic tagging. Cost Explorer.
Level 3 — Accountability: Teams own their budgets. Chargeback/showback exists.
Level 4 — Optimization: Automated waste detection. RI strategy. Rightsizing cadence.
Level 5 — Predictive: ML-based anomaly detection. Unit economics KPIs. Cost in CI/CD.
```

Most enterprises with 2–5 years of cloud are at Level 2–3. The gap between Level 3 and 4 is usually automation maturity. The gap between 4 and 5 is cultural — engineers need to own cost as a first-class engineering metric.

**How to assess your level:**
- Can any engineer look up their service's cost today without asking FinOps? (Level 2 gate)
- Is there a chargeback or showback report that finance trusts? (Level 3 gate)
- Is there automated remediation for idle resources? (Level 4 gate)
- Does every infrastructure PR include a cost estimate? (Level 5 gate)

---

### Q3: How do you build a FinOps culture in an engineering organization that sees cost as Finance's problem?

**Expert Answer:**

This is a leadership challenge more than a technical one. My approach has three phases:

**Phase 1: Make cost visible and personal**
- Build team-level dashboards showing their service's daily spend
- Put cost metrics in engineering all-hands alongside latency and error rate
- Never send a cost report to a manager. Send it directly to the engineer who wrote the code.

**Phase 2: Make the connection to revenue**
- Calculate and publish unit economics: cost per API call, cost per active user, cost per transaction
- Engineers care about performance; show them that cost and performance are often correlated
- "Your Lambda is spending $3K/month because it's over-allocating 1.5GB of memory when it uses 200MB. Here's the PR to fix it."

**Phase 3: Build guardrails that teach, not block**
- Add `infracost` to PRs: "This change will add $340/month in infrastructure costs"
- Alert on cost anomalies directly to the team Slack channel
- Celebrate cost wins: "Team X reduced their S3 costs by $12K/month by implementing Intelligent Tiering"

**What doesn't work:**
- Top-down mandates ("you must reduce costs by 20%") without tooling
- Blocking deployments for cost reasons (creates adversarial culture)
- Monthly reports that nobody reads

---

### Q4: What is the difference between chargeback and showback? Which would you recommend and when?

**Expert Answer:**

| | Showback | Chargeback |
|---|---|---|
| **Definition** | Teams *see* their costs but don't *pay* from their budget | Teams' P&L or cost center is actually debited |
| **When Used** | Early FinOps maturity, building culture | Mature orgs, ISV/product companies, internal platform teams |
| **Pros** | Low friction, builds awareness, no billing disputes | True financial accountability, drives behavior change |
| **Cons** | No teeth — teams can ignore it | Requires mature tagging, complex shared cost allocation |
| **Shared Costs** | Informational only | Must be allocated (by formula, usage, or equal split) |

**My recommendation:**

Start with showback for the first 6–12 months. Use it to:
1. Find and fix tagging gaps (you need >95% tagged before chargeback is meaningful)
2. Build trust with engineering teams (no surprises)
3. Validate your shared cost allocation methodology

Move to chargeback when:
- Tagging coverage > 95%
- Finance and Engineering leadership are aligned on allocation methodology
- You have a dispute resolution process for billing discrepancies
- The organization has real financial accountability at the team level (P&L ownership)

**Real example:** A SaaS company I worked with had perfect showback for 18 months. Teams could see their costs but ignored them. We moved to chargeback — each team's cloud spend came out of their engineering budget. Within 90 days, every team had implemented at least 3 cost optimizations. Culture changed faster than any tool could achieve.

---

## AWS Billing & Cost Management {#billing}

### Q11: Explain the difference between Unblended, Blended, and Effective costs in AWS billing. Which do you use for chargeback?

**Expert Answer:**

```
Unblended Cost:  The actual rate charged for each individual usage record.
                 If you buy an RI, usage covered by that RI is priced at the RI rate.
                 Non-covered usage is at On-Demand rate.
                 BEST FOR: Understanding what you're actually paying, account-level chargeback.

Blended Cost:    A weighted average of all rates applied across a linked account.
                 Designed to "share" RI/SP savings across all accounts proportionally.
                 LEGACY: Blended cost is considered outdated by FinOps practitioners.
                 AVOID: Creates confusion; no longer recommended by AWS.

Effective Cost:  The amortized cost including pre-paid RIs/SPs spread over their term.
                 Also includes free tier credits, EDP discounts.
                 BEST FOR: True cost of running a workload over time.
                 BEST FOR: Executive reporting and unit economics.

Net Unblended:   Unblended minus any credits, discounts, or refunds.
                 BEST FOR: Most accurate representation of actual cash outflow.
```

**For chargeback:** I use **Net Unblended Cost** at the resource level, with RI/SP savings allocated proportionally using `reservation_effective_cost` from CUR. This requires an allocation formula for shared savings, but it's the most accurate and defensible for finance.

---

### Q12: What is the Cost and Usage Report (CUR)? How is it different from Cost Explorer?

**Expert Answer:**

| | Cost Explorer | CUR |
|---|---|---|
| **Data granularity** | Hourly/daily/monthly aggregates | Line-item per hour per resource |
| **Dimensions** | Limited (20–30) | 300+ columns including all tags, RI/SP data |
| **Historical depth** | 13 months | Unlimited (you own the S3 data) |
| **Query interface** | API / Console | Athena SQL |
| **Cost** | API calls are charged | S3 storage + Athena query costs |
| **Real-time** | ~24h lag | 24h lag (refreshed up to 3x/day) |
| **Best for** | Quick ad-hoc analysis, alerts | Production analytics, chargeback, billing |

**The CUR is the source of truth for all serious FinOps work.** Cost Explorer is a frontend. CUR is the database.

Key CUR columns to know:
- `line_item_unblended_cost` — What you paid
- `reservation_effective_cost` — Your amortized RI/SP cost
- `line_item_resource_id` — The actual resource (instance ID, volume ID, etc.)
- `resource_tags_*` — Your custom tags
- `savings_plan_savings_plan_effective_cost` — SP amortized cost
- `line_item_line_item_type` — `Usage`, `Tax`, `RIFee`, `SavingsPlanRecurringFee`

---

### Q13: How do you architect a FinOps data platform for a company with 200+ AWS accounts and $50M/month in cloud spend?

**Expert Answer:**

```
Architecture:

Management Account (Payer)
  ├── CUR → S3 (finops-cur-master bucket, us-east-1)
  │          ├── Parquet format (most efficient for Athena)
  │          ├── Partitioned by year/month/day
  │          └── S3 Intelligent Tiering lifecycle
  │
  ├── AWS Glue Crawler → automatic schema updates
  │
  ├── Amazon Athena (primary query engine)
  │   ├── Workgroup per team (cost controls per team)
  │   ├── Query result caching enabled
  │   └── S3 results bucket with 30d lifecycle
  │
  ├── AWS QuickSight (executive dashboards)
  │   ├── SPICE for fast queries
  │   ├── Row-level security (teams see only their data)
  │   └── Scheduled email reports
  │
  ├── Grafana Cloud (engineering dashboards)
  │   ├── Athena data source plugin
  │   ├── Real-time alerting
  │   └── Per-team panels
  │
  └── Custom FinOps API (optional, for internal portals)
      ├── Lambda + API Gateway
      ├── DynamoDB (cost summaries cache)
      └── Used by internal developer portal / Backstage
```

**Scale considerations at $50M/month:**
- CUR will be 50–200GB/month compressed — Parquet is essential
- Athena query costs can reach $5K/month if queries aren't optimized
  - Solution: partition pruning, columnar format, query result reuse
- QuickSight SPICE import is cheaper than live Athena queries for dashboards
- For real-time anomaly detection, use AWS Cost Anomaly Detection + EventBridge, not Athena polling

---

## Kubernetes FinOps {#k8s}

### Q41: How do you implement accurate cost allocation in a shared EKS cluster with 20 teams?

**Expert Answer:**

This is one of the hardest FinOps problems. The challenge: EC2 nodes are shared resources. Multiple team pods run on the same node. How do you split the node cost?

**Three approaches:**

**1. Namespace-based allocation (most common)**
- Install OpenCost or Kubecost
- Allocate node cost proportionally by CPU+memory *requests* per namespace
- Formula: `team_cost = (team_requested_cpu / total_requested_cpu) * node_cost`
- Pro: Simple. Con: Doesn't account for actual utilization

**2. Actual utilization allocation (more accurate)**
- Use CloudWatch Container Insights or Prometheus metrics
- Allocate by actual CPU+memory *usage* per namespace over time
- Pro: Penalizes over-provisioning accurately
- Con: Teams can game it (temporarily scale down during reporting)

**3. Dedicated node groups per team (simplest but most expensive)**
- Each team has their own node group
- No shared cost allocation needed
- Pro: Perfect accountability, team controls their own scaling
- Con: Poor bin-packing, 20–40% higher cluster cost

**My recommendation for production:**
Use OpenCost with namespace allocation based on *requests* for the base cost, *plus* a shared overhead allocation (kube-system, logging, monitoring) split equally across all teams. Document the formula, review quarterly.

```yaml
# Label namespaces for OpenCost allocation
kubectl label namespace team-payments \
  billing/team=payments \
  billing/cost-center=CC-1042 \
  billing/environment=production
```

---

### Q42: A developer says "Kubernetes is free, I'll just run my workload on EKS." What is the true cost of running a container on EKS?

**Expert Answer:**

EKS is definitively NOT free. The full cost breakdown:

```
EKS Control Plane:          $0.10/hr = $73/month per cluster (non-negotiable)

Worker Node (m5.xlarge):    $0.192/hr On-Demand

Overhead per node (wasted):
  kube-proxy, CoreDNS:      ~100m CPU / 200Mi memory reserved
  kubelet, containerd:      ~300m CPU / 500Mi memory reserved
  CNI plugin (VPC CNI):     ~50m CPU / 100Mi memory
  CloudWatch agent:         ~100m CPU / 300Mi memory
  Karpenter/cluster-autoscaler: ~100m CPU / 500Mi memory

Total overhead per node:    ~650m CPU / 1.6Gi memory
On m5.xlarge (4 vCPU/16Gi):
  CPU overhead:             650m / 4000m = 16% wasted
  Memory overhead:          1.6Gi / 16Gi = 10% wasted

EBS volumes (gp3):          $0.08/GB/month
  Root volume (50GB):       $4/month per node
  PVCs (application data):  Varies

Load Balancer (ALB):        $0.0225/hr + $0.008/LCU = ~$18-100/month
NAT Gateway:                $0.045/hr + $0.045/GB = ~$33-200+/month per AZ
CloudWatch metrics/logs:    $0.30/metric/month + $0.50/GB ingestion

Data Transfer:
  Inter-AZ pod traffic:     $0.01/GB each direction
  Internet egress:          $0.085-0.09/GB

TOTAL for a simple 3-replica service:
  Compute share:            ~$30-60/month
  Storage:                  ~$5-15/month
  Networking:               ~$20-100/month
  Control plane share:      ~$5/month

Realistic total:            $60-180/month for a simple stateless service
```

This surprises developers who think containers are cheap. The answer is: "Containers are efficient, but the AWS infrastructure underneath them is not free."

---

## AI/ML & GPU Costs {#ai}

### Q56: Describe how you would implement a cost governance framework for a generative AI platform running on AWS Bedrock and SageMaker.

**Expert Answer:**

A GenAI platform has unique cost challenges: costs are token-based (not compute-based), can spike massively on misuse, and are hard to budget for (hard to predict token volumes).

**Framework components:**

**1. Unit Economics First**
Define your KPIs before governance:
- Cost per inference call
- Cost per 1K output tokens per model
- Cost per API customer (if SaaS)
- Cost per active user per month
- These become your guardrails

**2. Model Tiering (already shown in bedrock_model_router.py)**
- Route by task complexity — don't use Opus for FAQ lookups
- Haiku is 60x cheaper than Opus; use it for 80% of tasks

**3. Conversation Management**
- Enforce maximum context window (sliding window of 5–10 turns)
- Implement prompt compression for long contexts
- Cache responses for identical prompts (semantic caching with Titan Embeddings + Redis)

**4. Hard Budget Limits**
- Per-user daily token budget (DynamoDB counter + middleware check)
- Per-team hourly Bedrock spend circuit breaker (Lambda)
- Bedrock provisioned throughput only if you can prove consistent utilization > 50%

**5. SageMaker Endpoint Governance**
```python
# Rules for SageMaker endpoints:
# 1. All endpoints must have auto-scaling configured
# 2. Minimum instance count = 0 for dev endpoints (scale to zero)
# 3. All notebook instances must stop outside business hours
# 4. Training jobs must use Spot instances for non-time-critical work
# 5. SageMaker Studio domains must have idle timeout = 60 minutes
```

**6. FinOps Reporting**
- Tag every Bedrock call with `user_id`, `feature`, `team`
- Build CUR + Athena report: cost by feature, by team, by model
- Weekly review: which features have cost-per-call > target?

---

### Q57: A data science team says "we need a p3.16xlarge running 24/7 for training." How do you challenge and optimize this request?

**Expert Answer:**

The p3.16xlarge at $24.48/hr = $17,870/month. Before approving:

**Questions to ask:**
1. How many hours per week is it actually training? (Most DS teams: 20–40 hours/week, not 168)
2. Is the training job resumable? (Can it checkpoint to S3 and use Spot?)
3. Could SageMaker Training Jobs replace the persistent instance? (Pay only for training time)
4. Is p3.16xlarge the right size? (What's the actual GPU utilization? Would p3.8xlarge work?)
5. Are there idle periods (weekends, nights)? Can it be stopped automatically?

**Typical optimization:**
```
24/7 p3.16xlarge:       $24.48 × 730 = $17,870/month

Actual usage (40h/week training):
  On-Demand:            $24.48 × 40 × 4.3 = $4,210/month
  Spot (60% discount):  $24.48 × 0.40 × 40 × 4.3 = $1,684/month

SageMaker Training Jobs (Spot):
  Per-second billing, spot: ~$1,200-1,800/month for same workload
```

**Better architecture:**
1. Use SageMaker Training Jobs with Spot instances (checkpoint to S3 every epoch)
2. For development/iteration: SageMaker Studio with g5.xlarge on-demand (start/stop)
3. For production training: Managed Spot Training with automatic checkpointing
4. Savings: $17,870 → ~$1,500/month = **$196K/year**

---

## Architecture Scenarios {#architecture}

### Q86: Design a FinOps platform for a company migrating from on-premises to AWS, with $0 existing cloud infrastructure and a target of $2M/month cloud spend within 18 months.

**Expert Answer:**

**Phase 0 (Before Day 1): Establish the foundation**

```
Decisions to make before migrating a single workload:

1. Billing Structure:
   - AWS Organizations with management account
   - Separate accounts for: network, security, logging, shared-services, sandbox
   - Naming convention: company-environment-service (e.g., acme-prod-payments)

2. CUR Setup:
   - Enable immediately in management account (even before workloads)
   - You want 18 months of history by the time you're at $2M/month

3. Tagging Taxonomy:
   - Define 5 mandatory tags before any resource is created
   - SCP: deny resource creation without required tags
   - This is 10x harder to retrofit than to implement from day 1

4. Reserved Instances Strategy:
   - Don't buy any RIs for the first 3 months (don't know your patterns yet)
   - Month 3–6: Buy 1-year Compute Savings Plans for baseline
   - Month 12+: Consider 3-year RIs for proven steady workloads

5. FinOps Team:
   - Hire or designate a FinOps lead by Month 3
   - This person needs both cloud and finance knowledge
```

**Phase 1 (Months 1–6): Crawl**
- CUR deployed, Athena queries running
- Basic tagging and Cost Explorer dashboards
- Weekly cost review meeting (30 minutes, 3 people max)
- Target: 80% tagging coverage

**Phase 2 (Months 6–12): Walk**
- Showback reports by team (automated)
- First RI/SP purchases after 90 days of data
- Waste detection automation deployed
- Target: 90% tagging, first RI round

**Phase 3 (Months 12–18): Run**
- Automated anomaly detection + Slack alerts
- Chargeback integrated with internal billing
- Cost in CI/CD (Infracost on PRs)
- Unit economics dashboard live
- Target: >70% RI/SP coverage, <5% waste rate

**At $2M/month, realistic savings from optimization: $400K–$700K/year**

---

### Q87: You inherit an AWS environment spending $1.5M/month with no FinOps program. What do you do in your first 30, 60, and 90 days?

**Expert Answer:**

**Days 1–30: Assess and Stabilize**

```
Week 1: Understand the landscape
  - How many accounts? OUs? Billing structure?
  - Is CUR enabled? Can you query it?
  - What tagging exists? Run tag compliance report.
  - Who are the top 5 spenders? Meet with them.

Week 2: Quick wins (low risk, immediate savings)
  - S3/DynamoDB Gateway VPC endpoints (FREE, no risk)
  - Set retention on CloudWatch Log Groups with no policy
  - Find and document all unattached EBS volumes (don't delete yet)
  - Find all unassociated EIPs (document)

Week 3: Set up visibility
  - Deploy Cost Explorer dashboards for each team
  - Set up AWS Budgets with alert at 80% and 100% of last month's spend
  - Enable Cost Anomaly Detection for all services

Week 4: Report and prioritize
  - Present findings to VP Engineering / CTO
  - Top 10 waste items with dollar amounts
  - Top 3 quick-win optimizations (get approval)
  - Proposed 90-day roadmap
```

**Days 30–60: Execute Quick Wins**
```
  - Deploy waste cleanup automation (DRY_RUN=False after review)
  - First Compute Savings Plan purchase (1-year, based on 30 days of data)
  - Implement mandatory tagging SCP in non-production OUs
  - Set up weekly cost review meeting with each engineering team
  - Deploy idle EC2 detector, alert on zero-action threshold
```

**Days 60–90: Build the Program**
```
  - Chargeback/showback report in production (finance trusts it)
  - RI coverage analysis — plan purchases for Month 4
  - Build the FinOps KPI dashboard (targets: tagging 90%, waste < 5%, RI coverage 70%)
  - Hire second FinOps engineer if spend > $5M/year
  - Publish first FinOps newsletter to engineering all-hands
```

**Expected impact by Day 90:** $150K–$400K/month in identified savings, $50K–$150K actually realized.

---

## Cloud Economics {#economics}

### Q76: How do you calculate the total cost of ownership (TCO) for cloud vs on-premises?

**Expert Answer:**

Most TCO analyses are biased — either toward cloud (by tech teams) or on-premises (by infrastructure teams). The correct analysis includes:

**On-Premises Costs (often underestimated):**
```
Hardware:
  Server amortization (5-year): $15K-50K per server / 60 months
  Network equipment: $2K-10K/switch amortized
  Storage arrays: $100K-500K amortized

Facilities:
  Data center rent: $50-300/rack unit/month
  Power (redundant): $0.05-0.20/kWh × 24/7 × PUE 1.5-2.0
  Cooling: often bundled with power but can be 40-50% of compute power cost

People:
  Data center operations: 2-4 FTE per data center
  Hardware procurement: 1 FTE
  Network team: 2-4 FTE
  Storage team: 1-2 FTE
  Burdened cost (benefits, overhead): multiply salary × 1.4-1.6

Software:
  Operating system licenses: $500-2000/server/year (RHEL, Windows)
  VMware vSphere: $600-800/socket/year
  Backup software: $200-500/server/year
  Monitoring: $100-300/server/year

Opportunity cost:
  Capital tied up in hardware vs invested
  Provisioning lead time (6-12 weeks vs 5 minutes)
  Innovation velocity lost due to capacity constraints
```

**Cloud Benefits that TCO often misses:**
- Elasticity: only pay for what you use (impossible on-premises)
- Managed services: no DBAs needed for RDS, no Kafka admins for MSK
- Global reach: launch in Tokyo in 5 minutes
- Innovation: access to services (SageMaker, Bedrock, Rekognition) that would cost millions on-premises

**My TCO framework:**
```
True Cloud TCO = Compute + Storage + Network + Managed Services
               - Reduction in on-premises headcount
               - Reduction in licenses
               - Reduction in data center costs
               + Premium for cloud management (FinOps team, tools)
```

**Spoiler:** For most workloads, the break-even point depends heavily on utilization. If your on-premises utilization is < 40%, cloud is almost always cheaper (with proper optimization). If it's > 70%, dedicated cloud or hybrid is worth analyzing.

---

### Q85: What are unit economics in cloud, and why are they more important than absolute cloud spend?

**Expert Answer:**

Absolute cloud spend is a vanity metric. A company spending $10M/month on AWS might be extremely efficient. A company spending $100K/month might be wasting 70%.

**Unit economics tie cloud cost to business value:**

| Company Type | Unit | Example KPI | Good | Bad |
|---|---|---|---|---|
| SaaS | Per seat | Cloud cost per user/month | $0.50 | $5.00 |
| E-commerce | Per order | Cloud cost per order | $0.03 | $0.30 |
| API company | Per API call | Cloud cost per 1M calls | $5.00 | $50.00 |
| Data platform | Per GB processed | Cloud cost per TB | $1.00 | $10.00 |
| AI/ML product | Per inference | Cloud cost per 1K queries | $0.50 | $5.00 |
| FinTech | Per transaction | Cloud cost per transaction | $0.001 | $0.01 |

**Why unit economics > absolute spend:**

```
Scenario: Your cloud bill grew from $1M to $2M this quarter.

With absolute spend framing: "We doubled our cloud costs! Crisis!"

With unit economics framing:
  - Monthly active users grew from 1M to 3M
  - Revenue grew from $5M to $15M
  - Cost per user went from $1.00 to $0.67 (33% improvement)
  - Cloud as % of revenue went from 20% to 13%

Correct conclusion: "We scaled efficiently. Cloud unit economics improved."
```

**How to implement unit economics:**

```python
# scripts/unit_economics_calculator.py
"""
Combines AWS billing data with business metrics from your data warehouse
to produce unit economics KPIs.
"""
import boto3
import json
from datetime import datetime, timedelta

def get_monthly_cloud_cost(month_year: str) -> float:
    """Get total cloud cost for a month from Cost Explorer."""
    ce = boto3.client('ce')
    year, month = month_year.split('-')
    start = f"{year}-{month}-01"
    end = f"{year}-{int(month)+1:02d}-01" if int(month) < 12 else f"{int(year)+1}-01-01"

    response = ce.get_cost_and_usage(
        TimePeriod={'Start': start, 'End': end},
        Granularity='MONTHLY',
        Metrics=['UnblendedCost']
    )
    return float(response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount'])

def calculate_unit_economics(cloud_cost: float, business_metrics: dict) -> dict:
    """Calculate unit economics KPIs."""
    return {
        'cost_per_active_user': cloud_cost / business_metrics.get('mau', 1),
        'cost_per_api_call': cloud_cost / business_metrics.get('api_calls', 1) * 1_000_000,
        'cloud_as_pct_revenue': (cloud_cost / business_metrics.get('revenue', 1)) * 100,
        'cost_per_transaction': cloud_cost / business_metrics.get('transactions', 1)
    }

if __name__ == '__main__':
    # Example usage
    cloud_cost = get_monthly_cloud_cost('2024-06')

    # These would come from your data warehouse / product analytics
    business_metrics = {
        'mau': 500_000,
        'api_calls': 2_000_000_000,
        'revenue': 8_000_000,
        'transactions': 5_000_000
    }

    kpis = calculate_unit_economics(cloud_cost, business_metrics)
    print(f"\nUnit Economics — June 2024")
    print(f"Total Cloud Spend: ${cloud_cost:,.2f}")
    print(f"Cost per MAU: ${kpis['cost_per_active_user']:.4f}")
    print(f"Cost per 1M API calls: ${kpis['cost_per_api_call']:.4f}")
    print(f"Cloud as % Revenue: {kpis['cloud_as_pct_revenue']:.1f}%")
    print(f"Cost per Transaction: ${kpis['cost_per_transaction']:.6f}")
```

---

*This is a subset of 100+ questions. See the full list with answers for all 100 questions in [FULL_INTERVIEW_GUIDE.md](FULL_INTERVIEW_GUIDE.md).*

---

## 🎯 Interview Tips for Principal FinOps Roles

**What interviewers at FAANG/Tier-1 are looking for:**

1. **Specificity over breadth** — Say "m5.xlarge at $0.192/hr" not "EC2 is expensive"
2. **Business context** — Always tie optimization to business impact, not just cost savings
3. **Trade-off thinking** — "We could save $50K/month with Spot but it adds operational complexity for the on-call team — here's how I'd evaluate that trade-off"
4. **Failure stories** — "Here's an optimization that looked good but had unintended consequences"
5. **Culture awareness** — FinOps is 40% technology, 60% organizational change management

**Red flags interviewers look for:**
- Can only discuss tooling, not strategy
- Focuses only on cost cutting, not value optimization
- No opinion on build vs buy (just "use AWS Compute Optimizer")
- Has never pushed back on a business decision based on cloud economics
- Cannot explain a CUR column or write an Athena query

---

*Back to [Main README](../README.md)*
