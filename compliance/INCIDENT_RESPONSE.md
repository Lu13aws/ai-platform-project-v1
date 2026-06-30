# Incident Response Plan

**Version:** 1.0  
**Date:** June 2026  
**Owner:** Luciano (luciano.10@hotmail.de)  
**Platform:** AI Knowledge & Intelligence Platform

---

## Overview

This document defines the response procedure for security incidents and data breaches
affecting the AI Knowledge & Intelligence Platform. It covers detection, assessment,
containment, notification, and post-incident review.

**Scope:** All components deployed on AWS (eu-central-1), including:
- Public RAG Demo API
- Knowledge Platform (Agent Center, AI Chat, Skills Hub)
- Corporate LLM Prototype
- All pipeline Lambda functions (Radar, Competitor, Regulatory, Content Creator)

---

## Incident Categories

| Category | Examples |
|---|---|
| **Data breach** | Unauthorised access to corporate documents, audit logs, or embeddings |
| **Authentication failure** | Cognito pool compromised, JWT tokens leaked, credential exposure |
| **Infrastructure compromise** | Unauthorised changes to Lambda functions, RDS, IAM roles |
| **API abuse** | Sustained scraping, injection attempts, unexpected cost spikes |
| **Data integrity** | Incorrect data ingested, embeddings corrupted, reports manipulated |
| **Service disruption** | Pipeline failures, Lambda errors, RDS unavailability |
| **AI output incident** | Harmful, defamatory, or seriously inaccurate content published publicly |

---

## Severity Levels

| Level | Definition | Response time |
|---|---|---|
| **P1 — Critical** | Personal data of individuals exposed; corporate documents accessed without authorisation; credentials compromised | Immediate (< 1 hour) |
| **P2 — High** | Service fully unavailable; pipeline producing systematically wrong outputs; API keys exposed | < 4 hours |
| **P3 — Medium** | Single pipeline failure; non-sensitive data inconsistency; elevated error rates | < 24 hours |
| **P4 — Low** | Report formatting errors; minor UI defects; non-impacting LLM quality issues | Next scheduled maintenance |

---

## Detection

**Monitoring sources:**
- AWS CloudWatch: Lambda error rates, API Gateway 4xx/5xx rates, Lambda duration anomalies
- AWS Budgets: alert at 10 CHF (warning) and 25 CHF (critical) — catches runaway costs
- SNS email notifications: each pipeline sends success/failure emails
- Audit log review: `GET /corp/audit` endpoint shows all user actions on corporate data
- Manual review: LinkedIn Review UI for drafted content before publication

**Signs of potential incident:**
- Unexpected CloudWatch Lambda errors or sustained elevated invocation counts
- AWS Budget threshold crossed without an expected pipeline run
- Audit log entries with unexpected user IDs or IP addresses
- Failed Cognito authentication attempts (visible in Cognito console)
- API Gateway access logs showing unexpected traffic patterns (if CloudTrail is enabled)

---

## Response Procedure

### Step 1 — Detect & Classify (< 1 hour for P1/P2)

1. Identify the affected component and data scope
2. Assign severity level (P1–P4) using the table above
3. Determine whether personal data may have been exposed

### Step 2 — Contain (immediate for P1)

**Corporate prototype — data breach or authentication compromise:**
1. Disable the Cognito user pool or specific user account via AWS Console
2. Rotate `CORP_DATABASE_URL` secret in Secrets Manager and redeploy Lambda
3. Review audit log for the time window: `GET /corp/audit?limit=500`
4. Revoke API Gateway usage if necessary (delete API key or disable stage)

**Public API — abuse or injection:**
1. Enable WAF blocking rule on affected API Gateway stage (if WAF is configured)
2. Restrict Lambda concurrency to 0 via AWS Console to halt traffic temporarily
3. Review CloudWatch logs for the affected time window
4. Re-enable after root cause is identified

**Credential exposure (API keys, Secrets Manager):**
1. Immediately rotate the exposed credential (OpenAI key, Anthropic key, DB password)
2. Update the Lambda environment variable or Secrets Manager entry
3. Redeploy affected Lambda function(s) to pick up new credentials
4. Audit usage of the exposed key with the provider (OpenAI usage dashboard, Anthropic console)

**Content incident (harmful LinkedIn post published):**
1. Manually delete the post from LinkedIn using the post URL stored in `linkedin_post_url`
2. Review the ContentCreatorAgent prompt and output for the affected run
3. Add the specific case to the manual review checklist

### Step 3 — Assess Impact

Answer the following:
- What data was affected? (document content, embeddings, user data, audit logs)
- Was any personal data exposed? (names, emails in documents or audit logs)
- How many records/documents were affected?
- Was the exposure external (internet-reachable) or internal only?
- What was the time window of exposure?

### Step 4 — Notify (if personal data was exposed)

**GDPR Art. 33 — Supervisory authority notification:**  
If personal data of individuals (not just business documents) was involved in a breach,
the supervisory authority must be notified **within 72 hours** of becoming aware.

- Swiss supervisory authority: [FDPIC](https://www.edoeb.admin.ch/edoeb/en/home.html)
- German supervisory authority (if EU data subjects affected): [BfDI](https://www.bfdi.bund.de)

**What to include in the notification:**
1. Nature of the breach (what happened, which data)
2. Categories and approximate number of data subjects affected
3. Categories and approximate number of records affected
4. Contact details of the data controller (name, email)
5. Likely consequences of the breach
6. Measures taken or proposed to address the breach

**GDPR Art. 34 — Individual notification:**  
If the breach is likely to result in a high risk to the rights and freedoms of individuals,
notify the affected individuals directly without undue delay.

**72-hour clock starts:** when the platform owner becomes aware of the breach.

### Step 5 — Remediate

1. Fix the root cause (patch code, update configuration, rotate credentials)
2. Redeploy affected components
3. Verify the fix with a test run or API call
4. Re-enable any temporarily disabled components

### Step 6 — Post-Incident Review

For P1 and P2 incidents:
1. Document the timeline (detection → containment → resolution)
2. Document the root cause
3. List any corrective actions to prevent recurrence
4. Update this document if the response procedure needs revision
5. Record the incident in the risk register (`compliance/RISK_REGISTER.md` if maintained)

---

## Contact

| Role | Contact |
|---|---|
| Platform owner / data controller | Luciano — luciano.10@hotmail.de |
| AWS account access | Via IAM with MFA |
| OpenAI support | https://help.openai.com |
| Anthropic support | https://console.anthropic.com |

---

## Testing

This incident response plan has not been formally tested with a tabletop exercise.
For a production deployment with client data, a tabletop exercise covering the P1
data breach scenario is recommended before go-live.
