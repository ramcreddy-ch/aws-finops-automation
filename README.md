# AWS FinOps Automation

Automated scripts to detect and remediate cloud cost anomalies.

## Features
- **EBS**: Identify unattached volumes.
- **S3**: Report buckets without lifecycle policies.
- **RDS**: List idle db instances.

## Architecture
Runs on AWS Lambda triggered by EventBridge every week.
