"""
Injects secrets from AWS Secrets Manager into the environment before
aiplatform.settings.Settings() reads it — no-op outside Lambda so local dev
(.env file, no AWS credentials required) is unaffected.

A cold-start fetch failure inside Lambda raises and crashes the import,
which is correct: silently running with empty/missing credentials is worse
than a loud, visible startup failure in CloudWatch.
"""

import json
import os

import boto3


def load_json_secret_into_env(secret_id: str) -> None:
    if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return

    client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "eu-central-1"))
    data = json.loads(client.get_secret_value(SecretId=secret_id)["SecretString"])
    for key, value in data.items():
        os.environ.setdefault(key, value)
