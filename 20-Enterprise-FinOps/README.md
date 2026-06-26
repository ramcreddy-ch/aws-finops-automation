# 20 — Enterprise FinOps

> *Enterprise FinOps is about operating at scale. When you have $100M+ in cloud spend, optimization is no longer about finding idle EC2 instances—it is about organizational design, discount strategies (EDP), and building a FinOps culture.*

---

## 🏛️ Enterprise Discount Program (EDP)

An EDP is a negotiated contract with AWS where you commit to a specific volume of spend over 1-5 years in exchange for a flat discount across all services.

**Key EDP Metrics:**
- **Commitment Level:** E.g., commit to spend $10M/year for 3 years.
- **Discount Tier:** E.g., 9% discount if spending $10M, 11% if spending $20M.
- **True-up / Shortfall:** If you only spend $8M in a year where you committed to $10M, you must write AWS a check for the $2M shortfall.

**The EDP FinOps Strategy:**
1. **Never commit your full projected spend.** Commit to 70-80% of your projected baseline.
2. **Stacking Discounts:** EDP discounts stack *on top* of Savings Plans (SPs) and Reserved Instances (RIs).
   *Example: Compute SP (30% off) + EDP (10% off) = 37% total effective discount.*
3. **Marketplace Leverage:** Buying software (Datadog, Snowflake, CrowdStrike) through the AWS Marketplace usually retires 50-100% of your EDP commit. Use this if you are missing your spend target.

---

## 📈 The FinOps KPI Dashboard

At the enterprise level, executives do not care about individual Lambda functions. They care about KPIs.

**The Big 4 Enterprise KPIs:**

1. **Tagging Compliance %**
   - *Target:* > 95%
   - *Meaning:* Can we allocate costs to the correct P&L?
2. **Commitment Coverage % (RI/SP)**
   - *Target:* 70-80%
   - *Meaning:* Are we maximizing our discounts on baseline compute?
3. **Effective Savings Rate (ESR)**
   - *Target:* > 25%
   - *Meaning:* How much are we saving compared to On-Demand prices across all discounts (EDP, SP, RI)?
4. **Unit Cost Trend**
   - *Target:* Decreasing
   - *Meaning:* Is our cost per transaction/customer going down as we scale?

---

## 🔄 Centralized vs Decentralized FinOps

**Centralized (The traditional approach):**
- A dedicated FinOps team analyzes the bill, finds waste, and buys all RIs/SPs.
- *Pros:* High RI/SP coverage, deep expertise.
- *Cons:* Engineering teams ignore recommendations, feeling no ownership.

**Decentralized (The modern/agile approach):**
- The FinOps team acts as a platform/enablement team.
- They build dashboards and guardrails (e.g., Infracost in CI/CD).
- Engineering Directors own their cloud budgets and are accountable for their unit costs.
- *Pros:* True FinOps culture, cost is a first-class engineering metric.
- *Cons:* Requires massive leadership buy-in and excellent tooling.

---

## ✅ Enterprise Checklist
- [ ] Model EDP scenarios BEFORE signing (understand the shortfall risk).
- [ ] Shift software vendor purchases to AWS Marketplace if tracking behind on EDP commit.
- [ ] Define the formula for distributing shared costs (networking, support, shared clusters) to BUs.
- [ ] Automate chargeback reporting and integrate it with the corporate ERP/General Ledger.
