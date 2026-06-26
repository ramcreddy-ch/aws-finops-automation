# 23 — Terraform FinOps

> *Infrastructure as Code is the best place to implement FinOps. If you fix it in Terraform, you fix it forever. If you fix it in the console, it will break again on the next deployment.*

---

## 🛠️ The FinOps Terraform Module Pattern

Platform teams should provide pre-configured Terraform modules that have FinOps best practices baked in. Developers consume the module, not the raw AWS provider resource.

### Example: The Cost-Optimized RDS Module
```hcl
# modules/finops-rds/main.tf
# A wrapper around the AWS RDS resource that enforces cost rules.

resource "aws_db_instance" "this" {
  # Enforce gp3 (never gp2)
  storage_type = "gp3"
  
  # Only allow Graviton instances
  instance_class = var.instance_class
  
  # Auto-shutdown logic for non-prod
  tags = merge(
    var.tags,
    {
      "FinOps:Schedule" = var.environment == "prod" ? "24x7" : "business-hours"
    }
  )

  lifecycle {
    precondition {
      condition     = can(regex("^db\\.[a-z0-9]+\\.g", var.instance_class))
      error_message = "FinOps Policy: RDS instances must use Graviton (g) instance classes."
    }
  }
}
```

---

## 🏷️ Default Tags

Never rely on developers to remember tagging. Use the AWS Provider `default_tags` block to ensure every supported resource gets tagged globally.

```hcl
provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      Environment = var.environment
      Team        = var.team_name
      CostCenter  = var.cost_center
      ManagedBy   = "Terraform"
    }
  }
}
```

---

## 💰 Infracost Integration

Run Infracost directly in your local terminal before running `terraform apply`.

```bash
# See how much your local terraform changes will cost
infracost breakdown --path .

# See the difference between your code and the current state
infracost diff --path .
```

*(See [24-GitHub-Actions](../24-GitHub-Actions/README.md) for how to automate this in CI/CD).*
