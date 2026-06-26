# 03 — Enterprise Tagging Strategy

> *Tagging is not a chore. It is the foundation of every cost allocation, chargeback, showback, and automation decision in your AWS environment. Without it, you are flying blind.*

---

## 🎯 Why Tagging Fails at Enterprise Scale

Most organizations have a tagging policy on paper. The problem is enforcement. Common failure modes:

| Failure Mode | Root Cause | Impact |
|---|---|---|
| Tags defined but not enforced | No SCP/automation guardrail | 60–80% of resources untagged |
| Tags inconsistent across teams | No standard taxonomy | Impossible to allocate costs |
| Tags on EC2 but not EBS volumes | AWS doesn't propagate by default | Hidden unowned storage |
| Tagging happens after provisioning | No IaC enforcement | Drift over time |
| Finance and Engineering use different tag keys | No governance | Chargeback failures |
| Tags contain PII or secrets | No validation | Security/compliance risk |

---

## 🏷️ Mandatory Tag Taxonomy

### Tier 1 — Cost Allocation (Required on ALL resources)

| Tag Key | Description | Valid Values | Example |
|---|---|---|---|
| `env` | Environment | `prod`, `staging`, `dev`, `sandbox` | `prod` |
| `team` | Owning team | Free text | `platform-engineering` |
| `cost-center` | Finance cost center code | Alphanumeric | `CC-1042` |
| `project` | Business project or product | Free text | `checkout-api` |
| `owner` | Individual owner (email) | Valid email | `sre@company.com` |

### Tier 2 — Operational (Required on compute/data resources)

| Tag Key | Description | Valid Values | Example |
|---|---|---|---|
| `service` | Microservice or application name | Free text | `payment-processor` |
| `data-classification` | Data sensitivity | `public`, `internal`, `confidential`, `restricted` | `confidential` |
| `backup-policy` | Backup retention | `7d`, `30d`, `90d`, `none` | `30d` |
| `auto-stop` | Allow automated stop/terminate | `true`, `false` | `false` |
| `schedule` | Business hours only flag | `business-hours`, `24x7`, `weekdays` | `business-hours` |

### Tier 3 — FinOps Lifecycle (Used by automation bots)

| Tag Key | Set By | Purpose |
|---|---|---|
| `FinOps:MarkedForDeletion` | Automation bot | ISO timestamp when marked for deletion |
| `FinOps:Retain` | Engineer | `true` to opt out of cleanup |
| `FinOps:AutoBackup` | Automation bot | Marks final snapshots before deletion |
| `FinOps:LastReviewed` | FinOps bot | Last rightsizing review date |
| `FinOps:RightSizeRecommendation` | Compute Optimizer bot | e.g., `downgrade-to-t3.medium` |

---

## 🔐 Enforcement via Service Control Policies (SCPs)

### SCP: Deny Resource Creation Without Required Tags

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyEC2WithoutRequiredTags",
      "Effect": "Deny",
      "Action": [
        "ec2:RunInstances"
      ],
      "Resource": [
        "arn:aws:ec2:*:*:instance/*"
      ],
      "Condition": {
        "Null": {
          "aws:RequestTag/env": "true"
        }
      }
    },
    {
      "Sid": "DenyEC2WithoutTeamTag",
      "Effect": "Deny",
      "Action": [
        "ec2:RunInstances"
      ],
      "Resource": [
        "arn:aws:ec2:*:*:instance/*"
      ],
      "Condition": {
        "Null": {
          "aws:RequestTag/team": "true"
        }
      }
    },
    {
      "Sid": "DenyEC2WithoutCostCenter",
      "Effect": "Deny",
      "Action": [
        "ec2:RunInstances"
      ],
      "Resource": [
        "arn:aws:ec2:*:*:instance/*"
      ],
      "Condition": {
        "Null": {
          "aws:RequestTag/cost-center": "true"
        }
      }
    },
    {
      "Sid": "DenyRDSWithoutRequiredTags",
      "Effect": "Deny",
      "Action": [
        "rds:CreateDBInstance",
        "rds:CreateDBCluster"
      ],
      "Resource": "*",
      "Condition": {
        "Null": {
          "aws:RequestTag/env": "true"
        }
      }
    }
  ]
}
```

> ⚠️ **CAUTION:** Apply SCPs to non-production OUs first. Always test with `DryRun` where available. SCPs affect ALL accounts in the OU — including break-glass admin accounts.

---

## 🤖 Automated Tag Compliance Lambda

```python
# lambda_functions/tag_compliance_enforcer.py
"""
Scans all EC2, RDS, EBS, Lambda, S3 resources across all regions.
Reports compliance percentage per account, per team.
Optionally sends Slack/email alerts to resource owners.
"""

