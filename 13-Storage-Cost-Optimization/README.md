# 13 — Storage Cost Optimization (EBS & EFS)

> *Block storage (EBS) and file storage (EFS) are frequent culprits of cloud waste. When an EC2 instance is terminated, its attached EBS volumes are often left behind as orphaned "available" volumes.*

---

## 💿 EBS Cost Optimization

### 1. Orphaned Volume Cleanup
See [`25-Automation/lambda_functions/ebs_volume_reaper.py`](../25-Automation/lambda_functions/ebs_volume_reaper.py) for the production bot that tags and deletes unattached volumes.

### 2. The gp2 to gp3 Migration (EBS)
Just like RDS, standard EC2 volumes should use `gp3` instead of `gp2`. It is 20% cheaper and decoupled IOPS/throughput.

**Athena CUR Query to find gp2 waste:**
```sql
SELECT 
    line_item_resource_id,
    line_item_usage_account_id,
    SUM(line_item_unblended_cost) AS monthly_cost,
    SUM(line_item_unblended_cost) * 0.20 AS potential_savings
FROM "athenacurcfn"."finops_cur_hourly"
WHERE year = '2024' AND month = '06'
  AND line_item_usage_type LIKE '%EBS:VolumeUsage.gp2'
GROUP BY line_item_resource_id, line_item_usage_account_id
ORDER BY monthly_cost DESC;
```

### 3. Snapshot Lifecycle Management
Snapshots charge for incremental changes. Over years, this adds up massively.

See [`25-Automation/lambda_functions/snapshot_manager.py`](../25-Automation/lambda_functions/snapshot_manager.py) which moves snapshots > 30 days to EBS Snapshot Archive (75% savings) and deletes snapshots > 90 days.

---

## 📁 EFS (Elastic File System) FinOps

EFS Standard is **$0.30/GB-month** — incredibly expensive compared to EBS ($0.08) or S3 ($0.023).

### EFS Lifecycle Management
EFS Infrequent Access (IA) is **$0.016/GB-month** (95% cheaper!).
EFS Archive is **$0.008/GB-month**.

**Terraform Enforcement:**
```hcl
resource "aws_efs_file_system" "shared_data" {
  creation_token = "shared-data-prod"
  
  # ALWAYS enable lifecycle management on EFS
  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }
  
  lifecycle_policy {
    transition_to_archive = "AFTER_90_DAYS"
  }
}
```

### EFS Provisioned Throughput Anti-Pattern
Teams often enable "Provisioned Throughput" to fix EFS performance issues, paying $6.00/MBps/month. This is usually the wrong architectural choice. 
**Fix:** Switch to "Elastic Throughput" ($0.03/GB transferred) which handles spikes automatically and is usually cheaper unless you are transferring terabytes continuously.

---

## ✅ Storage Optimization Checklist

- [ ] Deploy `ebs_volume_reaper.py` to continuously delete unattached EBS volumes.
- [ ] Migrate all EC2 and EKS node volumes from `gp2` to `gp3`.
- [ ] Ensure DLM (Data Lifecycle Manager) or `snapshot_manager.py` is pruning old EBS snapshots.
- [ ] Enable EFS Lifecycle Policies (transition to IA) on EVERY EFS filesystem.
- [ ] Review Provisioned IOPS (`io1`/`io2`) usage — can it run on `gp3` with maxed out 16,000 IOPS?
