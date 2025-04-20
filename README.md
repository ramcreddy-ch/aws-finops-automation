# 💰 AWS FinOps Automation

[![Standard: FinOps](https://img.shields.io/badge/Standard-FinOps-green.svg)](https://www.finops.org/)
[![Cloud: AWS](https://img.shields.io/badge/Cloud-AWS-orange.svg)](https://aws.amazon.com/)

> Automated cloud financial management bots for resource optimization and waste reduction.

## 📈 Executive View

![Dashboard](dashboard.png)

This repository provides highly scalable Boto3-based automation to detect, report, and remediate unoptimized AWS resources, potentially saving up to 30% on monthly cloud spend.

## 🤖 Core Bots

- **`cleanup_snapshots.py`**: Intelligent lifecycle management for EBS snapshots.
- **`orphan_volume_reaper.py`**: Automated detection of unattached EBS volumes.
- **`s3_lifecycle_auditor.py`**: Enforces Tiering/Lifecycle policies on S3 buckets.

## ⚙️ Configuration

1. Copy `.env.example` to `.env`
2. Set your AWS region and threshold values.
3. Run `make install`

---
"Cloud is expensive only if you let it be." — **Ramchandra Chintala**
