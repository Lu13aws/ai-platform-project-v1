#!/usr/bin/env python3
"""
Deploy the Radar Pipeline as an AWS Lambda function + weekly EventBridge schedule.

Uses the SAME ECR image as the RAG demo but overrides the handler CMD.
No new Docker build required — just a new Lambda function pointing to a different handler.

Usage:
    uv run python scripts/deploy_radar_pipeline.py

Re-running is safe: updates existing resources instead of creating duplicates.

What this creates:
  - Lambda function   : ai-platform-radar-pipeline
  - EventBridge rule  : ai-platform-radar-weekly (Monday 06:00 UTC)
  - IAM inline policy : S3 write access for radar report uploads
"""

import json
import sys
import time
from pathlib import Path

import boto3

from aiplatform.settings import settings

ACCOUNT_ID = "759302162548"
REGION = "eu-central-1"

FUNCTION_NAME = "ai-platform-radar-pipeline"
ECR_IMAGE = f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/ai-platform-rag-demo:lambda"
HANDLER_CMD = ["apps.radar_pipeline.lambda_handler.handler"]

ROLE_NAME = "ai-platform-lambda-role"          # shared with RAG demo
S3_POLICY_NAME = "ai-platform-s3-radar-write"  # inline policy on the role

EVENTBRIDGE_RULE_NAME = "ai-platform-radar-weekly"
EVENTBRIDGE_SCHEDULE = "cron(0 6 ? * MON *)"   # Monday 06:00 UTC

SNS_POLICY_NAME = "ai-platform-sns-radar-publish"

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


def ensure_role(iam) -> str:
    """Get existing shared role and attach required policies."""
    try:
        role = iam.get_role(RoleName=ROLE_NAME)
        role_arn = role["Role"]["Arn"]
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
        role = iam.create_role(RoleName=ROLE_NAME, AssumeRolePolicyDocument=assume_policy)
        role_arn = role["Role"]["Arn"]
        iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=_BASIC_POLICY)
        print(f"  [ok] role '{ROLE_NAME}' created — waiting 15s for IAM propagation...")
        time.sleep(15)

    # VPC access
    try:
        iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=_VPC_POLICY)
        print("  [ok] AWSLambdaVPCAccessExecutionRole attached")
    except Exception:
        print("  [ok] AWSLambdaVPCAccessExecutionRole already attached")

    # S3 write for radar report uploads
    s3_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:HeadObject"],
            "Resource": f"arn:aws:s3:::{settings.s3_bucket_name}/*",
        }],
    })
    iam.put_role_policy(RoleName=ROLE_NAME, PolicyName=S3_POLICY_NAME, PolicyDocument=s3_policy)
    print(f"  [ok] inline S3 policy '{S3_POLICY_NAME}' applied")

    # SNS publish for pipeline notifications
    sns_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": "sns:Publish",
            "Resource": f"arn:aws:sns:{REGION}:{ACCOUNT_ID}:ai-platform-radar-notifications",
        }],
    })
    iam.put_role_policy(RoleName=ROLE_NAME, PolicyName=SNS_POLICY_NAME, PolicyDocument=sns_policy)
    print(f"  [ok] inline SNS policy '{SNS_POLICY_NAME}' applied")

    return role_arn


def build_env_vars() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "DATABASE_URL": settings.database_url,
        "OPENAI_API_KEY": settings.openai_api_key.get_secret_value(),
        "ANTHROPIC_API_KEY": settings.anthropic_api_key.get_secret_value(),
        "LLM_PROVIDER": settings.llm_provider,
        "OPENAI_CHAT_MODEL": settings.openai_chat_model,
        "OPENAI_EMBEDDING_MODEL": settings.openai_embedding_model,
        "OPENAI_EMBEDDING_DIMENSIONS": str(settings.openai_embedding_dimensions),
        "S3_BUCKET_NAME": settings.s3_bucket_name,
        "MAX_LLM_CALLS_PER_RUN": str(settings.max_llm_calls_per_run),
        "SNS_TOPIC_ARN": load_sns_config(),
    }


def deploy_lambda(lmb, role_arn: str, env_vars: dict[str, str], vpc: dict | None) -> str:
    config: dict = {
        "Environment": {"Variables": env_vars},
        "Timeout": 300,    # 5 minutes — allows ~100 LLM calls
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
    # Create or update the schedule rule
    rule = events.put_rule(
        Name=EVENTBRIDGE_RULE_NAME,
        ScheduleExpression=EVENTBRIDGE_SCHEDULE,
        State="ENABLED",
        Description="Trigger Technology Radar pipeline every Monday at 06:00 UTC",
    )
    rule_arn = rule["RuleArn"]
    print(f"  [ok] EventBridge rule '{EVENTBRIDGE_RULE_NAME}': {EVENTBRIDGE_SCHEDULE}")

    # Add Lambda as target
    events.put_targets(
        Rule=EVENTBRIDGE_RULE_NAME,
        Targets=[{
            "Id": "radar-pipeline-target",
            "Arn": fn_arn,
        }],
    )
    print("  [ok] Lambda target added to EventBridge rule")

    # Allow EventBridge to invoke the Lambda
    try:
        lmb.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId="eventbridge-radar-weekly",
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

    print("\n=== Step 1: IAM role + S3 policy ===")
    try:
        role_arn = ensure_role(iam)
    except Exception as exc:
        print(f"  [error] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n=== Step 2: Lambda function ===")
    env_vars = build_env_vars()
    try:
        fn_arn = deploy_lambda(lmb, role_arn, env_vars, vpc)
    except Exception as exc:
        print(f"  [error] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n=== Step 3: EventBridge weekly schedule ===")
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
  Schedule  : {EVENTBRIDGE_SCHEDULE} (Monday 06:00 UTC)
  Timeout   : 300s
  Memory    : 512 MB
{vpc_note}

To trigger manually:
  aws lambda invoke --function-name {FUNCTION_NAME} --region {REGION} /tmp/radar_out.json && cat /tmp/radar_out.json
""")


if __name__ == "__main__":
    main()
