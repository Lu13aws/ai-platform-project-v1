#!/usr/bin/env python3
"""
Set up VPC infrastructure for AI Platform Phase 2+.

Architecture:
  New VPC (10.0.0.0/16)
    Public subnets  (eu-central-1a/b) → Internet Gateway  → internet
    Private subnets (eu-central-1a/b) → NAT Gateway       → internet (Lambda outbound)

  RDS stays in its current location (public endpoint, existing default VPC).
  Lambda outbound traffic exits via the NAT Gateway Elastic IP, which is
  whitelisted in the RDS security group — no RDS migration required.

Security groups:
  ai-platform-lambda-sg  outbound all, no inbound
  ai-platform-rds-sg     port 5432 from: NAT EIP + developer home IP only
                         (removes the existing 0.0.0.0/0 rule)

Usage:
    uv run python scripts/setup_vpc.py

Re-running is safe: existing resources are found by tag and reused.
Output saved to infra/vpc_config.json (gitignored).
"""

import json
import urllib.request
from pathlib import Path

import boto3
from _aws import account_id
from botocore.exceptions import ClientError

REGION = "eu-central-1"
ACCOUNT_ID = account_id()
PROJECT = "ai-platform"

VPC_CIDR = "10.0.0.0/16"
SUBNETS = {
    "public-1a":  {"cidr": "10.0.0.0/24", "az": "eu-central-1a"},
    "public-1b":  {"cidr": "10.0.1.0/24", "az": "eu-central-1b"},
    "private-1a": {"cidr": "10.0.2.0/24", "az": "eu-central-1a"},
    "private-1b": {"cidr": "10.0.3.0/24", "az": "eu-central-1b"},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def tag_spec(resource_type: str, name: str) -> list[dict]:
    return [{
        "ResourceType": resource_type,
        "Tags": [
            {"Key": "Name", "Value": f"{PROJECT}-{name}"},
            {"Key": "Project", "Value": PROJECT},
        ],
    }]


def get_developer_ip() -> str:
    with urllib.request.urlopen("https://checkip.amazonaws.com", timeout=5) as r:
        ip = r.read().decode().strip()
    print(f"  [ok] Developer IP: {ip}")
    return ip


def _safe_authorize(ec2, sg_id: str, cidr: str, description: str) -> None:
    try:
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{
                "IpProtocol": "tcp",
                "FromPort": 5432,
                "ToPort": 5432,
                "IpRanges": [{"CidrIp": cidr, "Description": description}],
            }],
        )
        print(f"  [ok] Added {description} ({cidr})")
    except ClientError as e:
        if "InvalidPermission.Duplicate" in str(e):
            print(f"  [ok] Rule already exists: {description}")
        else:
            raise


def _safe_associate(ec2, rt_id: str, subnet_id: str) -> None:
    try:
        ec2.associate_route_table(RouteTableId=rt_id, SubnetId=subnet_id)
    except ClientError as e:
        if "Resource.AlreadyAssociated" not in str(e):
            raise


# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------

def get_or_create_vpc(ec2) -> str:
    vpcs = ec2.describe_vpcs(Filters=[
        {"Name": "tag:Name", "Values": [f"{PROJECT}-vpc"]},
    ])["Vpcs"]
    if vpcs:
        vpc_id = vpcs[0]["VpcId"]
        print(f"  [ok] VPC exists: {vpc_id}")
        return vpc_id

    vpc_id = ec2.create_vpc(
        CidrBlock=VPC_CIDR,
        TagSpecifications=tag_spec("vpc", "vpc"),
    )["Vpc"]["VpcId"]
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={"Value": True})
    print(f"  [ok] VPC created: {vpc_id}")
    return vpc_id


# ---------------------------------------------------------------------------
# Subnets
# ---------------------------------------------------------------------------

def get_or_create_subnets(ec2, vpc_id: str) -> dict[str, str]:
    subnet_ids: dict[str, str] = {}
    for name, cfg in SUBNETS.items():
        existing = ec2.describe_subnets(Filters=[
            {"Name": "tag:Name", "Values": [f"{PROJECT}-{name}"]},
            {"Name": "vpc-id", "Values": [vpc_id]},
        ])["Subnets"]
        if existing:
            sid = existing[0]["SubnetId"]
            print(f"  [ok] Subnet {name} exists: {sid}")
        else:
            sid = ec2.create_subnet(
                VpcId=vpc_id,
                CidrBlock=cfg["cidr"],
                AvailabilityZone=cfg["az"],
                TagSpecifications=tag_spec("subnet", name),
            )["Subnet"]["SubnetId"]
            print(f"  [ok] Subnet {name} created: {sid}")
        subnet_ids[name] = sid
    return subnet_ids


# ---------------------------------------------------------------------------
# Internet Gateway
# ---------------------------------------------------------------------------

