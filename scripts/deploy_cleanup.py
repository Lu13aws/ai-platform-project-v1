#!/usr/bin/env python3
"""
Deploy the Cleanup Lambda + monthly EventBridge schedule.

Uses the SAME ECR image as the other Lambda functions.
No Docker rebuild required if image was already pushed.

Usage:
    uv run python scripts/deploy_cleanup.py

Schedule: 1st of every month at 03:00 UTC.
"""

import contextlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import boto3
from _aws import account_id
from _secrets import ensure_secret_merged, grant_secret_read

ACCOUNT_ID = account_id()
REGION = "eu-central-1"

FUNCTION_NAME = "ai-platform-cleanup"
ECR_IMAGE = f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/ai-platform-rag-demo:lambda"
HANDLER_CMD = ["apps.cleanup.lambda_handler.handler"]

ROLE_NAME = "ai-platform-lambda-role"
S3_POLICY_NAME = "ai-platform-s3-radar-write"
APP_SECRET_NAME = "ai-platform/app-secrets"  # same secret the other Lambdas use
APP_SECRET_POLICY_NAME = "AppSecretsAccess"

EVENTBRIDGE_RULE_NAME = "ai-platform-cleanup-monthly"
EVENTBRIDGE_SCHEDULE = "cron(0 3 1 * ? *)"   # 1st of every month at 03:00 UTC

_VPC_POLICY = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
_BASIC_POLICY = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"


def load_vpc_config() -> dict | None:
    path = Path("infra/vpc_config.json")
    if not path.exists():
        print("  [info] infra/vpc_config.json not found — deploying without VPC config")
        return None
    config = json.loads(path.read_text())
    print(f"  [ok] VPC config loaded: {config['vpc_id']}")
    return config


def build_vpc_config(vpc: dict) -> dict:
    return {
        "SubnetIds": [vpc["subnets"]["private-1a"], vpc["subnets"]["private-1b"]],
        "SecurityGroupIds": [vpc["security_groups"]["lambda"]],
    }


def ensure_role(iam) -> str:
    try:
        role_arn = iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]
        print(f"  [ok] role '{ROLE_NAME}' found")
    except iam.exceptions.NoSuchEntityException:
        assume_policy = json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }],
        })
        role_arn = iam.create_role(RoleName=ROLE_NAME, AssumeRolePolicyDocument=assume_policy)["Role"]["Arn"]
        iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=_BASIC_POLICY)
        print(f"  [ok] role '{ROLE_NAME}' created — waiting 15s for IAM propagation...")
        time.sleep(15)

    for policy_arn in [_BASIC_POLICY, _VPC_POLICY]:
        with contextlib.suppress(Exception):  # already attached
            iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=policy_arn)

    print("  [ok] managed policies confirmed")
    return role_arn


def sync_app_secret(sm, iam) -> None:
    """DATABASE_URL lives in Secrets Manager (shared secret), not in the Lambda environment."""
    from aiplatform.settings import settings

    if urlparse(settings.database_url).hostname in (None, "", "localhost", "127.0.0.1"):
        sys.exit("ERROR: DATABASE_URL points at a local database; refusing to write it to the shared secret.")
    secret_arn = ensure_secret_merged(sm, APP_SECRET_NAME, {"DATABASE_URL": settings.database_url})
    grant_secret_read(iam, ROLE_NAME, APP_SECRET_POLICY_NAME, secret_arn)


def build_env_vars() -> dict[str, str]:
    from aiplatform.settings import settings
    return {
        "APP_ENV": "production",
        "REQUIRE_LLM": "false",   # cleanup does not call the LLM
        "S3_BUCKET_NAME": settings.s3_bucket_name,
        # DATABASE_URL comes from Secrets Manager at cold start (aiplatform/secrets.py)
        # AWS credentials injected automatically via Lambda IAM role
    }


