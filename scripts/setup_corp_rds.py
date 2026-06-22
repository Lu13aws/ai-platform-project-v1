"""
Phase 6 — Provision separate RDS instance for Corporate LLM Prototype.

Creates:
  - Security group: ai-platform-corp-rds-sg
  - RDS subnet group: ai-platform-corp-subnet-group (reuses private subnets)
  - RDS instance: ai-platform-db-corp (PostgreSQL 16, db.t3.micro)

Idempotent — safe to re-run.

Usage:
    uv run python scripts/setup_corp_rds.py
"""

import boto3
import time

REGION = "eu-central-1"
ACCOUNT_ID = "759302162548"

VPC_ID = "vpc-07f835a61e67a0271"
PRIVATE_SUBNETS = ["subnet-0876141c2e0feca97", "subnet-03d4fde53ac4bd7e5"]  # 1a + 1b
LAMBDA_SG_ID = "sg-0c9d9c6ec4dc513ad"  # ai-platform-lambda-sg

DB_IDENTIFIER = "ai-platform-db-corp"
DB_NAME = "aiplatform_corp"
DB_USERNAME = "aiplatform"
SUBNET_GROUP_NAME = "ai-platform-corp-subnet-group"
CORP_SG_NAME = "ai-platform-corp-rds-sg"


def get_or_create_security_group(ec2) -> str:
    existing = ec2.describe_security_groups(
        Filters=[
            {"Name": "group-name", "Values": [CORP_SG_NAME]},
            {"Name": "vpc-id", "Values": [VPC_ID]},
        ]
    )["SecurityGroups"]

    if existing:
        sg_id = existing[0]["GroupId"]
        print(f"[sg] already exists: {sg_id}")
        return sg_id

    sg = ec2.create_security_group(
        GroupName=CORP_SG_NAME,
        Description="RDS security group for Corporate LLM Prototype (Phase 6)",
        VpcId=VPC_ID,
    )
    sg_id = sg["GroupId"]

    # Allow port 5432 from Lambda SG only
    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": 5432,
            "ToPort": 5432,
            "UserIdGroupPairs": [{"GroupId": LAMBDA_SG_ID}],
        }],
    )
    print(f"[sg] created: {sg_id} (port 5432 from Lambda SG only)")
    return sg_id


def get_or_create_subnet_group(rds) -> None:
    try:
        rds.describe_db_subnet_groups(DBSubnetGroupName=SUBNET_GROUP_NAME)
        print(f"[subnet-group] already exists: {SUBNET_GROUP_NAME}")
    except rds.exceptions.DBSubnetGroupNotFoundFault:
        rds.create_db_subnet_group(
            DBSubnetGroupName=SUBNET_GROUP_NAME,
            DBSubnetGroupDescription="Private subnets for Corporate LLM RDS (Phase 6)",
            SubnetIds=PRIVATE_SUBNETS,
        )
        print(f"[subnet-group] created: {SUBNET_GROUP_NAME}")


def get_or_create_rds(rds, sg_id: str) -> dict:
    try:
        resp = rds.describe_db_instances(DBInstanceIdentifier=DB_IDENTIFIER)
        instance = resp["DBInstances"][0]
        print(f"[rds] already exists: {DB_IDENTIFIER}")
        return instance
    except rds.exceptions.DBInstanceNotFoundFault:
        pass

    import secrets
    db_password = secrets.token_urlsafe(24)

    print(f"[rds] creating {DB_IDENTIFIER} — this takes 5-10 minutes...")
    rds.create_db_instance(
        DBInstanceIdentifier=DB_IDENTIFIER,
        DBName=DB_NAME,
        DBInstanceClass="db.t3.micro",
        Engine="postgres",
        EngineVersion="16",
        MasterUsername=DB_USERNAME,
        MasterUserPassword=db_password,
        DBSubnetGroupName=SUBNET_GROUP_NAME,
        VpcSecurityGroupIds=[sg_id],
        MultiAZ=False,
        StorageType="gp2",
        AllocatedStorage=20,
        PubliclyAccessible=False,
        StorageEncrypted=True,
        DeletionProtection=False,
        Tags=[
            {"Key": "Project", "Value": "ai-platform"},
            {"Key": "Phase", "Value": "6"},
            {"Key": "Purpose", "Value": "corp-llm-prototype"},
        ],
    )

    print(f"[rds] waiting for {DB_IDENTIFIER} to become available...")
    waiter = rds.get_waiter("db_instance_available")
    waiter.wait(DBInstanceIdentifier=DB_IDENTIFIER, WaiterConfig={"Delay": 30, "MaxAttempts": 30})

    resp = rds.describe_db_instances(DBInstanceIdentifier=DB_IDENTIFIER)
    instance = resp["DBInstances"][0]
    endpoint = instance["Endpoint"]["Address"]

    print(f"[rds] ready: {endpoint}:5432")
    print()
    print("=" * 60)
    print("IMPORTANT — save these credentials NOW:")
    print(f"  Host:     {endpoint}")
    print(f"  Port:     5432")
    print(f"  DB:       {DB_NAME}")
    print(f"  Username: {DB_USERNAME}")
    print(f"  Password: {db_password}")
    print()
    print("Add to Lambda environment variables:")
    print(f"  CORP_DATABASE_URL=postgresql+asyncpg://{DB_USERNAME}:{db_password}@{endpoint}:5432/{DB_NAME}?ssl=require")
    print(f"  CORP_ALEMBIC_DATABASE_URL=postgresql://{DB_USERNAME}:{db_password}@{endpoint}:5432/{DB_NAME}?sslmode=require")
    print("=" * 60)

    return instance


def main():
    ec2 = boto3.client("ec2", region_name=REGION)
    rds = boto3.client("rds", region_name=REGION)

    print("Phase 6 — Corporate RDS Setup")
    print("=" * 40)

    sg_id = get_or_create_security_group(ec2)
    get_or_create_subnet_group(rds)
    get_or_create_rds(rds, sg_id)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
