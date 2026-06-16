#!/usr/bin/env python3
"""
Deploy the RAG demo as an AWS Lambda container + API Gateway HTTP API.

Usage:
    uv run python scripts/deploy_lambda.py

Re-running is safe: updates existing function/API instead of creating duplicates.
"""

import json
import sys
import time

import boto3

from aiplatform.settings import settings

ACCOUNT_ID = "759302162548"
REGION = "eu-central-1"
FUNCTION_NAME = "ai-platform-rag-demo"
ECR_IMAGE = f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/ai-platform-rag-demo:lambda"
ROLE_NAME = "ai-platform-lambda-role"


def create_or_get_role(iam: boto3.client) -> str:
    try:
        role = iam.get_role(RoleName=ROLE_NAME)
        print(f"  [ok] role '{ROLE_NAME}' already exists")
        return role["Role"]["Arn"]
    except iam.exceptions.NoSuchEntityException:
        pass

    assume_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    })
    role = iam.create_role(RoleName=ROLE_NAME, AssumeRolePolicyDocument=assume_policy)
    iam.attach_role_policy(
        RoleName=ROLE_NAME,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    )
    print(f"  [ok] role '{ROLE_NAME}' created — waiting 15s for IAM propagation...")
    time.sleep(15)
    return role["Role"]["Arn"]


def build_env_vars() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "DATABASE_URL": settings.database_url,
        "OPENAI_API_KEY": settings.openai_api_key.get_secret_value(),
        "LLM_PROVIDER": settings.llm_provider,
        "OPENAI_CHAT_MODEL": settings.openai_chat_model,
        "OPENAI_EMBEDDING_MODEL": settings.openai_embedding_model,
        "OPENAI_EMBEDDING_DIMENSIONS": str(settings.openai_embedding_dimensions),
        "RETRIEVAL_SIMILARITY_THRESHOLD": str(settings.retrieval_similarity_threshold),
        "MAX_CHUNKS_PER_DOC": str(settings.max_chunks_per_doc),
    }


def deploy_lambda(lmb: boto3.client, role_arn: str, env_vars: dict[str, str]) -> str:
    config = {
        "Environment": {"Variables": env_vars},
        "Timeout": 60,
        "MemorySize": 512,
    }
    try:
        lmb.get_function(FunctionName=FUNCTION_NAME)
        lmb.update_function_code(FunctionName=FUNCTION_NAME, ImageUri=ECR_IMAGE)
        # wait for code update to finish before updating config
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


def deploy_api_gateway(apigw: boto3.client, lmb: boto3.client, fn_arn: str) -> str:
    apis = apigw.get_apis()
    existing = next((a for a in apis["Items"] if a["Name"] == FUNCTION_NAME), None)
    if existing:
        print(f"  [ok] API already exists: {existing['ApiEndpoint']}")
        return existing["ApiEndpoint"]

    api = apigw.create_api(
        Name=FUNCTION_NAME,
        ProtocolType="HTTP",
        Target=fn_arn,
        CorsConfiguration={
            "AllowOrigins": ["https://bridging-data.com", "http://localhost:3000"],
            "AllowMethods": ["GET", "POST"],
            "AllowHeaders": ["Content-Type", "Authorization"],
        },
    )
    api_id = api["ApiId"]
    api_url = api["ApiEndpoint"]

    lmb.add_permission(
        FunctionName=FUNCTION_NAME,
        StatementId="apigateway-invoke",
        Action="lambda:InvokeFunction",
        Principal="apigateway.amazonaws.com",
        SourceArn=f"arn:aws:execute-api:{REGION}:{ACCOUNT_ID}:{api_id}/*/*",
    )
    print(f"  [ok] API Gateway created: {api_url}")
    return api_url


def main() -> None:
    iam = boto3.client("iam", region_name=REGION)
    lmb = boto3.client("lambda", region_name=REGION)
    apigw = boto3.client("apigatewayv2", region_name=REGION)

    print("\n=== Step 1: IAM execution role ===")
    role_arn = create_or_get_role(iam)

    print("\n=== Step 2: Lambda function ===")
    env_vars = build_env_vars()
    try:
        fn_arn = deploy_lambda(lmb, role_arn, env_vars)
    except Exception as exc:
        print(f"  [error] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n=== Step 3: API Gateway HTTP API ===")
    try:
        api_url = deploy_api_gateway(apigw, lmb, fn_arn)
    except Exception as exc:
        print(f"  [error] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"""
=== Deployment complete ===
  Function : {FUNCTION_NAME}
  API URL  : {api_url}
  Health   : {api_url}/health
  Docs     : {api_url}/docs
  Query    : {api_url}/api/v1/query
""")


if __name__ == "__main__":
    main()
