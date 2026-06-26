# 16 — SageMaker FinOps

> *SageMaker provides managed ML environments, but convenience comes at a premium. A SageMaker instance generally costs 20-30% more than the equivalent raw EC2 instance.*

---

## 🛑 SageMaker Studio / Notebook Waste

The most common SageMaker waste is data scientists leaving Studio Apps or Notebook instances running 24/7.
A single `ml.g5.4xlarge` notebook left on all month costs $1,475.

### Automation: Stop Idle SageMaker Resources

```python
# 25-Automation/lambda_functions/sagemaker_idle_stopper.py
"""
Identifies and stops SageMaker Notebook Instances and Studio Apps
that are running outside of business hours or haven't been active.
"""
import boto3
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def stop_idle_notebooks(sm_client):
    notebooks = sm_client.list_notebook_instances(StatusEquals='InService')['NotebookInstances']
    stopped = 0
    
    for nb in notebooks:
        name = nb['NotebookInstanceName']
        tags = sm_client.list_tags(ResourceArn=nb['NotebookInstanceArn'])['Tags']
        tag_dict = {t['Key']: t['Value'] for t in tags}
        
        # Skip if tagged to run 24/7
        if tag_dict.get('FinOps:Retain', '').lower() == 'true':
            continue
            
        logger.info(f"Stopping idle notebook: {name}")
        sm_client.stop_notebook_instance(NotebookInstanceName=name)
        stopped += 1
        
    return stopped

def lambda_handler(event, context):
    sm = boto3.client('sagemaker')
    
    # Example logic: Stop standard notebooks
    stopped_notebooks = stop_idle_notebooks(sm)
    
    # You would also list and delete/stop Studio Apps (JupyterServer, KernelGateway)
    # sm.list_apps() -> sm.delete_app() (Studio Apps are deleted, not stopped, to stop billing)
    
    return {"stopped_notebooks": stopped_notebooks}
```

---

## 🎓 Managed Spot Training

Training jobs take hours or days. You can use Managed Spot Training to save up to **90%** on training costs.

**How to implement (Boto3):**
```python
import sagemaker

# Enable Managed Spot Training
estimator = sagemaker.estimator.Estimator(
    image_uri=train_model_uri,
    role=role,
    instance_count=1,
    instance_type='ml.p3.2xlarge',
    use_spot_instances=True,        # <-- KEY SETTING
    max_run=3600,
    max_wait=7200,                  # <-- Required for Spot
    checkpoint_s3_uri=f"s3://{bucket}/checkpoints" # <-- Critical for resuming
)
```

---

## 🚀 Endpoint Optimization (Inference)

Real-time inference endpoints run 24/7.
1. **Serverless Inference:** If your endpoint gets < 1 request per minute, use SageMaker Serverless Inference. It scales to zero.
2. **Multi-Model Endpoints (MME):** If you have 50 different models serving low traffic, do NOT deploy 50 endpoints. Deploy 1 Multi-Model Endpoint that loads models into memory on demand.
3. **Auto-Scaling:** ALL provisioned endpoints must have an Auto Scaling policy attached.

---

## ✅ SageMaker Checklist
- [ ] Enforce auto-shutdown scripts (Lifecycle Configurations) for all SageMaker Studio and Notebook instances.
- [ ] Ensure all training jobs > 1 hour use `use_spot_instances=True` and S3 Checkpointing.
- [ ] Migrate rarely-used real-time endpoints to Serverless Inference.
- [ ] Consolidate multiple low-traffic models onto Multi-Model Endpoints (MME).
