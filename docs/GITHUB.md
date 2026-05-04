# GitHub Publishing Checklist

Use this checklist before creating a GitHub repository or pushing changes.

## Required Gate

```bash
make github-ready
```

This runs static validation, policy checks, and a publish safety scan.

For public release, also run full-history scanning with official scanner binaries:

```bash
gitleaks detect --source . --log-opts="--all"
trufflehog git file://. --since-commit=<FIRST_COMMIT>
```

If either scanner finds account IDs, ARNs, wallet addresses, transaction hashes,
local paths, secrets, Terraform state, generated keys, or evidence bundles in
history, decide whether to rewrite history before publishing.

## Must Not Be Published

These files are local runtime artifacts and must stay untracked:

- `terraform/terraform.tfstate`
- `terraform/terraform.tfstate.backup`
- `terraform/.terraform/`
- `out/`
- `logs/`
- `.venv/`
- `.pytest_cache/`
- `__pycache__/`
- `tailscale-auth-key`
- `.env`
- `evidence/`
- `artifacts/`
- `tmp/`
- `*.tfstate`
- `*.tfvars`

## Expected Publish Files

Commit source, tests, scripts, docs, GitHub Actions, and Terraform lock data:

- `.github/workflows/ci.yml`
- `.gitignore`
- `LICENSE`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `Makefile`
- `README.md`
- `AGENTS.md`
- `docs/`
- `landing/`
- `policies/`
- `provisioner/`
- `requirements-dev.txt`
- `scripts/`
- `terraform/*.tf`
- `terraform/.terraform.lock.hcl`
- `terraform/user-data.sh.tpl`
- `terraform/terraform.tfvars.example`
- `tests/`

## First Push From This Directory

This directory may not already be a git repository. Initialize it only after
`make github-ready` passes:

```bash
git init
git add .
git status --short
make github-ready
git commit -m "Prepare zero trust infrastructure MVP"
git branch -M main
git remote add origin git@github.com:<owner>/zt-infra-v2.git
git push -u origin main
```

Review `git status --short` before committing. If generated files appear, stop
and fix `.gitignore` before pushing.

## GitHub Settings

Before announcing a public repo:

- enable private vulnerability reporting;
- enable secret scanning and push protection;
- enable Dependabot alerts and security updates;
- require pull requests for `main`;
- require passing CI checks before merge;
- restrict workflow token permissions to least privilege.
