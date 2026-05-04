# SOC 2 Terraform Control Mapping

This MVP maps SOC 2 control intent to enforceable Terraform, policy checks, and automated evidence. The authoritative machine-readable mapping is `policies/soc2-terraform-controls.yml`.

| SOC 2 control | Control objective | Terraform enforcement | Evidence |
| --- | --- | --- | --- |
| CC6.1 | Restrict logical access to authorized paths. | No public ingress on the instance security group, locked-down default security group, SSM managed instance role. | `security-groups.json`, `ssm-instance-information.json` |
| CC6.6 | Protect data and metadata access. | Encrypted EC2 root volume, IMDSv2 required, KMS-encrypted VPC Flow Logs with key rotation. | `ec2-instance.json`, Terraform outputs |
| CC7.2 | Log security events. | VPC Flow Logs capture all traffic, encrypted CloudWatch log group, VPC reject metric filter. | CloudWatch dashboard, policy output |
| CC7.3 | Detect and alert on threats. | GuardDuty regional detector, EC2 status alarm, VPC reject alarm, compliance dashboard. | GuardDuty detector and CloudWatch dashboard exports |
| CC7.4 | Block and log unauthorized agent activity. | `POST /actions` policy decision API, asymmetric KMS audit signatures, hash-chained local audit state, encrypted CloudWatch audit log group, non-root systemd sandbox. | Agent audit KMS key, CloudWatch audit log events |
| CC8.1 | Validate infrastructure changes before release. | `make static`, `make policy`, and `make github-ready` guard the release path. | Policy output |
| A1.2 | Monitor availability and retain recovery access. | EC2 status alarm, SSM managed access, bootstrap verification JSON. | SSM instance data, `zt-verify.json` |

Run `make evidence` after a deployment to collect an immutable evidence bundle under `evidence/<timestamp>/`. Evidence bundles are local artifacts and are intentionally ignored by Git.
