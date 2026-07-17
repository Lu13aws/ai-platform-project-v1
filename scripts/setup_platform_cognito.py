"""
Session 6A — Create public Cognito User Pool for platform.bridging-data.com.

Self-registration + email verification + no admin approval.
Run once:
    uv run python scripts/setup_platform_cognito.py
"""

import boto3

REGION = "eu-central-1"


def get_or_create_group(cognito, pool_id: str, group_name: str, description: str) -> None:
    try:
        cognito.get_group(UserPoolId=pool_id, GroupName=group_name)
        print(f"Group already exists: {group_name}")
    except cognito.exceptions.ResourceNotFoundException:
        cognito.create_group(
            UserPoolId=pool_id,
            GroupName=group_name,
            Description=description,
        )
        print(f"Group created: {group_name}")


def main() -> None:
    cognito = boto3.client("cognito-idp", region_name=REGION)

    # Check if pool already exists
    pools = cognito.list_user_pools(MaxResults=60)["UserPools"]
    existing = next((p for p in pools if p["Name"] == "ai-platform-public"), None)
    if existing:
        pool_id = existing["Id"]
        print(f"User pool already exists: {pool_id}")
    else:
        resp = cognito.create_user_pool(
            PoolName="ai-platform-public",
            Policies={
                "PasswordPolicy": {
                    "MinimumLength": 8,
                    "RequireUppercase": True,
                    "RequireLowercase": True,
                    "RequireNumbers": True,
                    "RequireSymbols": False,
                }
            },
            AutoVerifiedAttributes=["email"],
            UsernameAttributes=["email"],
            EmailVerificationMessage="Your AI Knowledge Platform verification code is {####}",
            EmailVerificationSubject="Verify your AI Knowledge Platform account",
            UsernameConfiguration={"CaseSensitive": False},
            AdminCreateUserConfig={"AllowAdminCreateUserOnly": False},
        )
        pool_id = resp["UserPool"]["Id"]
        print(f"Created user pool: {pool_id}")

    # App client (no secret — browser-based auth)
    clients = cognito.list_user_pool_clients(UserPoolId=pool_id, MaxResults=60)["UserPoolClients"]
    existing_client = next((c for c in clients if c["ClientName"] == "platform-ui"), None)
    if existing_client:
        client_id = existing_client["ClientId"]
        print(f"App client already exists: {client_id}")
    else:
        resp = cognito.create_user_pool_client(
            UserPoolId=pool_id,
            ClientName="platform-ui",
            GenerateSecret=False,
            ExplicitAuthFlows=[
                "ALLOW_USER_PASSWORD_AUTH",
                "ALLOW_REFRESH_TOKEN_AUTH",
            ],
        )
        client_id = resp["UserPoolClient"]["ClientId"]
        print(f"Created app client: {client_id}")

    # Admin group — gates the knowledge-platform management routes
    # (LinkedIn review/publish, ingest-skill, cross-namespace query). Not
    # auto-assigned to anyone; add specific users via the console or
    # admin_add_user_to_group after running this.
    get_or_create_group(
        cognito, pool_id, "corp-admins", "Admin access to knowledge platform management routes"
    )

    print("\n--- Add these to .env.local ---")
    print(f"NEXT_PUBLIC_PLATFORM_COGNITO_USER_POOL_ID={pool_id}")
    print(f"NEXT_PUBLIC_PLATFORM_COGNITO_CLIENT_ID={client_id}")
    print(f"NEXT_PUBLIC_PLATFORM_COGNITO_REGION={REGION}")


if __name__ == "__main__":
    main()
