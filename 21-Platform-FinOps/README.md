# 21 — Platform FinOps

> *Platform Engineering is FinOps at scale. The best way to reduce cloud costs is to abstract the infrastructure away from developers and provide them with cost-optimized, secure-by-default internal developer platforms (IDPs).*

---

## 🛠️ The Platform FinOps Architecture

Instead of letting 50 development teams write their own Terraform for EC2, RDS, and EKS, the Platform Team provides **Golden Paths**.

### Example: The "Golden Path" Web Service
When a developer requests a new web service in Backstage (or another IDP), the platform provisions:
- A Kubernetes namespace (with predefined ResourceQuotas and LimitRanges)
- Or an ECS Fargate service (defaulting to Fargate Spot for non-prod)
- An RDS instance (defaulting to Graviton, gp3, and night-time shutdown schedules for dev)
- Mandatory FinOps tags (CostCenter, Team, Environment, Service) automatically applied

**Result:** The developer gets their infrastructure in 5 minutes, and FinOps gets 100% compliance and optimization by default.

---

## 🚧 FinOps Guardrails (Preventative)

Platform FinOps shifts from *detective* controls (finding waste after it's deployed) to *preventative* controls.

### 1. CI/CD Cost Estimation (Infracost)
Block PRs that increase infrastructure costs by > 20% without approval.
(See [24-GitHub-Actions](../24-GitHub-Actions/README.md) for the implementation).

### 2. OPA / Kyverno Policies (Kubernetes)
Reject any Pod deployment that does not specify CPU and Memory requests/limits.

```yaml
# Kyverno Policy: Require Limits and Requests
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-resources
spec:
  validationFailureAction: enforce
  rules:
  - name: check-memory-requests-limits
    match:
      resources:
        kinds: [Pod]
    validate:
      message: "CPU and Memory requests and limits are required."
      pattern:
        spec:
          containers:
          - resources:
              requests:
                memory: "?*"
                cpu: "?*"
              limits:
                memory: "?*"
```

### 3. Terraform Sentinel / Checkov (Infrastructure)
Reject Terraform deployments that attempt to provision expensive resources (e.g., `p4d` instances or `io2` volumes) without special approval.

---

## 💸 Shared Service Cost Allocation

Platform teams run shared services (Kafka, EKS control planes, Transit Gateways). How do you charge this back?

**The Platform Tax:**
Distribute the cost of shared platform services to the application teams based on a proportional metric.

- **EKS Control Plane:** Split equally among all namespaces, or proportionally based on node compute used.
- **Kafka / MSK:** Charge per GB of throughput or per topic.
- **Datadog / Monitoring:** Charge based on host count or custom metric volume.

---

## ✅ Platform FinOps Checklist
- [ ] Embed Infracost or Terracost in your IaC CI/CD pipelines.
- [ ] Create automated provisioning templates (Golden Paths) that hardcode cost-saving defaults (gp3, Graviton, Spot).
- [ ] Enforce resource limits at the platform level (K8s LimitRanges, AWS SCPs).
- [ ] Define a transparent "Platform Tax" methodology for allocating shared infrastructure costs.