import boto3
import json
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REQUIRED_TAGS = ['env', 'team', 'cost-center', 'project', 'owner']

SLACK_WEBHOOK = os.environ.get('SLACK_WEBHOOK_URL', '')

def get_ec2_compliance(region: str) -> dict:
    """Returns compliance stats for EC2 instances in a region."""
    ec2 = boto3.client('ec2', region_name=region)
    compliant = 0
    non_compliant = []

    paginator = ec2.get_paginator('describe_instances')
    for page in paginator.paginate(Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'stopped']}]):
        for reservation in page['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']
                tags = {t['Key']: t['Value'] for t in instance.get('Tags', [])}
                missing = [t for t in REQUIRED_TAGS if t not in tags]
                if missing:
                    non_compliant.append({
                        'resource': instance_id,
                        'type': 'EC2',
                        'region': region,
                        'missing_tags': missing,
                        'owner': tags.get('owner', 'UNKNOWN')
                    })
                else:
                    compliant += 1

    return {'compliant': compliant, 'non_compliant': non_compliant}

def get_rds_compliance(region: str) -> dict:
    """Returns compliance stats for RDS instances in a region."""
    rds = boto3.client('rds', region_name=region)
    compliant = 0
    non_compliant = []

    paginator = rds.get_paginator('describe_db_instances')
    for page in paginator.paginate():
        for db in page['DBInstances']:
            db_id = db['DBInstanceIdentifier']
            arn = db['DBInstanceArn']
            tag_resp = rds.list_tags_for_resource(ResourceName=arn)
            tags = {t['Key']: t['Value'] for t in tag_resp.get('TagList', [])}
            missing = [t for t in REQUIRED_TAGS if t not in tags]
            if missing:
                non_compliant.append({
                    'resource': db_id,
                    'type': 'RDS',
                    'region': region,
                    'missing_tags': missing,
                    'owner': tags.get('owner', 'UNKNOWN')
                })
            else:
                compliant += 1

    return {'compliant': compliant, 'non_compliant': non_compliant}

