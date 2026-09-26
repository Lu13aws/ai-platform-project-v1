"""
Phase 6 — Deploy Corporate API Lambda + API Gateway with Cognito JWT Authorizer.

Creates:
  - Lambda: ai-platform-corp-api (same ECR image, different handler)
  - API Gateway HTTP API: ai-platform-corp-api
  - Cognito JWT Authorizer on all /api/v1/corp/* routes (except /health)
  - IAM role: ai-platform-corp-lambda-role (separate from public role)

Usage:
    uv run python scripts/deploy_corp_api.py

Re-running is safe — updates existing resources.
"""

import json
import os
import sys
import time

import boto3
from _secrets import ensure_secret_merged

ACCOUNT_ID = "759302162548"
REGION = "eu-central-1"
FUNCTION_NAME = "ai-platform-corp-api"
HANDLER = "apps.corp_api.lambda_handler.handler"
ROLE_NAME = "ai-platform-corp-lambda-role"
API_NAME = "ai-platform-corp-api"

# Corp-only secret — covered by the CorpSecretsAccess IAM policy's
# ai-platform/corp-* wildcard (see create_or_get_role below), so this needs
# no new IAM grant, only the write. aiplatform/storage/corp_db.py and
# aiplatform/settings.py (via APP_SECRETS_NAME below) read it back at
# Lambda cold start — see aiplatform/secrets.py.
CORP_APP_SECRET_NAME = "ai-platform/corp-app-secrets"

# Same ECR image as all other Lambdas
ECR_REPO = f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/ai-platform-rag-demo"

# VPC config
VPC_SUBNET_IDS = ["subnet-0876141c2e0feca97", "subnet-03d4fde53ac4bd7e5"]
LAMBDA_SG_ID = "sg-0c9d9c6ec4dc513ad"

# Cognito
COGNITO_USER_POOL_ID = "eu-central-1_EAxyIp3WZ"
COGNITO_CLIENT_ID = "3vptapgfltcov01fo7enpld3it"
COGNITO_ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"

_BASIC_POLICY = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
_VPC_POLICY = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"

# Default throttle for the whole corp API (JWT routes, /health and the $default catch-all).
# Unauthenticated noise on /health and $default still invokes the Lambda, which shares the
# account-wide limit of 10 concurrent executions with all other functions.
_DEFAULT_THROTTLE = {"ThrottlingRateLimit": 5, "ThrottlingBurstLimit": 10}


def get_ecr_image_uri(ecr) -> str:
    """Get the latest image URI from ECR (same image as all other Lambdas)."""
    images = ecr.describe_images(
        repositoryName="ai-platform-rag-demo",
        filter={"tagStatus": "TAGGED"},
    )["imageDetails"]
    images.sort(key=lambda x: x["imagePushedAt"], reverse=True)
    tag = images[0]["imageTags"][0]
    uri = f"{ECR_REPO}:{tag}"
    print(f"  [ecr] using image: {uri}")
    return uri


def create_or_get_role(iam) -> str:
    try:
        role = iam.get_role(RoleName=ROLE_NAME)
        print(f"  [iam] role '{ROLE_NAME}' already exists")
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
    role_arn = role["Role"]["Arn"]

    for policy in [_BASIC_POLICY, _VPC_POLICY]:
        iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=policy)

    # Allow reading corp secrets from Secrets Manager
    secret_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["secretsmanager:GetSecretValue"],
            "Resource": f"arn:aws:secretsmanager:{REGION}:{ACCOUNT_ID}:secret:ai-platform/corp-*",
        }],
    })
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="CorpSecretsAccess",
        PolicyDocument=secret_policy,
    )

    print(f"  [iam] role '{ROLE_NAME}' created — waiting 15s for IAM propagation...")
    time.sleep(15)
    return role_arn


