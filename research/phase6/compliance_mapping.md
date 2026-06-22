# Phase 6 — Compliance Mapping

**Use case:** Corporate LLM Prototype — demo for potential customers  
**Data:** Own business documents (Skills, README, project docs)  
**Requirement:** Public and private data must be physically separated  
**Date:** June 2026

---

## Summary

| Framework | Coverage Today | Missing for Phase 6 |
|---|---|---|
| NIST AI RMF | ~30% | Govern policies, risk docs, model cards, incident response |
| GDPR / Swiss DSG | ~40% | Consent, deletion on request, processing records, user notifications |
| AWS Well-Architected (Security) | ~60% | RBAC, separate RDS, audit logging per user |

---

## 1. NIST AI Risk Management Framework (AI RMF)

### GOVERN — Policies, Accountability, Risk Tolerance

| Requirement | Status | Notes |
|---|---|---|
| Define AI system purpose and scope | ✅ Done | Documented in CLAUDE.md |
| Define risk tolerance | ⚠️ Partial | Cost controls exist, no formal AI risk policy |
| Assign accountability for AI outputs | ❌ Missing | No owner/reviewer role defined |
| Document AI model used + version | ❌ Missing | No model card — which model, which version, known limitations |
| Define acceptable use policy | ❌ Missing | What the system may/may not be used for |
| Establish review cadence | ❌ Missing | When and how system performance is reviewed |

### MAP — Context, Risk Identification

| Requirement | Status | Notes |
|---|---|---|
| Identify affected stakeholders | ⚠️ Partial | End users known, no formal stakeholder map |
| Identify data sources and provenance | ✅ Done | Source attribution in all answers, S3 raw storage |
| Identify potential harms | ❌ Missing | Hallucination risk, data leakage, bias in classification |
| Document assumptions and limitations | ⚠️ Partial | Known issues in README, no formal limitation doc |

### MEASURE — Risk Analysis

| Requirement | Status | Notes |
|---|---|---|
| Source attribution on all answers | ✅ Done | Every LLM answer includes source references |
| Confidence / similarity scoring | ✅ Done | Cosine similarity scores returned with results |
| Cost monitoring | ✅ Done | AWS Budgets, LLM call limits per run |
| Hallucination mitigation | ⚠️ Partial | RAG reduces risk, no formal evaluation |
| Bias assessment | ❌ Missing | LLM classification bias not evaluated |
| Regular model performance review | ❌ Missing | No process defined |

### MANAGE — Risk Response, Monitoring

| Requirement | Status | Notes |
|---|---|---|
| Retention and deletion policies | ✅ Done | CleanupAgent enforces retention rules |
| Incident response plan | ❌ Missing | What to do if data leak, wrong output, etc. |
| Human review before publication | ⚠️ Partial | Planned for LinkedIn/Newsletter, not yet built |
| Monitoring and alerting | ⚠️ Partial | CloudWatch logs exist, no semantic drift alerts |

---

## 2. GDPR / Swiss DSG

### Data Processing Principles (Art. 5 GDPR)

| Principle | Status | Notes |
|---|---|---|
| Lawfulness — clear legal basis | ⚠️ Partial | Own documents: legitimate interest. Customer data: needs consent definition |
| Purpose limitation — data used only for stated purpose | ✅ Done | app_name scoping prevents cross-use |
| Data minimisation — only what's necessary | ✅ Done | Only metadata + chunks stored, not full documents |
| Accuracy | ✅ Done | SHA-256 dedup, version tracking for regulatory docs |
| Storage limitation | ✅ Done | Retention rules per data type, CleanupAgent |
| Integrity & confidentiality | ⚠️ Partial | Encryption at rest/transit ✅, physical isolation ❌ |

### Individual Rights

| Right | Status | Notes |
|---|---|---|
| Right to access (Art. 15) | ❌ Missing | No API for "show me all data stored about me" |
| Right to erasure / deletion (Art. 17) | ❌ Missing | No user-triggered deletion implemented |
| Right to data portability (Art. 20) | ❌ Missing | No export function |
| Right to object (Art. 21) | ❌ Missing | No opt-out mechanism |

### Technical & Organizational Measures (Art. 32)

| Measure | Status | Notes |
|---|---|---|
| Encryption at rest | ✅ Done | RDS encryption enabled, S3 SSE |
| Encryption in transit | ✅ Done | HTTPS via API Gateway, SSL for RDS |
| Access control | ⚠️ Partial | IAM for AWS services, no end-user auth |
| Authentication | ❌ Missing | No Cognito, no login for demo users |
| Audit logging per user action | ❌ Missing | CloudWatch has Lambda logs, no per-user trail |
| Data breach notification process | ❌ Missing | No process defined (72h window per GDPR) |