def deploy_lambda(lmb, role_arn: str, env_vars: dict[str, str], vpc: dict | None) -> str:
    config: dict = {
        "Environment": {"Variables": env_vars},
        "Timeout": 120,    # cleanup is fast — 2 minutes is plenty
        "MemorySize": 256,
        "ImageConfig": {"Command": HANDLER_CMD},
    }
    if vpc:
        config["VpcConfig"] = build_vpc_config(vpc)

    try:
        lmb.get_function(FunctionName=FUNCTION_NAME)
        lmb.update_function_code(FunctionName=FUNCTION_NAME, ImageUri=ECR_IMAGE)
        waiter = lmb.get_waiter("function_updated_v2")
        waiter.wait(FunctionName=FUNCTION_NAME)
        lmb.update_function_configuration(FunctionName=FUNCTION_NAME, **config)
        print(f"  [ok] function '{FUNCTION_NAME}' updated")
    except lmb.exceptions.ResourceNotFoundException:
        lmb.create_function(
            FunctionName=FUNCTION_NAME,
            PackageType="Image",
            Code={"ImageUri": ECR_IMAGE},
            Role=role_arn,
            **config,
        )
        print(f"  [ok] function '{FUNCTION_NAME}' created")

    print("  [wait] waiting for function to become active...")
    waiter = lmb.get_waiter("function_active_v2")
    waiter.wait(FunctionName=FUNCTION_NAME)

    fn = lmb.get_function(FunctionName=FUNCTION_NAME)
    return fn["Configuration"]["FunctionArn"]


def deploy_eventbridge(events, lmb, fn_arn: str) -> None:
    rule = events.put_rule(
        Name=EVENTBRIDGE_RULE_NAME,
        ScheduleExpression=EVENTBRIDGE_SCHEDULE,
        State="ENABLED",
        Description="Monthly cleanup: delete expired raw_articles and old radar reports from S3",
    )
    rule_arn = rule["RuleArn"]
    print(f"  [ok] EventBridge rule '{EVENTBRIDGE_RULE_NAME}': {EVENTBRIDGE_SCHEDULE}")

    events.put_targets(
        Rule=EVENTBRIDGE_RULE_NAME,
        Targets=[{"Id": "cleanup-target", "Arn": fn_arn}],
    )
    print("  [ok] Lambda target added to EventBridge rule")

    try:
        lmb.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId="eventbridge-cleanup-monthly",
            Action="lambda:InvokeFunction",
            Principal="events.amazonaws.com",
            SourceArn=rule_arn,
        )
        print("  [ok] Lambda permission granted to EventBridge")
    except lmb.exceptions.ResourceConflictException:
        print("  [ok] Lambda permission already exists")


def main() -> None:
    iam = boto3.client("iam", region_name=REGION)
    lmb = boto3.client("lambda", region_name=REGION)
    events = boto3.client("events", region_name=REGION)

    print("\n=== Step 0: VPC config ===")
    vpc = load_vpc_config()

    print("\n=== Step 1: IAM role ===")
    try:
        role_arn = ensure_role(iam)
    except Exception as exc:
        print(f"  [error] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n=== Step 1b: App secret (Secrets Manager) ===")
    sync_app_secret(boto3.client("secretsmanager", region_name=REGION), iam)

    print("\n=== Step 2: Lambda function ===")
    env_vars = build_env_vars()
    try:
        fn_arn = deploy_lambda(lmb, role_arn, env_vars, vpc)
    except Exception as exc:
        print(f"  [error] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n=== Step 3: EventBridge monthly schedule ===")
    try:
        deploy_eventbridge(events, lmb, fn_arn)
    except Exception as exc:
        print(f"  [error] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    vpc_note = (
        f"  VPC:      {vpc['vpc_id']} (private subnets)"
    ) if vpc else "  VPC:      none"

    print(f"""
=== Deployment complete ===
  Function  : {FUNCTION_NAME}
  Handler   : {HANDLER_CMD[0]}
  Schedule  : {EVENTBRIDGE_SCHEDULE} (1st of month, 03:00 UTC)
  Timeout   : 120s
  Memory    : 256 MB
{vpc_note}

To trigger manually:
  aws lambda invoke --function-name {FUNCTION_NAME} --region {REGION} "$env:TEMP\\cleanup_out.json"; Get-Content "$env:TEMP\\cleanup_out.json"
""")


if __name__ == "__main__":
    main()
