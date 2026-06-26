# 14 — GPU Cost Optimization

> *GPU instances (P, G, and Trn families) are the most expensive compute resources in AWS. A single p4d.24xlarge costs over $23,000 per month. Optimizing GPU workloads requires specialized metrics and instance selection.*

---

## 🚀 GPU Instance Selection Guide (2024)

Matching the right GPU to the workload is where 80% of savings happen.

| Instance Family | GPU Model | Primary Use Case | Cost Profile |
|---|---|---|---|
| **g4dn** | NVIDIA T4 | ML Inference, Graphics, Small training | Lowest cost ($0.52/hr) |
| **g5** | NVIDIA A10G | Med/Large Inference, LoRA tuning | High perf/price ($1.00/hr) |
| **p3** | NVIDIA V100 | Legacy training (Avoid for new workloads) | Expensive, outdated |
| **p4d** | NVIDIA A100 | Large LLM training, massive datasets | Very expensive ($32.77/hr) |
| **p5** | NVIDIA H100 | State-of-the-art foundation model training | Premium ($98.32/hr) |
| **trn1** | AWS Trainium | Deep learning training (AWS Silicon) | Up to 50% cheaper than A100 |
| **inf2** | AWS Inferentia2 | High-performance inference (LLMs) | Lowest cost per inference |

**Rule of Thumb:**
- If you are deploying inference for an LLM (e.g., Llama 3), test **inf2** first. It can be 40-50% cheaper than the equivalent `g5` instance for the same throughput.
- Do not use `p3` or `p4` for inference. Use `g5` or `inf2`.

---

## 📊 Monitoring GPU Utilization (DCGM)

CloudWatch does NOT monitor GPU utilization out-of-the-box. You must install the CloudWatch Agent with the NVIDIA Data Center GPU Manager (DCGM).

**If you don't monitor GPU utilization, you are guaranteed to be wasting money.**

```json
// CloudWatch Agent Configuration for GPU (amazon-cloudwatch-agent.json)
{
  "agent": {
    "metrics_collection_interval": 60
  },
  "metrics": {
    "metrics_collected": {
      "nvidia_gpu": {
        "measurement": [
          "utilization_gpu",
          "utilization_memory",
          "temperature_gpu",
          "power_draw"
        ]
      }
    },
    "append_dimensions": {
      "InstanceId": "${aws:InstanceId}"
    }
  }
}
```

---

## 💸 GPU Spot & Capacity Optimization

GPU Spot instances can save up to 70%, but they have the highest interruption rates on AWS (often > 20% during peak AI hype cycles).

### Architecture for Spot GPU Training
1. **Checkpointing:** Your training script must write checkpoints to S3/EFS every X steps.
2. **Diversification:** Never request only `p4d`. Request a mix of `p4d`, `p3dn`, and `trn1` if your framework supports it.
3. **Availability Zones:** Let the Auto Scaling Group select the AZ with the deepest Spot pool.

```python
# Terraform ASG Spot Configuration for GPUs
# Note the use of capacity-optimized allocation to minimize interruptions
```
```hcl
resource "aws_autoscaling_group" "gpu_training" {
  name = "gpu-training-spot-fleet"
  
  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "capacity-optimized"
    }
    
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.gpu_base.id
        version            = "$Latest"
      }
      
      # Diversify across GPU instance types that fit the VRAM requirement
      override { instance_type = "g5.12xlarge" }
      override { instance_type = "g5.24xlarge" }
      override { instance_type = "p3.8xlarge" }
    }
  }
}
```

---

## 🛑 GPU Waste Detection Script

```python
# scripts/gpu_waste_detector.py
"""
Scans for GPU instances running with low utilization.
Requires CloudWatch Agent with nvidia_gpu metrics configured.
"""
import boto3
from datetime import datetime, timezone, timedelta

def find_idle_gpus(region='us-east-1'):
    ec2 = boto3.client('ec2', region_name=region)
    cw = boto3.client('cloudwatch', region_name=region)
    
    # Get all running GPU instances
    gpus = ec2.describe_instances(
        Filters=[
            {'Name': 'instance-state-name', 'Values': ['running']},
            {'Name': 'instance-type', 'Values': ['p*', 'g*', 'trn*', 'inf*']}
        ]
    )
    
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=3) # Look back 3 days
    
    idle_gpus = []
    
    for res in gpus['Reservations']:
        for inst in res['Instances']:
            instance_id = inst['InstanceId']
            instance_type = inst['InstanceType']
            
            # Check GPU utilization metric
            metrics = cw.get_metric_statistics(
                Namespace='CWAgent',
                MetricName='utilization_gpu',
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                StartTime=start, EndTime=end, Period=3600, Statistics=['Average', 'Maximum']
            )
            
            if not metrics.get('Datapoints'):
                idle_gpus.append((instance_id, instance_type, "NO_METRICS (Blind!)"))
                continue
                
            avg_util = sum(d['Average'] for d in metrics['Datapoints']) / len(metrics['Datapoints'])
            max_util = max(d['Maximum'] for d in metrics['Datapoints'])
            
            if avg_util < 10.0 and max_util < 50.0:
                idle_gpus.append((instance_id, instance_type, f"Avg: {avg_util:.1f}%, Max: {max_util:.1f}%"))
                
    for g in idle_gpus:
        print(f"IDLE GPU WARNING: {g[0]} ({g[1]}) - {g[2]}")
```

---

## ✅ GPU Optimization Checklist
- [ ] Install CloudWatch Agent + DCGM on all GPU instances.
- [ ] Test AWS Inferentia (`inf2`) for all inference workloads before using `g5` or `p4`.
- [ ] Ensure all training jobs are resumable from checkpoints.
- [ ] Use Spot instances for non-time-critical training and data processing.
- [ ] Schedule Auto Scaling to terminate development GPU instances at 6 PM local time.
