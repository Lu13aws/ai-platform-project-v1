"""
Phase 6 — Provision Cognito User Pool for Corporate LLM Prototype.

Creates:
  - User Pool: ai-platform-corp-users
  - App Client: ai-platform-corp-client (for frontend)
  - Groups: admin, demo_user
  - Admin user: luciano.10@hotmail.de

Idempotent — safe to re-run.

Usage:
    uv run python scripts/setup_corp_cognito.py
"""

import boto3
import json

REGION = "eu-central-1"
POOL_NAME = "ai-platform-corp-users"
CLIENT_NAME = "ai-platform-corp-client"
ADMIN_EMAIL = "luciano.10@hotmail.de"


def get_or_create_user_pool(cognito) -> str:
    # Check if pool already exists
    paginator = cognito.get_paginator("list_user_pools")
    for page in paginator.paginate(MaxResults=60):
        for pool in page["UserPools"]:
            if pool["Name"] == POOL_NAME:
                pool_id = pool["Id"]
                print(f"[cognito] user pool already exists: {pool_id}")
                return pool_id

    resp = cognito.create_user_pool(
        PoolName=POOL_NAME,
        Policies={
            "PasswordPolicy": {
                "MinimumLength": 12,
                "RequireUppercase": True,
                "RequireLowercase": True,
                "RequireNumbers": True,
                "RequireSymbols": False,
                "TemporaryPasswordValidityDays": 7,
            }
        },
        AutoVerifiedAttributes=["email"],
        UsernameAttributes=["email"],
        Schema=[
            {
                "Name": "email",
                "AttributeDataType": "String",
                "Required": True,
                "Mutable": True,
            }
        ],
        UserPoolTags={
            "Project": "ai-platform",
            "Phase": "6",
            "Purpose": "corp-llm-prototype",
        },
        AdminCreateUserConfig={
            "AllowAdminCreateUserOnly": True,  # Only admin can create users (controlled demo)
            "InviteMessageTemplate": {
                "EmailMessage": (
                    "You have been invited to the AI Knowledge Platform demo.\n\n"
                    "Username: {username}\nTemporary password: {####}\n\n"
                    "Please log in and change your password on first use."
                ),
                "EmailSubject": "AI Knowledge Platform — Your Demo Access",
            },
        },
        MfaConfiguration="OFF",  # Off for demo simplicity
        AccountRecoverySetting={
            "RecoveryMechanisms": [{"Priority": 1, "Name": "verified_email"}]
        },
    )

    pool_id = resp["UserPool"]["Id"]
    print(f"[cognito] user pool created: {pool_id}")
    return pool_id


def get_or_create_app_client(cognito, pool_id: str) -> dict:
    clients = cognito.list_user_pool_clients(UserPoolId=pool_id, MaxResults=10)["UserPoolClients"]
    for c in clients:
        if c["ClientName"] == CLIENT_NAME:
            full = cognito.describe_user_pool_client(
                UserPoolId=pool_id, ClientId=c["ClientId"]
            )["UserPoolClient"]
            print(f"[cognito] app client already exists: {c['ClientId']}")
            return full

    resp = cognito.create_user_pool_client(
        UserPoolId=pool_id,
        ClientName=CLIENT_NAME,
        GenerateSecret=False,  # No secret — SPA / frontend client
        ExplicitAuthFlows=[
            "ALLOW_USER_PASSWORD_AUTH",
            "ALLOW_REFRESH_TOKEN_AUTH",
            "ALLOW_USER_SRP_AUTH",
        ],
        AccessTokenValidity=8,        # 8 hours — reasonable for a workday demo session
        IdTokenValidity=8,
        RefreshTokenValidity=30,      # 30 days
        TokenValidityUnits={
            "AccessToken": "hours",
            "IdToken": "hours",
            "RefreshToken": "days",
        },
        PreventUserExistenceErrors="ENABLED",
    )

    client = resp["UserPoolClient"]
    print(f"[cognito] app client created: {client['ClientId']}")
    return client


def get_or_create_group(cognito, pool_id: str, group_name: str, description: str) -> None:
    try:
        cognito.get_group(UserPoolId=pool_id, GroupName=group_name)
        print(f"[cognito] group already exists: {group_name}")
    except cognito.exceptions.ResourceNotFoundException:
        cognito.create_group(
            UserPoolId=pool_id,
            GroupName=group_name,
            Description=description,
        )
        print(f"[cognito] group created: {group_name}")


def get_or_create_admin_user(cognito, pool_id: str) -> None:
    try:
        cognito.admin_get_user(UserPoolId=pool_id, Username=ADMIN_EMAIL)
        print(f"[cognito] admin user already exists: {ADMIN_EMAIL}")
    except cognito.exceptions.UserNotFoundException:
        cognito.admin_create_user(
            UserPoolId=pool_id,
            Username=ADMIN_EMAIL,
            UserAttributes=[{"Name": "email", "Value": ADMIN_EMAIL}],
            MessageAction="SUPPRESS",  # No welcome email — we set permanent password next
        )
        print(f"[cognito] admin user created: {ADMIN_EMAIL}")

    # Add to admin group
    try:
        cognito.admin_add_user_to_group(
            UserPoolId=pool_id,
            Username=ADMIN_EMAIL,
            GroupName="admin",
        )
        print(f"[cognito] {ADMIN_EMAIL} added to admin group")
    except Exception as e:
        print(f"[cognito] add to group: {e}")


def print_summary(pool_id: str, client: dict) -> None:
    print()
    print("=" * 60)
    print("Cognito setup complete. Add to Lambda environment:")
    print()
    print(f"  COGNITO_USER_POOL_ID={pool_id}")
    print(f"  COGNITO_CLIENT_ID={client['ClientId']}")
    print(f"  COGNITO_REGION={REGION}")
    print()
    print("Next steps:")
    print("  1. Set admin password:")
    print(f"     aws cognito-idp admin-set-user-password \\")
    print(f"       --user-pool-id {pool_id} \\")
    print(f"       --username {ADMIN_EMAIL} \\")
    print(f"       --password '<YourStrongPassword12!' \\")
    print(f"       --permanent")
    print()
    print("  2. Create a demo user:")
    print(f"     aws cognito-idp admin-create-user \\")
    print(f"       --user-pool-id {pool_id} \\")
    print(f"       --username demo@example.com \\")
    print(f"       --user-attributes Name=email,Value=demo@example.com \\")
    print(f"       --temporary-password 'TempPass123!'")
    print()
    print(f"     aws cognito-idp admin-add-user-to-group \\")
    print(f"       --user-pool-id {pool_id} \\")
    print(f"       --username demo@example.com \\")
    print(f"       --group-name demo_user")
    print("=" * 60)


def main():
    cognito = boto3.client("cognito-idp", region_name=REGION)

    print("Phase 6 — Cognito User Pool Setup")
    print("=" * 40)

    pool_id = get_or_create_user_pool(cognito)
    client = get_or_create_app_client(cognito, pool_id)
    get_or_create_group(cognito, pool_id, "admin", "Full access — ingest + query + manage users")
    get_or_create_group(cognito, pool_id, "demo_user", "Read-only — query only")
    get_or_create_admin_user(cognito, pool_id)

    print_summary(pool_id, client)


if __name__ == "__main__":
    main()
