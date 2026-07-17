#!/usr/bin/env python3
"""
Deploy the RAG demo as an AWS Lambda container + API Gateway HTTP API.

Usage:
    uv run python scripts/deploy_lambda.py

Re-running is safe: updates existing function/API instead of creating duplicates.

VPC: if infra/vpc_config.json exists (created by setup_vpc.py), Lambda is deployed
into the private subnets. Otherwise deploys without VPC config (backwards compatible).
"""

import json
import sys
import time
from pathlib import Path

import boto3

from aiplatform.settings import settings

ACCOUNT_ID = "759302162548"
REGION = "eu-central-1"
FUNCTION_NAME = "ai-platform-rag-demo"
ECR_IMAGE = f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/ai-platform-rag-demo:lambda"
ROLE_NAME = "ai-platform-lambda-role"

_VPC_POLICY = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
_BASIC_POLICY = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

# Cognito — the *public* pool (apps/knowledge_platform + apps/rag_demo both
# authenticate against this one; it is NOT the same pool apps/corp_api uses,
# see scripts/deploy_corp_api.py / scripts/setup_platform_cognito.py).
COGNITO_USER_POOL_ID = "eu-central-1_FPrGewp3l"
COGNITO_CLIENT_ID = "52gsvhl73b3bvaigpmrfbknltq"
COGNITO_ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"

# Routes that must require a valid Cognito JWT: the 5 LinkedIn admin routes
# plus the 3 previously-unauthenticated ingest/query routes. Everything else
# (health checks, /docs, other rag_demo routes) stays on the quick-create
# $default route at AuthorizationType=NONE — HTTP APIs let explicit routes
# coexist with, and take precedence over, $default, so this list only needs
# to name what actually requires auth.
_PROTECTED_ROUTES = [
    "GET /api/v1/kp/linkedin",
    "PATCH /api/v1/kp/linkedin/{post_id}",
    "POST /api/v1/kp/linkedin/{post_id}/regenerate",
    "POST /api/v1/kp/linkedin/{post_id}/publish",
    "DELETE /api/v1/kp/linkedin/{post_id}",
    "POST /api/v1/kp/ingest-skill",
    "POST /api/v1/kp/query",
    "POST /api/v1/ingest",
]


def load_vpc_config() -> dict | None:
    path = Path("infra/vpc_config.json")
    if not path.exists():
        print("  [info] infra/vpc_config.json not found — deploying without VPC config")
        return None
    config = json.loads(path.read_text())
    print(f"  [ok] VPC config loaded: {config['vpc_id']}")
    return config


def create_or_get_role(iam, use_vpc: bool) -> str:
    try:
        role = iam.get_role(RoleName=ROLE_NAME)
        role_arn = role["Role"]["Arn"]
        print(f"  [ok] role '{ROLE_NAME}' already exists")
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

    # Attach VPC policy when deploying into a VPC — idempotent, safe to call repeatedly
    if use_vpc:
        try:
            iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=_VPC_POLICY)
            print(f"  [ok] attached AWSLambdaVPCAccessExecutionRole")
        except iam.exceptions.EntityAlreadyExistsException:
            print(f"  [ok] AWSLambdaVPCAccessExecutionRole already attached")

    return role_arn


def build_env_vars() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "DATABASE_URL": settings.database_url,
        "ALEMBIC_DATABASE_URL": settings.alembic_database_url,
        "OPENAI_API_KEY": settings.openai_api_key.get_secret_value(),
        "LLM_PROVIDER": settings.llm_provider,
        "OPENAI_CHAT_MODEL": settings.openai_chat_model,
        "OPENAI_EMBEDDING_MODEL": settings.openai_embedding_model,
        "OPENAI_EMBEDDING_DIMENSIONS": str(settings.openai_embedding_dimensions),
        "RETRIEVAL_SIMILARITY_THRESHOLD": str(settings.retrieval_similarity_threshold),
        "MAX_CHUNKS_PER_DOC": str(settings.max_chunks_per_doc),
    }


def build_vpc_config(vpc: dict) -> dict:
    return {
        "SubnetIds": [
            vpc["subnets"]["private-1a"],
            vpc["subnets"]["private-1b"],
        ],
        "SecurityGroupIds": [vpc["security_groups"]["lambda"]],
    }


