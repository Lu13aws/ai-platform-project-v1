# Acceptable Use Policy

**Version:** 1.0  
**Date:** June 2026  
**Applies to:** AI Knowledge & Intelligence Platform (platform.bridging-data.com and corporate prototype)  
**Owner:** Luciano (<OWNER_EMAIL>)

---

## Purpose

This policy defines the permitted and prohibited uses of the AI Knowledge & Intelligence Platform.
It applies to all users of the platform, including portfolio visitors, demo participants,
and users of the Corporate LLM Prototype.

---

## Permitted Uses

### Public RAG Demo & Knowledge Platform

- Querying public documents (AWS whitepapers, NIST frameworks, OWASP documentation,
  data governance guides) using semantic search
- Demonstrating AI-assisted knowledge retrieval to potential clients or collaborators
- Testing the platform's retrieval accuracy using publicly available reference material
- Portfolio evaluation by prospective employers, clients, or technical reviewers

### Corporate LLM Prototype

- Querying internal business documents uploaded by the admin user
- Demonstrating enterprise-grade knowledge retrieval to potential clients under controlled demo conditions
- Evaluating RAG accuracy over known internal documents
- Reviewing audit logs and pipeline status by authorised admin users

### All Components

- Searching and browsing agent pipeline status in the Agent Center
- Reviewing generated radar reports (Technology, Regulatory, Competitor)
- Reviewing LinkedIn draft content before approving or rejecting publication

---

## Prohibited Uses

The following uses are **not permitted** under any circumstances:

### Data ingestion

- Ingesting personal data of third parties without a lawful basis (customer records, employee data,
  contact lists, CRM exports, medical records, financial data of individuals)
- Ingesting confidential client data or trade secrets without explicit client authorisation
- Ingesting classified government information or documents subject to export control restrictions
- Ingesting copyright-protected material beyond what is permissible under applicable fair use
  or citation law

### Queries and outputs

- Using the platform to generate content intended to deceive, defame, or harm any person
- Using AI-generated outputs as final, authoritative answers without human review
- Treating radar classifications (Adopt/Trial/Assess/Hold) as investment advice or professional recommendations
- Publishing AI-generated LinkedIn content without reviewing the draft and clicking "Publish" manually
- Using the platform to generate legal, medical, financial, or regulatory compliance advice

### System access

- Sharing Cognito credentials or access tokens with unauthorised parties
- Attempting to access data from application namespaces other than the one authorised
  (e.g. accessing `corp` data via the public API, or vice versa)
- Probing for API vulnerabilities, running automated scanners, or attempting to extract
  data beyond what is returned by the authorised endpoints
- Using the platform to train or fine-tune other AI models without explicit written permission

### Infrastructure

- Running workloads that could cause unexpected cost spikes without prior authorisation
  (e.g. ingesting thousands of documents in a single session, running bulk embedding jobs
  outside scheduled pipelines)
- Modifying or deleting pipeline infrastructure (EventBridge rules, Lambda functions,
  RDS instances) without explicit intent and backup

---

## Liability Disclaimer

All AI-generated content on this platform — including radar classifications, competitor signals,
regulatory summaries, LinkedIn drafts, and RAG answers — is produced by language models
based on indexed source material.

**This platform does not provide professional advice of any kind.**

The platform owner accepts no liability for:
- Decisions made based on AI-generated classifications or summaries
- Inaccuracies in retrieved or generated content
- Loss of data resulting from pipeline failures or infrastructure outages
- Third-party actions resulting from published LinkedIn content

Users are responsible for reviewing any AI-generated output before acting on it or sharing it.

---

## Enforcement

Violations of this policy may result in:
- Immediate revocation of Cognito access credentials
- Deletion of ingested data in violation of this policy
- Notification to relevant authorities if a legal obligation exists

The platform owner reserves the right to review audit logs and access patterns to verify
compliance with this policy.

---

## Changes

This policy may be updated at any time. The version number and date at the top of this
document indicate the current version. Changes take effect immediately upon update.
