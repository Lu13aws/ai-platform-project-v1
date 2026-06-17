"""
Notifier Agent — publishes a pipeline run summary to Amazon SNS.

Called at the end of the radar pipeline after the Reporter finishes.
If SNS_TOPIC_ARN is not configured, it logs and skips gracefully.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import boto3

from aiplatform.settings import settings

if TYPE_CHECKING:
    from aiplatform.agents.change_detector import ChangeReport


class NotifierAgent:
    def __init__(self, topic_arn: str | None = None) -> None:
        self._topic_arn = topic_arn or settings.sns_topic_arn

    def run(self, pipeline_results: dict[str, str], change_report: "ChangeReport | None" = None) -> bool:
        if not self._topic_arn:
            print("  [notify] SNS_TOPIC_ARN not set — skipping notification")
            return False

        subject = _build_subject(pipeline_results, change_report)
        message = _build_message(pipeline_results, change_report)

        sns = boto3.client("sns", region_name=settings.aws_region)
        sns.publish(TopicArn=self._topic_arn, Subject=subject, Message=message)
        print(f"  [notify] published to {self._topic_arn}")
        return True


def _build_subject(results: dict[str, str], change_report: "ChangeReport | None") -> str:
    reporter = results.get("reporter", "")
    entry_count = _extract(reporter, "entries")
    if change_report and change_report.has_changes():
        n = change_report.total_changes()
        return f"Technology Radar — {n} change{'s' if n != 1 else ''} detected | {entry_count} technologies tracked"
    return f"Technology Radar — Run Complete | {entry_count} technologies tracked"


def _build_message(results: dict[str, str], change_report: "ChangeReport | None") -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    collector = results.get("collector", "n/a")
    analyzer = results.get("analyzer", "n/a")
    reporter = results.get("reporter", "n/a")

    html_uri = ""
    for part in reporter.split():
        if part.startswith("html=s3://"):
            html_uri = part[5:]
            break

    lines = [
        "Technology Radar — Weekly Pipeline Run",
        "=" * 44,
        f"Completed: {now}",
        "",
        "Pipeline results:",
        f"  Collector : {collector}",
        f"  Analyzer  : {analyzer}",
        f"  Reporter  : {reporter}",
    ]

    if change_report and change_report.has_changes():
        lines += ["", "Changes detected:", "-" * 28]
        for line in change_report.summary_lines():
            lines.append(f"  {line}")
        lines.append(f"  ({change_report.unchanged} technologies unchanged)")

    if html_uri:
        lines += ["", f"Report: {html_uri}", "", "Download:"]
        lines.append(f"  aws s3 cp {html_uri} radar_report.html")

    lines += ["", "— AI Platform · bridging-data.com"]
    return "\n".join(lines)


def _extract(text: str, key: str) -> str:
    for part in text.split():
        if part.startswith(f"{key}="):
            return part.split("=", 1)[1]
    return "?"