def deploy_lambda(lmb, role_arn: str, env_vars: dict[str, str], vpc: dict | None) -> str:
    config: dict = {
        "Environment": {"Variables": env_vars},
        "Timeout": 60,
        "MemorySize": 512,
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


def deploy_api_gateway(apigw, lmb, fn_arn: str) -> tuple[str, str]:
    apis = apigw.get_apis()
    existing = next((a for a in apis["Items"] if a["Name"] == FUNCTION_NAME), None)
    if existing:
        print(f"  [ok] API already exists: {existing['ApiEndpoint']}")
        return existing["ApiId"], existing["ApiEndpoint"]

    api = apigw.create_api(
        Name=FUNCTION_NAME,
        ProtocolType="HTTP",
        Target=fn_arn,
        CorsConfiguration={
            "AllowOrigins": [
                "https://bridging-data.com",
                "https://www.bridging-data.com",
                "http://localhost:3000",
            ],
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
    return api_id, api_url


def create_or_get_authorizer(apigw, api_id: str) -> str:
    authorizers = apigw.get_authorizers(ApiId=api_id)["Items"]
    for auth in authorizers:
        if auth["Name"] == "cognito-jwt":
            print(f"  [apigw] authorizer already exists: {auth['AuthorizerId']}")
            return auth["AuthorizerId"]

    auth = apigw.create_authorizer(
        ApiId=api_id,
        Name="cognito-jwt",
        AuthorizerType="JWT",
        IdentitySource=["$request.header.Authorization"],
        JwtConfiguration={
            "Audience": [COGNITO_CLIENT_ID],
            "Issuer": COGNITO_ISSUER,
        },
    )
    auth_id = auth["AuthorizerId"]
    print(f"  [apigw] JWT authorizer created: {auth_id}")
    return auth_id


def setup_protected_routes(apigw, lmb, api_id: str, auth_id: str, fn_arn: str) -> None:
    # The quick-create integration from deploy_api_gateway should already
    # cover this Lambda — reuse it if discoverable, same lookup-by-ARN
    # deploy_corp_api.py's setup_routes uses. If it isn't (quick-create's
    # integration doesn't always behave like an explicitly-created one),
    # fall back to creating a second integration pointed at the same
    # function rather than failing — HTTP APIs allow more than one
    # integration per Lambda, and $default keeps using whichever one it
    # already has.
    integrations = apigw.get_integrations(ApiId=api_id)["Items"]
    integration_id = next(
        (i["IntegrationId"] for i in integrations if fn_arn in i.get("IntegrationUri", "")),
        None,
    )
    if integration_id is None:
        integ = apigw.create_integration(
            ApiId=api_id,
            IntegrationType="AWS_PROXY",
            IntegrationUri=fn_arn,
            PayloadFormatVersion="2.0",
        )
        integration_id = integ["IntegrationId"]
        print(f"  [apigw] integration created: {integration_id}")
        lmb.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId="apigateway-invoke-protected",
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=f"arn:aws:execute-api:{REGION}:{ACCOUNT_ID}:{api_id}/*/*",
        )
    else:
        print(f"  [apigw] integration already exists: {integration_id}")

    existing_routes = {r["RouteKey"] for r in apigw.get_routes(ApiId=api_id)["Items"]}
    for route_key in _PROTECTED_ROUTES:
        if route_key in existing_routes:
            print(f"  [apigw] route exists: {route_key}")
            continue
        apigw.create_route(
            ApiId=api_id,
            RouteKey=route_key,
            Target=f"integrations/{integration_id}",
            AuthorizationType="JWT",
            AuthorizerId=auth_id,
        )
        print(f"  [apigw] route created: {route_key} (auth=JWT)")


def main() -> None:
    iam = boto3.client("iam", region_name=REGION)
    lmb = boto3.client("lambda", region_name=REGION)
    apigw = boto3.client("apigatewayv2", region_name=REGION)

    print("\n=== Step 0: VPC config ===")
    vpc = load_vpc_config()

    print("\n=== Step 1: IAM execution role ===")
    role_arn = create_or_get_role(iam, use_vpc=vpc is not None)

    print("\n=== Step 2: Lambda function ===")
    env_vars = build_env_vars()
    try:
        fn_arn = deploy_lambda(lmb, role_arn, env_vars, vpc)
    except Exception as exc:
        print(f"  [error] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n=== Step 3: API Gateway HTTP API ===")
    try:
        api_id, api_url = deploy_api_gateway(apigw, lmb, fn_arn)
    except Exception as exc:
        print(f"  [error] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n=== Step 4: Cognito JWT authorizer on sensitive routes ===")
    try:
        auth_id = create_or_get_authorizer(apigw, api_id)
        setup_protected_routes(apigw, lmb, api_id, auth_id, fn_arn)
    except Exception as exc:
        print(f"  [error] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    vpc_note = (
        f"  VPC:     {vpc['vpc_id']} (private subnets)\n"
        f"  Subnets: {vpc['subnets']['private-1a']}, {vpc['subnets']['private-1b']}\n"
        f"  Lambda SG: {vpc['security_groups']['lambda']}"
    ) if vpc else "  VPC:     none"

    print(f"""
=== Deployment complete ===
  Function : {FUNCTION_NAME}
  API URL  : {api_url}
  Health   : {api_url}/health
  Docs     : {api_url}/docs
  Query    : {api_url}/api/v1/query
{vpc_note}
""")


if __name__ == "__main__":
    main()
