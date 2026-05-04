SHELL := /usr/bin/env bash
AWS_PROFILE ?= default
AWS_REGION ?= us-east-2
PROJECT_NAME ?= zt-infra
TAILSCALE_SECRET_NAME ?= $(PROJECT_NAME)/tailscale-auth-key
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
TF_VAR_aws_profile ?= $(AWS_PROFILE)
TF_VAR_aws_region ?= $(AWS_REGION)
TF_VAR_project_name ?= $(PROJECT_NAME)
TF_VAR_tailscale_secret_name ?= $(TAILSCALE_SECRET_NAME)
TF_VAR_allowed_aws_account_id ?=
export AWS_PROFILE AWS_REGION PROJECT_NAME TAILSCALE_SECRET_NAME TF_VAR_aws_profile TF_VAR_aws_region TF_VAR_project_name TF_VAR_tailscale_secret_name TF_VAR_allowed_aws_account_id

.PHONY: help preflight init fmt validate static policy test github-ready deploy live verify fetch-logs evidence destroy provisioner clean-policy

help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-18s %s\n", $$1, $$2}'

preflight: ## Verify local tools, AWS identity, and Tailscale secret
	./scripts/preflight.sh

init: ## Terraform init
	cd terraform && terraform init

fmt: ## Terraform fmt
	cd terraform && terraform fmt -recursive

validate: init ## Terraform validate
	cd terraform && terraform validate

policy: ## Run policy-as-code guardrails with Checkov and tfsec when installed
	./scripts/policy-scan.sh

static: fmt validate ## Static repo and Terraform checks
	$(PYTHON) -m pytest tests/test_static_repo.py tests/test_bootstrap_simulation.py tests/test_langgraph_plugin.py tests/test_openai_assistants_wrapper.py tests/test_openai_responses_wrapper.py tests/test_openai_agents_sdk_guardrail.py tests/test_mcp_zero_trust_gateway.py tests/test_a2a_policy_proxy.py tests/test_interoperability_demo_contract.py

test: static policy ## Run static and policy checks

github-ready: static policy ## Check that the repo is safe to publish to GitHub
	./scripts/github-ready.sh

provisioner: ## Run local Node provisioner
	cd provisioner && npm install && npm start

deploy: preflight init ## Deploy live AWS MVP
	./scripts/deploy.sh

live: ## Run live integration tests after deploy
	$(PYTHON) -m pytest tests/test_live_integration.py

verify: ## Verify live AWS deployment and retrieve remote logs
	@status=0; \
	$(PYTHON) -m pytest tests/test_live_integration.py || status=$$?; \
	./scripts/fetch-logs.sh || status=$$?; \
	if [ $$status -ne 0 ]; then \
		echo ""; \
		echo "verify failed. If logs/zt-verify.json reports tailscale-auth-key=invalid, rotate $$TAILSCALE_SECRET_NAME with a fresh reusable key, then run: make deploy && make verify"; \
	fi; \
	exit $$status

fetch-logs: ## Fetch bootstrap and verify logs over SSM
	./scripts/fetch-logs.sh

evidence: ## Collect SOC 2 deployment evidence through Terraform, AWS CLI, and SSM
	./scripts/collect-evidence.sh

destroy: ## Destroy AWS infrastructure
	./scripts/destroy.sh

clean-policy: ## Remove local policy scanner cache folders
	rm -rf .external_modules .checkov .tfsec
