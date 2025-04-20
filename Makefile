.PHONY: help install test deploy logs

help:
	@echo "AWS FinOps Automation CLI"
	@echo "  install - Install Python dependencies"
	@echo "  test    - Run cost bot simulation"
	@echo "  deploy  - Suite of Lambda deployment commands"
	@echo "  logs    - Stream CloudWatch logs"

install:
	pip install -r requirements.txt

test:
	python scripts/cleanup_snapshots.py

deploy:
	# Placeholder for SAM or Terraform deployment
	terraform apply -auto-approve

logs:
	aws logs tail /aws/lambda/finops-cost-bot --follow
