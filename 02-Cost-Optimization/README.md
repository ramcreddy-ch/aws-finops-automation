# 02 — Cost Optimization Lifecycle

> *Cost optimization is not a one-time project; it is a continuous lifecycle. Treat FinOps like security—you don't "secure" an application once and walk away.*

---

## 🔄 The Continuous Optimization Loop

Effective FinOps teams operate in a continuous 4-step loop:

### 1. Visibility & Allocation (See It)
You cannot optimize what you cannot see.
- Tagging must be enforced (Target: > 95% compliance).
- Every dollar must map to a product, team, and environment.
- Dashboards must be available to engineering teams in near real-time.

### 2. Architecture Optimization (Fix the Design)
This is where 70% of savings happen, but it takes engineering effort.
- Shift from EC2 to Serverless (Lambda, Fargate).
- Shift from Provisioned RDS to Aurora Serverless (if spiky).
- Implement S3 Intelligent-Tiering.
- Add VPC Endpoints to eliminate NAT Gateway costs.

### 3. Resource Optimization (Fix the Waste)
This is the low-hanging fruit (requires minimal engineering).
- **Rightsizing:** Downsize `m5.4xlarge` to `m5.xlarge` if CPU is < 20%.
- **Modernization:** Upgrade `gp2` to `gp3`, `m5` to `m6g` (Graviton).
- **Cleanup:** Delete unattached EBS volumes, zombie RDS instances, and old snapshots.
- **Scheduling:** Stop dev/test environments nights and weekends.

### 4. Rate Optimization (Fix the Price)
This requires zero engineering effort, handled entirely by FinOps/Finance.
- Purchase Compute Savings Plans (SPs) and Reserved Instances (RIs).
- Optimize EDP (Enterprise Discount Program) commitments.
- Purchase Spot instances for stateless, fault-tolerant workloads.

---

## 📈 Optimization Priority Matrix

When prioritizing FinOps work, map tasks on a grid of **Engineering Effort** vs **Cost Impact**.

| High Impact, Low Effort (DO FIRST) | High Impact, High Effort (PLAN) |
|---|---|
| - Convert all gp2 to gp3 | - Migrate to Graviton processors |
| - S3 Intelligent-Tiering | - Re-architect to Serverless/Lambda |
| - Delete unattached EBS/EIPs | - Spot instance adoption in EKS |
| - Buy Savings Plans | - Multi-tenant database consolidation |

| Low Impact, Low Effort (DO LATER) | Low Impact, High Effort (AVOID) |
|---|---|
| - Delete unused small snapshots | - Micro-optimizing 128MB lambdas |
| - Downsize non-prod t3 instances | - Building custom billing scripts |

---

## ✅ Best Practices
- **Do Rate Optimization Last:** Never buy a Savings Plan for a workload you are about to downsize or turn off. Optimize the architecture and resources first, *then* commit to the discounted rate.
- **Automate Everything:** Waste will always creep back in. Build lambdas (like the ones in this repository) to continuously prune waste automatically.
