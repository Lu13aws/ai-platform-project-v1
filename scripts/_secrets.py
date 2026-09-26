"""
Shared helper for deploy scripts that write app secrets into AWS Secrets
Manager and grant a Lambda execution role read access, instead of putting
raw values into Lambda Environment.Variables in cleartext.

Deliberately shared (unlike most of this codebase's per-script duplication
convention): 6 deploy scripts write to the SAME secret
("ai-platform/app-secrets"), and a naive overwrite-without-merge would
silently drop keys another script had just written.
"""

import json


def ensure_secret_merged(sm, secret_name: str, updates: dict[str, str]) -> str:
    """Create the secret if it doesn't exist, or merge `updates` on top of
    its current value if it does — never wipes keys another script wrote."""
    try:
        existing = sm.get_secret_value(SecretId=secret_name)
        current = json.loads(existing["SecretString"])
        merged = {**current, **updates}
        sm.put_secret_value(SecretId=secret_name, SecretString=json.dumps(merged))
        secret_arn = existing["ARN"]
        print(f"  [secrets] '{secret_name}' updated ({len(merged)} keys)")
    except sm.exceptions.ResourceNotFoundException:
        resp = sm.create_secret(Name=secret_name, SecretString=json.dumps(updates))
        secret_arn = resp["ARN"]
        print(f"  [secrets] '{secret_name}' created ({len(updates)} keys)")
    return secret_arn


def grant_secret_read(iam, role_name: str, policy_name: str, secret_arn: str) -> None:
    policy_document = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["secretsmanager:GetSecretValue"],
            "Resource": secret_arn,
        }],
    })
    iam.put_role_policy(RoleName=role_name, PolicyName=policy_name, PolicyDocument=policy_document)
    print(f"  [secrets] '{policy_name}' granted on role '{role_name}'")
