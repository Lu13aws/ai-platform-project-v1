"""
Competitor Notifier Agent — sends SNS email summary after the pipeline run.

Reuses the same SNS topic as the Technology Radar and Regulatory Radar.
Topic ARN is read from the SNS_TOPIC_ARN environment variable (set in Lambda
from infra/sns_config.json by the deploy script).

Skips gracefully if SNS_TOPIC_ARN is not configured (e.g. local dev).
"""

import json
import os

import boto3


class CompetitorNotifierAgent:
    def run(self, pipeline_results: dict, report_result=None) -> bool:
        topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
        if not topic_arn:
            print("  [notify] SNS_TOPIC_ARN not set - skipping notification")
            return False

        signal_count = 0
        company_count = 0
        if report_result:
            signal_count = getattr(report_result, "signal_count", 0)
            company_count = getattr(report_result, "company_count", 0)

        subject = f"Competitor Radar - {signal_count} signals | {company_count} companies monitored"
        subject = subject[:100]  # SNS subject max 100 chars

        lines = [
            "Competitor Radar — Weekly Run Summary",
            "=" * 40,
            "",
            f"Companies monitored : {company_count}",
            f"Signals detected    : {signal_count}",
            "",
            "Pipeline results:",
        ]
        for phase, res in pipeline_results.items():
            lines.append(f"  {phase}: {res}")

        if report_result and getattr(report_result, "html_s3_uri", ""):
            lines += [
                "",
                "Report:",
                f"  {report_result.html_s3_uri}",
                "",
                "Download via AWS CLI:",
                f"  aws s3 cp {report_result.html_s3_uri} competitor_report.html",
            ]

        message = "\n".join(lines)

        try:
            sns = boto3.client("sns")
            sns.publish(TopicArn=topic_arn, Subject=subject, Message=message)
            print(f"  [notify] SNS notification sent: {subject}")
            return True
        except Exception as exc:
            print(f"  [notify] SNS publish failed: {type(exc).__name__}: {exc}")
            return False
