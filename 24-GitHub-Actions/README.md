# 24 — GitHub Actions FinOps

> *CI/CD pipelines are often a blind spot for FinOps. GitHub Actions minutes and runner infrastructure can silently drain thousands of dollars a month. Furthermore, CI/CD is the perfect place to inject FinOps checks.*

---

## 💸 Optimizing GitHub Actions Costs

GitHub charges by the minute for managed runners, with multipliers based on OS:
- Linux: 1x (e.g., $0.008/min)
- Windows: 2x
- macOS: 10x

### 1. Self-Hosted Runners (AWS Auto Scaling)
If you run thousands of CI/CD jobs, move from GitHub Managed Runners to self-hosted runners on AWS Spot Instances.

**Architecture (Action Runner Controller - ARC):**
Deploy ARC into your EKS cluster. It listens to GitHub webhooks and auto-scales runner pods based on queue depth.
- Configure ARC to run on **Spot node groups**.
- CI jobs are naturally resilient to interruptions; just re-run the job if a Spot node dies.
- **Savings: ~60-80% compared to managed runners.**

### 2. Cache Dependencies Aggressively
Downloading `node_modules` or Maven dependencies every run wastes bandwidth and compute time.

```yaml
# Good Pattern: Caching dependencies
- name: Cache Node.js modules
  uses: actions/cache@v3
  with:
    path: ~/.npm
    key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-node-
```

---

## 🚧 Shifting FinOps Left: Infracost

The most powerful FinOps workflow is showing developers the cost impact of their code *before* it is merged.

### Infracost GitHub Action

When a developer opens a Pull Request with Terraform changes, Infracost comments on the PR with the estimated cost difference.

```yaml
# .github/workflows/infracost.yml
name: Infracost
on: [pull_request]

jobs:
  infracost:
    name: Infracost Check
    runs-on: ubuntu-latest
    steps:
      - name: Checkout PR branch
        uses: actions/checkout@v3

      - name: Setup Infracost
        uses: infracost/actions/setup@v2
        with:
          api-key: ${{ secrets.INFRACOST_API_KEY }}

      - name: Generate Infracost cost estimate baseline
        run: |
          infracost breakdown --path . \
                              --format json \
                              --out-file infracost-base.json

      - name: Post Infracost Comment
        uses: infracost/actions/comment@v2
        with:
          path: infracost-base.json
          behavior: update
```

**What the developer sees in the PR:**
> 💰 **Infracost Estimate:**
> Monthly cost will increase by **$345.00**
> - `aws_db_instance.main` (db.r6g.large) -> +$210.00
> - `aws_instance.worker` (m5.xlarge) -> +$135.00

---

## ✅ CI/CD FinOps Checklist
- [ ] Migrate heavy Linux CI jobs to AWS-hosted ARC (Action Runner Controller) on Spot instances.
- [ ] Implement robust caching (`actions/cache`) for all language package managers.
- [ ] Implement `Infracost` on all infrastructure-as-code repositories to shift cost left.
- [ ] Audit CI/CD retention policies (logs and artifacts are stored on GitHub/AWS and cost money).
