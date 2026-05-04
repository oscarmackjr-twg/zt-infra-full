"""Live AWS integration tests.

Run after `make deploy` with AWS_PROFILE and AWS_REGION set.
These tests inspect Terraform outputs and query EC2/SSM metadata via boto3.
"""
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.exceptions import WaiterError
import requests

ROOT = Path(__file__).resolve().parents[1]
TF = ROOT / "terraform"


def tf_output_json():
    raw = subprocess.check_output(["terraform", "output", "-json"], cwd=TF, text=True)
    return json.loads(raw)


def aws_session():
    region = os.environ.get("AWS_REGION", "us-east-2")
    profile = os.environ.get("AWS_PROFILE")
    assert profile, "Set AWS_PROFILE before running live integration tests."
    return boto3.Session(profile_name=profile, region_name=region)


def instance_id():
    return tf_output_json()["instance_id"]["value"]


def wait_for_ssm_instance(ssm, target):
    deadline = time.time() + 600
    last = []
    while time.time() < deadline:
        last = ssm.describe_instance_information(
            Filters=[{"Key": "InstanceIds", "Values": [target]}]
        )["InstanceInformationList"]
        if last and last[0]["PingStatus"] == "Online":
            return last[0]
        time.sleep(10)
    raise AssertionError(f"Instance did not become SSM Online: {last}")


def run_ssm_shell(command):
    target = instance_id()
    session = aws_session()
    ssm = session.client("ssm")
    wait_for_ssm_instance(ssm, target)
    sent = ssm.send_command(
        InstanceIds=[target],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": [command]},
    )
    command_id = sent["Command"]["CommandId"]
    waiter = ssm.get_waiter("command_executed")
    try:
        waiter.wait(
            CommandId=command_id,
            InstanceId=target,
            WaiterConfig={"Delay": 5, "MaxAttempts": 120},
        )
        result = ssm.get_command_invocation(CommandId=command_id, InstanceId=target)
    except WaiterError:
        result = ssm.get_command_invocation(CommandId=command_id, InstanceId=target)
    assert result["Status"] == "Success", result.get("StandardErrorContent", "")
    return result["StandardOutputContent"]


def wait_for_verify_json():
    deadline = time.time() + 900
    last = None
    while time.time() < deadline:
        raw = run_ssm_shell("sudo test -f /var/log/zt-verify.json && sudo cat /var/log/zt-verify.json || true")
        if raw.strip():
            last = json.loads(raw)
            if last.get("bootstrap", {}).get("status") in {"ok", "failed"}:
                return last
        time.sleep(15)
    raise AssertionError(f"Verification JSON was not written: {last}")


def test_instance_is_running_and_has_no_public_ingress():
    target = instance_id()
    session = aws_session()
    ec2 = session.client("ec2")
    resp = ec2.describe_instances(InstanceIds=[target])
    inst = resp["Reservations"][0]["Instances"][0]
    assert inst["State"]["Name"] in {"pending", "running"}
    sg_ids = [sg["GroupId"] for sg in inst["SecurityGroups"]]
    sgs = ec2.describe_security_groups(GroupIds=sg_ids)["SecurityGroups"]
    for sg in sgs:
        assert sg.get("IpPermissions", []) == []


def test_live_network_guardrails_are_applied():
    target = instance_id()
    session = aws_session()
    ec2 = session.client("ec2")
    resp = ec2.describe_instances(InstanceIds=[target])
    inst = resp["Reservations"][0]["Instances"][0]
    vpc_id = inst["VpcId"]
    sg_ids = [sg["GroupId"] for sg in inst["SecurityGroups"]]
    sgs = ec2.describe_security_groups(GroupIds=sg_ids)["SecurityGroups"]
    for sg in sgs:
        assert sg.get("IpPermissions", []) == []
        assert not any(
            perm.get("IpProtocol") == "-1"
            and any(rng.get("CidrIp") == "0.0.0.0/0" for rng in perm.get("IpRanges", []))
            for perm in sg.get("IpPermissionsEgress", [])
        )

    default_sg = ec2.describe_security_groups(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "group-name", "Values": ["default"]},
        ]
    )["SecurityGroups"][0]
    assert default_sg.get("IpPermissions", []) == []
    assert default_sg.get("IpPermissionsEgress", []) == []

    flow_logs = ec2.describe_flow_logs(
        Filters=[{"Name": "resource-id", "Values": [vpc_id]}]
    )["FlowLogs"]
    assert any(log["TrafficType"] == "ALL" and log["LogDestinationType"] == "cloud-watch-logs" for log in flow_logs)


