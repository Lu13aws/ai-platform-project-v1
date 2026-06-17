#!/usr/bin/env python3
"""
Create the SNS topic for radar pipeline notifications and subscribe your email.

Usage:
    uv run python scripts/setup_sns.py --email luciano.10@hotmail.de

Saves the topic ARN to infra/sns_config.json (gitignored).
Re-running is safe — idempotent.
"""

import argparse
import json
from pathlib import Path

import boto3

REGION = "eu-central-1"
TOPIC_NAME = "ai-platform-radar-notifications"
SNS_CONFIG_PATH = Path("infra/sns_config.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True, help="Email address to subscribe")
    args = parser.parse_args()

    sns = boto3.client("sns", region_name=REGION)

    # Create or get existing topic (idempotent — same name returns same ARN)
    response = sns.create_topic(
        Name=TOPIC_NAME,
        Attributes={"DisplayName": "AI Platform Radar"},
    )
    topic_arn = response["TopicArn"]
    print(f"  [ok] SNS topic: {topic_arn}")

    # Subscribe email
    sub = sns.subscribe(
        TopicArn=topic_arn,
        Protocol="email",
        Endpoint=args.email,
        ReturnSubscriptionArn=True,
    )
    print(f"  [ok] subscribed {args.email} (status: pending confirmation)")
    print(f"       Check your inbox and click 'Confirm subscription'")

    # Save config
    SNS_CONFIG_PATH.parent.mkdir(exist_ok=True)
    SNS_CONFIG_PATH.write_text(json.dumps({"topic_arn": topic_arn}, indent=2))
    print(f"  [ok] saved to {SNS_CONFIG_PATH}")

    print(f"""
=== SNS setup complete ===
  Topic ARN : {topic_arn}
  Email     : {args.email}

IMPORTANT: check your inbox and confirm the subscription before testing.
""")


if __name__ == "__main__":
    main()
