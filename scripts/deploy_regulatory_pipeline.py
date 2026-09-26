#!/usr/bin/env python3
"""
Deploy the Regulatory Radar Pipeline as an AWS Lambda function + monthly EventBridge schedule.

Uses the SAME ECR image as the RAG demo and Radar Pipeline but overrides the handler CMD.
No new Docker build required.

Usage:
    uv run python scripts/deploy_regulatory_pipeline.py

Re-running is safe: updates existing resources instead of creating duplicates.

What this creates:
  - Lambda function   : ai-platform-regulatory-pipeline
  - EventBridge rule  : ai-platform-regulatory-monthly (1st of month, 07:00 UTC)

What this reuses (already exists from Phase 2 deploy):
  - IAM role          : ai-platform-lambda-role (with S3 + SNS policies already attached)
  - ECR image         : ai-platform-rag-demo:lambda
"""

import json
import sys
import time
from pathlib import Path

import boto3
from _secrets import ensure_secret_merged, grant_secret_read
from aiplatform.settings import settings

ACCOUNT_ID = "759302162548"
REGION = "eu-central-1"

FUNCTION_NAME = "ai-platform-regulatory-pipeline"
ECR_IMAGE = f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/ai-platform-rag-demo:lambda"
HANDLER_CMD = ["apps.regulatory_pipeline.lambda_handler.handler"]

ROLE_NAME = "ai-platform-lambda-role"          # shared with Phase 1 + Phase 2

# Shared across all non-corp Lambdas — see scripts/_secrets.py and
# aiplatform/secrets.py (which reads this same secret at cold start).
APP_SECRET_NAME = "ai-platform/app-secrets"
APP_SECRET_POLICY_NAME = "AppSecretsAccess"

EVENTBRIDGE_RULE_NAME = "ai-platform-regulatory-monthly"
EVENTBRIDGE_SCHEDULE = "cron(0 7 1 * ? *)"     # 1st of month, 07:00 UTC

_VPC_POLICY = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
_BASIC_POLICY = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"


def load_sns_config() -> str:
    path = Path("infra/sns_config.json")
    if not path.exists():
        print("  [info] infra/sns_config.json not found — notifications disabled")
        return ""
    config = json.loads(path.read_text())
    arn = config.get("topic_arn", "")
    print(f"  [ok] SNS topic: {arn}")
    return arn


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


def get_role_arn(iam) -> str:
    """Get the existing shared role — created by deploy_radar_pipeline.py."""
    try:
        role = iam.get_role(RoleName=ROLE_NAME)
        role_arn = role["Role"]["Arn"]
        print(f"  [ok] role '{ROLE_NAME}' found: {role_arn}")
        return role_arn
    except iam.exceptions.NoSuchEntityException:
        print(f"  [error] Role '{ROLE_NAME}' not found.")
        print("  Run scripts/deploy_radar_pipeline.py first to create the shared role.")
        sys.exit(1)


def build_env_vars() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "LLM_PROVIDER": settings.llm_provider,
        "OPENAI_CHAT_MODEL": settings.openai_chat_model,
        "OPENAI_EMBEDDING_MODEL": settings.openai_embedding_model,
        "OPENAI_EMBEDDING_DIMENSIONS": str(settings.openai_embedding_dimensions),
        "S3_BUCKET_NAME": settings.s3_bucket_name,
        "MAX_LLM_CALLS_PER_RUN": str(settings.max_llm_calls_per_run),
        "SNS_TOPIC_ARN": load_sns_config(),
    }


def sync_app_secret(sm, iam) -> None:
    secret_arn = ensure_secret_merged(
        sm,
        APP_SECRET_NAME,
        {
            "DATABASE_URL": settings.database_url,
            "OPENAI_API_KEY": settings.openai_api_key.get_secret_value(),
            "ANTHROPIC_API_KEY": settings.anthropic_api_key.get_secret_value(),
        },
    )
    grant_secret_read(iam, ROLE_NAME, APP_SECRET_POLICY_NAME, secret_arn)


def deploy_lambda(lmb, role_arn: str, env_vars: dict[str, str], vpc: dict | None) -> str:
    config: dict = {
        "Environment": {"Variables": env_vars},
        "Timeout": 300,
        "MemorySize": 512,
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
        Description="Trigger Regulatory Radar pipeline on the 1st of each month at 07:00 UTC",
    )
    rule_arn = rule["RuleArn"]
    print(f"  [ok] EventBridge rule '{EVENTBRIDGE_RULE_NAME}': {EVENTBRIDGE_SCHEDULE}")

    events.put_targets(
        Rule=EVENTBRIDGE_RULE_NAME,
        Targets=[{"Id": "regulatory-pipeline-target", "Arn": fn_arn}],
    )
    print("  [ok] Lambda target added to EventBridge rule")

    try:
        lmb.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId="eventbridge-regulatory-monthly",
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
    sm = boto3.client("secretsmanager", region_name=REGION)

    print("\n=== Step 0: VPC config ===")
    vpc = load_vpc_config()

    print("\n=== Step 1: IAM role (shared) ===")
    try:
        role_arn = get_role_arn(iam)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"  [error] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n=== Step 1b: App secret (Secrets Manager) ===")
    sync_app_secret(sm, iam)

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
        f"  VPC:      {vpc['vpc_id']} (private subnets)\n"
        f"  Subnets:  {vpc['subnets']['private-1a']}, {vpc['subnets']['private-1b']}"
    ) if vpc else "  VPC:      none"

    print(f"""
=== Deployment complete ===
  Function  : {FUNCTION_NAME}
  Handler   : {HANDLER_CMD[0]}
  Schedule  : {EVENTBRIDGE_SCHEDULE} (1st of month, 07:00 UTC)
  Timeout   : 300s
  Memory    : 512 MB
{vpc_note}

To trigger manually:
  aws lambda invoke --function-name {FUNCTION_NAME} --region {REGION} /tmp/regulatory_out.json && cat /tmp/regulatory_out.json
""")


if __name__ == "__main__":
    main()