def test_live_instance_runtime_hardening_is_applied():
    target = instance_id()
    session = aws_session()
    ec2 = session.client("ec2")
    resp = ec2.describe_instances(InstanceIds=[target])
    inst = resp["Reservations"][0]["Instances"][0]

    assert inst["MetadataOptions"]["HttpTokens"] == "required"
    assert inst["MetadataOptions"]["InstanceMetadataTags"] == "disabled"

    volume_ids = [mapping["Ebs"]["VolumeId"] for mapping in inst["BlockDeviceMappings"] if "Ebs" in mapping]
    assert volume_ids
    volumes = ec2.describe_volumes(VolumeIds=volume_ids)["Volumes"]
    assert all(volume["Encrypted"] for volume in volumes)


def test_ssm_managed_instance_available():
    target = instance_id()
    session = aws_session()
    ssm = session.client("ssm")
    info = wait_for_ssm_instance(ssm, target)
    assert info["PingStatus"] == "Online"


def test_remote_verify_json_reports_zero_trust_services():
    verify = wait_for_verify_json()
    assert verify["project"] == "zt-infra-v2"
    if verify["bootstrap"]["status"] != "ok":
        attempts = verify["bootstrap"].get("self_healing_attempts", [])
        if any(
            attempt.get("action") == "tailscale-auth-key"
            and attempt.get("status") == "invalid"
            for attempt in attempts
        ):
            raise AssertionError(
                "Tailscale auth key was rejected. Rotate the AWS Secrets Manager "
                    "configured Tailscale Secrets Manager secret with a fresh reusable auth key, "
                "then run `make deploy && make verify`."
            )
        raise AssertionError(verify["bootstrap"])
    assert verify["tailscale"]["online"] is True, verify["tailscale"]
    assert verify["tailscale"]["dnsName"], verify["tailscale"]
    assert verify["serve_syntax"]["working"] in {
        "current-set-path",
        "current",
        "current-partial-target",
        "legacy-1.52",
    }, verify["serve_syntax"]
    assert verify["services"]["nginx"] == "active"
    assert verify["services"]["zt_provisioner"] == "active"


def test_remote_local_endpoints_and_tailscale_https():
    wait_for_verify_json()
    run_ssm_shell(
        "curl -fsS http://127.0.0.1/ >/dev/null && "
        "curl -fsS http://127.0.0.1:3000/health | jq -e '.ok == true' >/dev/null"
    )
    url = run_ssm_shell("sudo jq -r .test_url /var/log/zt-verify.json").strip().rstrip(".")
    host = urlparse(url).hostname
    assert url and host, (
        "No Tailscale HTTPS URL was written. Inspect logs/zt-verify.json; if "
        "tailscale-auth-key is invalid, rotate the AWS Secrets Manager secret "
        "and redeploy."
    )
    try:
        socket.getaddrinfo(host, 443)
        response = requests.get(url, timeout=20)
        assert response.status_code == 200
        assert "ZT Infra v2 MVP" in response.text
    except socket.gaierror:
        serve_status = json.loads(run_ssm_shell("tailscale serve status --json"))
        web = serve_status.get("Web", {})
        handlers = [
            handler
            for host_config in web.values()
            for handler in host_config.get("Handlers", {}).values()
        ]
        assert any(handler.get("Proxy") == "http://127.0.0.1:80" for handler in handlers)


def test_agent_control_plane_blocks_and_signs_unauthorized_action():
    wait_for_verify_json()
    raw = run_ssm_shell(
        "curl -sS -X POST http://127.0.0.1:3000/actions "
        "-H 'content-type: application/json' "
        "-d '{\"actor\":\"demo-agent\",\"action\":\"aws.ec2.terminate_instances\"}' "
        "| jq -c ."
    )
    body = json.loads(raw)
    assert body["ok"] is False
    assert body["decision"] == "deny"
    assert "terminate" in body["reason"].lower()
    assert len(body["audit"]["previous_hash"]) == 64
    assert len(body["audit"]["current_hash"]) == 64
    assert body["audit"]["kms_signature"]["algorithm"] == "ECDSA_SHA_256"
    assert body["audit"]["kms_signature"]["signature"]


def test_agent_control_plane_systemd_sandbox_is_enabled():
    wait_for_verify_json()
    raw = run_ssm_shell(
        "systemctl show zt-provisioner "
        "-p User -p Group -p NoNewPrivileges -p PrivateTmp "
        "-p ProtectSystem -p ProtectHome -p CapabilityBoundingSet "
        "-p RestrictAddressFamilies"
    )
    props = dict(line.split("=", 1) for line in raw.strip().splitlines() if "=" in line)
    assert props["User"] == "zt-provisioner"
    assert props["Group"] == "zt-provisioner"
    assert props["NoNewPrivileges"] == "yes"
    assert props["PrivateTmp"] == "yes"
    assert props["ProtectSystem"] == "strict"
    assert props["ProtectHome"] == "yes"
    assert props["CapabilityBoundingSet"] == ""
    assert "AF_INET" in props["RestrictAddressFamilies"]
    assert "AF_INET6" in props["RestrictAddressFamilies"]
    assert "AF_UNIX" in props["RestrictAddressFamilies"]