def sync_corp_secret(sm) -> None:
    corp_db_url = os.environ.get("CORP_DATABASE_URL")
    if not corp_db_url:
        print("ERROR: CORP_DATABASE_URL not set locally. Set it before running this script.")
        sys.exit(1)

    # corp_api never reads settings.database_url (it uses CORP_DATABASE_URL
    # via aiplatform.storage.corp_db exclusively) — but importing
    # aiplatform.settings anywhere in this Lambda (e.g. aiplatform.auth.cognito,
    # aiplatform.llm) still constructs the shared Settings object, and its
    # production validator rejects a still-default database_url. Reuse
    # CORP_DATABASE_URL as a syntactically-valid, never-actually-used value
    # for that unrelated field rather than weakening the validator for every
    # other Lambda that does depend on it.
    updates = {"CORP_DATABASE_URL": corp_db_url, "DATABASE_URL": corp_db_url}
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if openai_key:
        updates["OPENAI_API_KEY"] = openai_key
    if anthropic_key:
        updates["ANTHROPIC_API_KEY"] = anthropic_key
    if not openai_key and not anthropic_key:
        print(
            "WARNING: No LLM API key set locally (OPENAI_API_KEY or ANTHROPIC_API_KEY) "
            "— leaving any existing value in the secret untouched"
        )

    ensure_secret_merged(sm, CORP_APP_SECRET_NAME, updates)


def build_env_vars() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "APP_SECRETS_NAME": CORP_APP_SECRET_NAME,
        "LLM_PROVIDER": os.environ.get("LLM_PROVIDER", "openai"),
        "COGNITO_USER_POOL_ID": COGNITO_USER_POOL_ID,
        "COGNITO_CLIENT_ID": COGNITO_CLIENT_ID,
        "COGNITO_REGION": REGION,
        "REQUIRE_LLM": "true",
    }


def create_or_update_lambda(lambda_client, role_arn: str, image_uri: str) -> str:
    env_vars = build_env_vars()

    try:
        existing = lambda_client.get_function(FunctionName=FUNCTION_NAME)
        print(f"  [lambda] updating {FUNCTION_NAME}...")
        lambda_client.update_function_code(
            FunctionName=FUNCTION_NAME,
            ImageUri=image_uri,
        )
        waiter = lambda_client.get_waiter("function_updated")
        waiter.wait(FunctionName=FUNCTION_NAME)
        lambda_client.update_function_configuration(
            FunctionName=FUNCTION_NAME,
            ImageConfig={"Command": [HANDLER]},
            Environment={"Variables": env_vars},
            Timeout=30,
            MemorySize=512,
        )
        fn_arn = existing["Configuration"]["FunctionArn"]
    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"  [lambda] creating {FUNCTION_NAME}...")
        resp = lambda_client.create_function(
            FunctionName=FUNCTION_NAME,
            PackageType="Image",
            Code={"ImageUri": image_uri},
            Role=role_arn,
            ImageConfig={"Command": [HANDLER]},
            Environment={"Variables": env_vars},
            Timeout=30,
            MemorySize=512,
            VpcConfig={
                "SubnetIds": VPC_SUBNET_IDS,
                "SecurityGroupIds": [LAMBDA_SG_ID],
            },
        )
        fn_arn = resp["FunctionArn"]
        print(f"  [lambda] waiting for function to become active...")
        waiter = lambda_client.get_waiter("function_active")
        waiter.wait(FunctionName=FUNCTION_NAME)

    print(f"  [lambda] {FUNCTION_NAME} ready: {fn_arn}")
    return fn_arn


def create_or_get_api(apigw, fn_arn: str) -> tuple[str, str]:
    # Check if API already exists
    apis = apigw.get_apis(MaxResults="100")["Items"]
    for api in apis:
        if api["Name"] == API_NAME:
            api_id = api["ApiId"]
            endpoint = api["ApiEndpoint"]
            print(f"  [apigw] API already exists: {api_id} -> {endpoint}")
            return api_id, endpoint

    # Create new HTTP API
    api = apigw.create_api(
        Name=API_NAME,
        ProtocolType="HTTP",
        CorsConfiguration={
            "AllowOrigins": ["https://bridging-data.com", "https://www.bridging-data.com", "http://localhost:3000"],
            "AllowMethods": ["GET", "POST", "OPTIONS"],
            "AllowHeaders": ["Content-Type", "Authorization"],
            "MaxAge": 300,
        },
    )
    api_id = api["ApiId"]
    endpoint = api["ApiEndpoint"]
    print(f"  [apigw] created API: {api_id} -> {endpoint}")
    return api_id, endpoint


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