### Records of Processing (Art. 30)

| Requirement | Status | Notes |
|---|---|---|
| Document what data is processed | ⚠️ Partial | README documents data types, no formal ROPA |
| Document retention periods | ✅ Done | Retention table in README and CLAUDE.md |
| Document data recipients / processors | ❌ Missing | OpenAI / Anthropic as processors not documented |

---

## 3. AWS Well-Architected Framework — Security Pillar

### Identity & Access Management

| Control | Status | Notes |
|---|---|---|
| IAM roles with least privilege | ✅ Done | Lambda roles scoped to required services |
| No hardcoded credentials | ✅ Done | All secrets in Lambda env vars |
| End-user authentication | ❌ Missing | Cognito not yet implemented |
| RBAC — users see only their data | ❌ Missing | No role-based data scoping |

### Infrastructure Protection

| Control | Status | Notes |
|---|---|---|
| RDS in private VPC | ✅ Done | Migrated 2026-06-20, no public endpoint |
| Security groups scoped | ✅ Done | Port 5432 from Lambda SG only |
| Physical data isolation (private vs public) | ❌ Missing | Shared RDS instance, only logical app_name separation |
| WAF on API Gateway | ❌ Missing | No rate limiting or WAF rules |

### Data Protection

| Control | Status | Notes |
|---|---|---|
| Encryption at rest | ✅ Done | RDS + S3 |
| Encryption in transit | ✅ Done | TLS everywhere |
| Data classification | ❌ Missing | No formal classification (public / internal / confidential) |
| Separate storage per data class | ❌ Missing | All data in one RDS instance |

### Detection & Monitoring

| Control | Status | Notes |
|---|---|---|
| CloudWatch logs | ✅ Done | All Lambda logs captured |
| Cost alerts | ✅ Done | AWS Budgets configured |
| Security alerts | ❌ Missing | No GuardDuty, no anomaly detection |
| Audit trail per user action | ❌ Missing | No per-user logging |

---

## Phase 6 Build List (Priority Order)

### Must-Have (MVP for demo)

| Item | Why |
|---|---|
| **Cognito authentication** | Without login, you can't show this to customers |
| **Separate RDS instance** for private data | Physical isolation is a hard requirement |
| **RBAC** — users only see their own documents | Core trust requirement |
| **Audit logging per user action** | Required for any compliance claim |
| **Data deletion on request** | GDPR Art. 17 — must be implementable |

### Should-Have (makes it credible)

| Item | Why |
|---|---|
| **Model card document** | Describes AI system, limitations, which model used |
| **Acceptable use policy** | What the system may/may not be used for |
| **Data processing records (ROPA)** | Art. 30 — documents what data is processed and why |
| **Document OpenAI/Anthropic as processors** | GDPR requires documenting third-party processors |
| **Human review before AI-generated publication** | LinkedIn/Newsletter approval step |

### Nice-to-Have (Phase 6+)

| Item | Why |
|---|---|
| WAF on API Gateway | Rate limiting, DDoS protection |
| GuardDuty | Threat detection |
| Data portability (export) | GDPR Art. 20 |
| Bias evaluation | NIST AI RMF Measure |
| Semantic drift monitoring | Long-term quality assurance |

---

## Architecture Implications

Based on this mapping, Phase 6 requires a **separate infrastructure stack**:

```
Current Stack (public, shared):
  RDS ai-platform-db-v2 (ai-platform-vpc)
  └── app_name: rag_demo, skills_hub, knowledge_platform, private_hub
  Lambda: ai-platform-rag-demo (no auth)

Phase 6 Stack (private, isolated):
  RDS ai-platform-db-corp (new VPC or strict peering)
  └── tenant_id + user_id scoping
  Lambda: ai-platform-corp-api (Cognito authorizer)
  Cognito User Pool: corporate users only
  CloudTrail: per-user audit log
```

**Do NOT reuse the current RDS for Phase 6 private data.**

---

## Next Steps

1. Review and confirm this mapping
2. Design the Phase 6 infrastructure architecture
3. Set up Cognito User Pool
4. Provision separate RDS instance
5. Implement RBAC middleware
6. Implement audit logging
7. Build deletion endpoint
8. Write model card + acceptable use policy
