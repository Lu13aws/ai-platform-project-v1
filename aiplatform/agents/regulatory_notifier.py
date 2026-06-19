"""
Regulatory Notifier Agent — publishes a pipeline run summary to Amazon SNS.

Reuses the same SNS topic as the Technology Radar pipeline.
If SNS_TOPIC_ARN is not configured, logs and skips gracefully.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import boto3

from aiplatform.settings import settings

if TYPE_CHECKING:
    from aiplatform.agents.regulatory_reporter import RegulatoryReportResult


class RegulatoryNotifierAgent:
    def __init__(self, topic_arn: str | None = None) -> None:
        self._topic_arn = topic_arn or settings.sns_topic_arn

    def run(
        self,
        pipeline_results: dict[str, str],
        report_result: "RegulatoryReportResult | None" = None,
    ) -> bool:
        if not self._topic_arn:
            print("  [notify] SNS_TOPIC_ARN not set — skipping notification")
            return False

        subject = _build_subject(report_result)
        message = _build_message(pipeline_results, report_result)

        sns = boto3.client("sns", region_name=settings.aws_region)
        sns.publish(TopicArn=self._topic_arn, Subject=subject, Message=message)
        print(f"  [notify] published to {self._topic_arn}")
        return True


def _build_subject(report_result: "RegulatoryReportResult | None") -> str:
    if report_result and report_result.change_count > 0:
        n = report_result.change_count
        s = report_result.source_count
        return f"Regulatory Radar — {n} change{'s' if n != 1 else ''} detected | {s} sources monitored"
    sources = report_result.source_count if report_result else "?"
    return f"Regulatory Radar — Run Complete | {sources} sources monitored"


def _build_message(
    results: dict[str, str],
    report_result: "RegulatoryReportResult | None",
) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    collector = results.get("collector", "n/a")
    analyzer = results.get("analyzer", "n/a")
    reporter = results.get("reporter", "n/a")

    lines = [
        "Regulatory Radar — Monthly Pipeline Run",
        "=" * 44,
        f"Completed: {now}",
        "",
        "Pipeline results:",
        f"  Collector : {collector}",
        f"  Analyzer  : {analyzer}",
        f"  Reporter  : {reporter}",
    ]

    if report_result and report_result.change_count > 0:
        lines += ["", f"{report_result.change_count} regulatory change(s) detected this run."]
        lines += ["Review the full report for impact summaries and diff details."]

    if report_result and report_result.html_s3_uri:
        s3_uri = report_result.html_s3_uri
        lines += [
            "",
            f"Report: {s3_uri}",
            "",
            "Download:",
            f"  aws s3 cp {s3_uri} regulatory_report.html",
        ]

    lines += ["", "— AI Platform · bridging-data.com"]
    return "\n".join(lines)