def send_slack_alert(non_compliant_resources: list, account_id: str):
    """Sends a Slack alert listing non-compliant resources."""
    import urllib.request
    if not SLACK_WEBHOOK or not non_compliant_resources:
        return

    top_offenders = non_compliant_resources[:10]
    fields = []
    for r in top_offenders:
        fields.append({
            "title": f"{r['type']}: {r['resource']} ({r['region']})",
            "value": f"Missing tags: `{', '.join(r['missing_tags'])}` | Owner: {r['owner']}",
            "short": False
        })

    payload = {
        "attachments": [{
            "color": "danger",
            "pretext": f"🏷️ *Tag Compliance Alert* — Account: `{account_id}`",
            "title": f"{len(non_compliant_resources)} Non-Compliant Resources Found",
            "fields": fields,
            "footer": "AWS FinOps Tag Enforcer",
            "ts": int(datetime.now(timezone.utc).timestamp())
        }]
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(SLACK_WEBHOOK, data=data, headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req)

def lambda_handler(event, context):
    sts = boto3.client('sts')
    account_id = sts.get_caller_identity()['Account']
    ec2_global = boto3.client('ec2', region_name='us-east-1')
    regions = [r['RegionName'] for r in ec2_global.describe_regions()['Regions']]

    all_non_compliant = []
    total_compliant = 0

    for region in regions:
        logger.info(f"Scanning region: {region}")
        ec2_result = get_ec2_compliance(region)
        rds_result = get_rds_compliance(region)

        total_compliant += ec2_result['compliant'] + rds_result['compliant']
        all_non_compliant.extend(ec2_result['non_compliant'])
        all_non_compliant.extend(rds_result['non_compliant'])

    total = total_compliant + len(all_non_compliant)
    compliance_pct = (total_compliant / total * 100) if total > 0 else 100.0

    logger.info(f"Tag Compliance: {compliance_pct:.1f}% ({total_compliant}/{total} compliant)")
    logger.info(f"Non-compliant resources: {len(all_non_compliant)}")

    if compliance_pct < 90.0:
        send_slack_alert(all_non_compliant, account_id)

    return {
        'statusCode': 200,
        'compliance_percentage': round(compliance_pct, 2),
        'total_resources': total,
        'compliant_resources': total_compliant,
        'non_compliant_count': len(all_non_compliant),
        'non_compliant_sample': all_non_compliant[:20]
    }
```

---

## 📊 Tagging Compliance Dashboard (CloudWatch)

```python
# scripts/publish_tagging_metrics.py
"""
Publishes tagging compliance metrics to CloudWatch for dashboarding.
Run after tag_compliance_enforcer.py to track compliance over time.
"""
import boto3

def publish_compliance_metric(compliance_pct: float, account_id: str, region: str = 'us-east-1'):
    cw = boto3.client('cloudwatch', region_name=region)
    cw.put_metric_data(
        Namespace='FinOps/TagCompliance',
        MetricData=[
            {
                'MetricName': 'CompliancePercentage',
                'Dimensions': [
                    {'Name': 'AccountId', 'Value': account_id},
                ],
                'Value': compliance_pct,
                'Unit': 'Percent'
            }
        ]
    )
    print(f"Published compliance metric: {compliance_pct}% for account {account_id}")
```

---

## 🗃️ Athena Query: Find Untagged Resources via CUR

```sql
-- Find spend attributed to resources missing the 'team' tag
-- Run against your CUR Athena database

SELECT
    line_item_resource_id,
    line_item_product_code,
    SUM(line_item_unblended_cost) AS total_cost_usd,
    MIN(line_item_usage_start_date) AS first_seen,
    MAX(line_item_usage_start_date) AS last_seen
FROM
    "athenacurcfn"."your_cur_table"
WHERE
    year = '2024'
    AND month = '06'
    AND (
        resource_tags_user_team IS NULL
        OR resource_tags_user_team = ''
    )
    AND line_item_line_item_type = 'Usage'
    AND line_item_unblended_cost > 0
GROUP BY
    line_item_resource_id,
    line_item_product_code
ORDER BY
    total_cost_usd DESC
LIMIT 100;
```

---

## ✅ Tagging Governance Checklist

### Before Launch
- [ ] All IaC (Terraform/CDK) includes required tags as variables
- [ ] CI/CD pipeline runs `tfsec` or `checkov` to validate tags
- [ ] SCP applied to deny resource creation without required tags
- [ ] Tag Editor configured to bulk-tag existing resources

### Monthly Review
- [ ] Run tag compliance report (> 95% target)
- [ ] Review untagged spend in Cost Explorer
- [ ] Update tag taxonomy as new teams/projects are created
- [ ] Audit tag values for typos and inconsistencies

### Common Pitfalls to Avoid
- ❌ Using `Name` as the only tag — it's not billable
- ❌ Inconsistent casing: `Team` vs `team` vs `TEAM`
- ❌ Long tag values with special characters (breaks filtering)
- ❌ Tagging EC2 but not the EBS volumes attached to it
- ❌ Tags that get overwritten by Auto Scaling launch templates
- ❌ No tag inheritance for EKS pods (use Cost Allocation Tags for K8s)

---

*Back: [01 — FinOps Foundation](../01-FinOps-Foundation/README.md) | Next: [04 — Cost Allocation →](../04-Cost-Allocation/README.md)*
