# 22 — Kubernetes FinOps (General)

> *Kubernetes abstracting away infrastructure is great for developers, but it makes cost allocation and optimization incredibly difficult for FinOps teams.*

*(For AWS EKS specific optimizations like Karpenter, see [08-EKS-Cost-Optimization](../08-EKS-Cost-Optimization/README.md))*

---

## 🏗️ The Kubernetes FinOps Maturity Model

1. **Crawl:** You know the total cost of the EC2 nodes running your cluster.
2. **Walk:** You use OpenCost or Kubecost to allocate node costs to Namespaces.
3. **Run:** Developers see cost-per-pod in CI/CD, and Karpenter autoscales nodes instantly to match pod requests.

---

## 📊 Kubecost / OpenCost

You absolutely must run a cost allocation tool inside the cluster. OpenCost is an open-source CNCF project that measures CPU, memory, storage, and network usage per pod/namespace and maps it to the cloud provider bill.

**Install OpenCost via Helm:**
```bash
helm repo add opencost https://opencost.github.io/opencost-helm-chart
helm upgrade -i opencost opencost/opencost -n opencost --create-namespace
```

---

## 🚧 Preventative Governance: ResourceQuotas

A rogue deployment with 1,000 replicas can bankrupt a cloud account if autoscaling is enabled. You must enforce maximums at the Namespace level.

```yaml
# Enforce maximum compute for a namespace
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-frontend-quota
  namespace: team-frontend
spec:
  hard:
    requests.cpu: "10"       # Total CPU guaranteed across all pods
    requests.memory: 20Gi    # Total Memory guaranteed
    limits.cpu: "20"         # Absolute maximum CPU allowed
    limits.memory: 40Gi      # Absolute maximum memory allowed
    pods: "50"               # Max number of pods
```

---

## 🚦 Preventative Governance: LimitRanges

Developers often forget to set CPU/Memory requests on their pods. If they don't, Kubernetes scheduling breaks down, and OpenCost cannot allocate costs accurately. LimitRanges provide default values.

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: default-pod-limits
  namespace: team-frontend
spec:
  limits:
  - default:           # If limits aren't specified, use these
      cpu: 500m
      memory: 512Mi
    defaultRequest:    # If requests aren't specified, use these
      cpu: 100m
      memory: 256Mi
    type: Container
```

---

## ✅ Kubernetes FinOps Checklist
- [ ] Install OpenCost/Kubecost to allocate shared node costs to Namespaces.
- [ ] Enforce ResourceQuotas on EVERY non-system namespace.
- [ ] Enforce LimitRanges to ensure every pod has a default request/limit.
- [ ] Use Kyverno or OPA Gatekeeper to block deployments missing specific cost-allocation labels (e.g., `cost-center`).