def get_or_create_igw(ec2, vpc_id: str) -> str:
    igws = ec2.describe_internet_gateways(Filters=[
        {"Name": "attachment.vpc-id", "Values": [vpc_id]},
        {"Name": "tag:Project", "Values": [PROJECT]},
    ])["InternetGateways"]
    if igws:
        igw_id = igws[0]["InternetGatewayId"]
        print(f"  [ok] Internet Gateway exists: {igw_id}")
        return igw_id

    igw_id = ec2.create_internet_gateway(
        TagSpecifications=tag_spec("internet-gateway", "igw"),
    )["InternetGateway"]["InternetGatewayId"]
    ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
    print(f"  [ok] Internet Gateway created: {igw_id}")
    return igw_id


# ---------------------------------------------------------------------------
# Elastic IP + NAT Gateway
# ---------------------------------------------------------------------------

def get_or_create_eip(ec2) -> tuple[str, str]:
    """Returns (AllocationId, PublicIp)."""
    eips = ec2.describe_addresses(Filters=[
        {"Name": "tag:Name", "Values": [f"{PROJECT}-nat-eip"]},
    ])["Addresses"]
    if eips:
        alloc_id = eips[0]["AllocationId"]
        public_ip = eips[0]["PublicIp"]
        print(f"  [ok] Elastic IP exists: {public_ip} ({alloc_id})")
        return alloc_id, public_ip

    resp = ec2.allocate_address(
        Domain="vpc",
        TagSpecifications=tag_spec("elastic-ip", "nat-eip"),
    )
    print(f"  [ok] Elastic IP allocated: {resp['PublicIp']} ({resp['AllocationId']})")
    return resp["AllocationId"], resp["PublicIp"]


def get_or_create_nat_gw(ec2, public_subnet_id: str, eip_alloc_id: str) -> str:
    existing = ec2.describe_nat_gateways(Filters=[
        {"Name": "subnet-id", "Values": [public_subnet_id]},
        {"Name": "state", "Values": ["pending", "available"]},
        {"Name": "tag:Project", "Values": [PROJECT]},
    ])["NatGateways"]

    if existing:
        nat_gw_id = existing[0]["NatGatewayId"]
        print(f"  [ok] NAT Gateway exists: {nat_gw_id} — waiting for available state...")
    else:
        nat_gw_id = ec2.create_nat_gateway(
            SubnetId=public_subnet_id,
            AllocationId=eip_alloc_id,
            TagSpecifications=tag_spec("natgateway", "nat-gw"),
        )["NatGateway"]["NatGatewayId"]
        print(f"  [ok] NAT Gateway created: {nat_gw_id} — waiting (~2 min)...")

    ec2.get_waiter("nat_gateway_available").wait(NatGatewayIds=[nat_gw_id])
    print(f"  [ok] NAT Gateway available: {nat_gw_id}")
    return nat_gw_id


# ---------------------------------------------------------------------------
# Route Tables
# ---------------------------------------------------------------------------

def get_or_create_route_tables(
    ec2,
    vpc_id: str,
    igw_id: str,
    nat_gw_id: str,
    subnet_ids: dict[str, str],
) -> dict[str, str]:
    rt_ids: dict[str, str] = {}

    for rt_name, dest_kwarg, subnets in [
        ("public-rt",  {"GatewayId": igw_id},       ["public-1a",  "public-1b"]),
        ("private-rt", {"NatGatewayId": nat_gw_id}, ["private-1a", "private-1b"]),
    ]:
        existing = ec2.describe_route_tables(Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "tag:Name", "Values": [f"{PROJECT}-{rt_name}"]},
        ])["RouteTables"]

        if existing:
            rt_id = existing[0]["RouteTableId"]
            print(f"  [ok] Route table {rt_name} exists: {rt_id}")
        else:
            rt_id = ec2.create_route_table(
                VpcId=vpc_id,
                TagSpecifications=tag_spec("route-table", rt_name),
            )["RouteTable"]["RouteTableId"]
            ec2.create_route(
                RouteTableId=rt_id,
                DestinationCidrBlock="0.0.0.0/0",
                **dest_kwarg,
            )
            print(f"  [ok] Route table {rt_name} created: {rt_id}")

        for name in subnets:
            _safe_associate(ec2, rt_id, subnet_ids[name])

        rt_ids[rt_name.replace("-rt", "")] = rt_id

    return rt_ids


# ---------------------------------------------------------------------------
# Security Groups
# ---------------------------------------------------------------------------