def setup_routes(apigw, lambda_client, api_id: str, auth_id: str, fn_arn: str) -> None:
    account_id = ACCOUNT_ID

    # Lambda integration
    integrations = apigw.get_integrations(ApiId=api_id)["Items"]
    integration_id = None
    for integ in integrations:
        if fn_arn in integ.get("IntegrationUri", ""):
            integration_id = integ["IntegrationId"]
            print(f"  [apigw] integration already exists: {integration_id}")
            break

    if not integration_id:
        integ = apigw.create_integration(
            ApiId=api_id,
            IntegrationType="AWS_PROXY",
            IntegrationUri=fn_arn,
            PayloadFormatVersion="2.0",
        )
        integration_id = integ["IntegrationId"]
        print(f"  [apigw] integration created: {integration_id}")

        # Grant API Gateway permission to invoke Lambda
        lambda_client.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId="AllowAPIGatewayInvoke",
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=f"arn:aws:execute-api:{REGION}:{account_id}:{api_id}/*/*",
        )

    # Routes: /health (no auth), everything else requires JWT
    existing_routes = {r["RouteKey"] for r in apigw.get_routes(ApiId=api_id)["Items"]}

    route_configs = [
        ("GET /api/v1/corp/health", False),
        ("POST /api/v1/corp/query", True),
        ("POST /api/v1/corp/ingest", True),
        ("GET /api/v1/corp/sources", True),
        ("GET /api/v1/corp/audit", True),
        ("GET /api/v1/corp/health/auth", True),
        ("$default", False),  # Catch-all for docs etc.
    ]

    for route_key, require_auth in route_configs:
        if route_key in existing_routes:
            print(f"  [apigw] route exists: {route_key}")
            continue
        kwargs = {
            "ApiId": api_id,
            "RouteKey": route_key,
            "Target": f"integrations/{integration_id}",
        }
        if require_auth:
            kwargs["AuthorizationType"] = "JWT"
            kwargs["AuthorizerId"] = auth_id
        else:
            kwargs["AuthorizationType"] = "NONE"

        apigw.create_route(**kwargs)
        print(f"  [apigw] route created: {route_key} (auth={require_auth})")

    # Deploy to $default stage
    try:
        apigw.create_stage(ApiId=api_id, StageName="$default", AutoDeploy=True)
        print("  [apigw] stage '$default' created with AutoDeploy")
    except apigw.exceptions.ConflictException:
        print("  [apigw] stage '$default' already exists")

    apigw.update_stage(ApiId=api_id, StageName="$default", DefaultRouteSettings=_DEFAULT_THROTTLE)
    print("  [apigw] default throttling applied (5 rps / burst 10)")


def main() -> None:
    iam = boto3.client("iam", region_name=REGION)
    lambda_client = boto3.client("lambda", region_name=REGION)
    ecr = boto3.client("ecr", region_name=REGION)
    apigw = boto3.client("apigatewayv2", region_name=REGION)
    sm = boto3.client("secretsmanager", region_name=REGION)

    print(f"Phase 6 — Deploy {FUNCTION_NAME}")
    print("=" * 50)

    image_uri = get_ecr_image_uri(ecr)
    role_arn = create_or_get_role(iam)
    sync_corp_secret(sm)
    fn_arn = create_or_update_lambda(lambda_client, role_arn, image_uri)
    api_id, endpoint = create_or_get_api(apigw, fn_arn)
    auth_id = create_or_get_authorizer(apigw, api_id)
    setup_routes(apigw, lambda_client, api_id, auth_id, fn_arn)

    print()
    print("=" * 50)
    print("Deploy complete.")
    print(f"  API endpoint: {endpoint}")
    print(f"  Health check: {endpoint}/api/v1/corp/health")
    print(f"  Authenticated: {endpoint}/api/v1/corp/health/auth")
    print()
    print("Next step — initialize corp DB schema:")
    print(f"  CORP_DATABASE_URL=<url> uv run python scripts/setup_corp_schema.py")


if __name__ == "__main__":
    main()