def get_or_create_lambda_sg(ec2, vpc_id: str) -> str:
    existing = ec2.describe_security_groups(Filters=[
        {"Name": "vpc-id", "Values": [vpc_id]},
        {"Name": "group-name", "Values": [f"{PROJECT}-lambda-sg"]},
    ])["SecurityGroups"]
    if existing:
        sg_id = existing[0]["GroupId"]
        print(f"  [ok] Lambda SG exists: {sg_id}")
        return sg_id

    sg_id = ec2.create_security_group(
        GroupName=f"{PROJECT}-lambda-sg",
        Description="AI Platform Lambda functions - outbound all, no inbound",
        VpcId=vpc_id,
        TagSpecifications=tag_spec("security-group", "lambda-sg"),
    )["GroupId"]
    print(f"  [ok] Lambda SG created: {sg_id}")
    return sg_id


def update_rds_sg(ec2, nat_eip: str, developer_ip: str) -> str:
    """
    Update the existing ai-platform-rds-sg:
      - Remove 0.0.0.0/0 on port 5432
      - Allow NAT Gateway Elastic IP (Lambda outbound)
      - Allow developer home IP (local dev + Alembic migrations)
    """
    sgs = ec2.describe_security_groups(Filters=[
        {"Name": "group-name", "Values": [f"{PROJECT}-rds-sg"]},
    ])["SecurityGroups"]
    if not sgs:
        raise RuntimeError(
            f"{PROJECT}-rds-sg not found. Has Phase 1 been deployed?\n"
            "Run scripts/deploy_lambda.py first to create the RDS security group."
        )

    sg_id = sgs[0]["GroupId"]
    print(f"  [ok] RDS SG found: {sg_id}")

    # Remove 0.0.0.0/0 if still present
    try:
        ec2.revoke_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{
                "IpProtocol": "tcp",
                "FromPort": 5432,
                "ToPort": 5432,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            }],
        )
        print("  [ok] Removed 0.0.0.0/0 from RDS SG")
    except ClientError as e:
        if "InvalidPermission.NotFound" in str(e):
            print("  [ok] 0.0.0.0/0 rule already removed")
        else:
            raise

    _safe_authorize(ec2, sg_id, f"{nat_eip}/32", "NAT Gateway EIP - Lambda outbound")
    _safe_authorize(ec2, sg_id, f"{developer_ip}/32", "Developer home IP")

    return sg_id


# ---------------------------------------------------------------------------
# Config output
# ---------------------------------------------------------------------------

def save_config(config: dict) -> None:
    path = Path("infra/vpc_config.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2))
    print(f"\n  Config saved → {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ec2 = boto3.client("ec2", region_name=REGION)

    print("\n=== Step 1: Developer IP ===")
    developer_ip = get_developer_ip()

    print("\n=== Step 2: VPC ===")
    vpc_id = get_or_create_vpc(ec2)

    print("\n=== Step 3: Subnets ===")
    subnet_ids = get_or_create_subnets(ec2, vpc_id)

    print("\n=== Step 4: Internet Gateway ===")
    igw_id = get_or_create_igw(ec2, vpc_id)

    print("\n=== Step 5: Elastic IP ===")
    eip_alloc_id, nat_eip = get_or_create_eip(ec2)

    print("\n=== Step 6: NAT Gateway (~2 min) ===")
    nat_gw_id = get_or_create_nat_gw(ec2, subnet_ids["public-1a"], eip_alloc_id)

    print("\n=== Step 7: Route Tables ===")
    rt_ids = get_or_create_route_tables(ec2, vpc_id, igw_id, nat_gw_id, subnet_ids)

    print("\n=== Step 8: Lambda Security Group ===")
    lambda_sg_id = get_or_create_lambda_sg(ec2, vpc_id)

    print("\n=== Step 9: RDS Security Group ===")
    rds_sg_id = update_rds_sg(ec2, nat_eip, developer_ip)

    config = {
        "region": REGION,
        "account_id": ACCOUNT_ID,
        "vpc_id": vpc_id,
        "subnets": subnet_ids,
        "nat_gateway_id": nat_gw_id,
        "nat_eip": nat_eip,
        "route_tables": rt_ids,
        "security_groups": {
            "lambda": lambda_sg_id,
            "rds": rds_sg_id,
        },
    }
    save_config(config)

    print(f"""
=== VPC Setup Complete ===
  VPC:             {vpc_id}
  Public subnets:  {subnet_ids['public-1a']}, {subnet_ids['public-1b']}
  Private subnets: {subnet_ids['private-1a']}, {subnet_ids['private-1b']}
  NAT Gateway:     {nat_gw_id}
  Elastic IP:      {nat_eip}  ← whitelisted in RDS SG
  Lambda SG:       {lambda_sg_id}
  RDS SG:          {rds_sg_id}

RDS security group updated:
  ✓ Removed 0.0.0.0/0
  ✓ Allowed NAT Gateway EIP ({nat_eip}) - Lambda outbound traffic
  ✓ Allowed developer IP ({developer_ip}) - local dev + Alembic migrations

Next step:
  Update deploy_lambda.py with VPC config from infra/vpc_config.json,
  then redeploy: uv run python scripts/deploy_lambda.py
""")


if __name__ == "__main__":
    main()
