# AI Limitations and Disclaimers

**Version:** 1.0 | **Date:** June 2026 | **Platform:** AI Knowledge & Intelligence Platform

This document explains what AI can and cannot do on this platform.  
It is intended for customers, demo participants, and anyone evaluating AI-generated outputs.

---

## What AI Does Well on This Platform

- Searches indexed documents and surfaces relevant excerpts
- Generates answers grounded in retrieved source material
- Returns source references with every grounded answer (if nothing relevant is found it says so, without sources)
- Classifies signals into categories (technology trends, risk levels, sentiment)
- Drafts content based on provided context

---

## What AI Cannot Guarantee

**Accuracy:** AI-generated answers may be incorrect, incomplete, or outdated — even when
they sound confident. The system is designed to cite its sources, but source material itself
may contain errors.

**Completeness:** The system can only answer from documents that have been indexed. If a
relevant document has not been ingested, the system has no knowledge of it.

**Current information:** AI models have a training cutoff. Recent events are only known to
the system if they appear in indexed documents collected by the pipelines.

**Consistency:** Different queries about the same topic may produce different answers.
AI outputs are probabilistic, not deterministic.

---

## Specific Risks to Be Aware Of

**Hallucination:** Language models can generate plausible-sounding statements that are
factually wrong. This risk is reduced by grounding answers in retrieved documents, but
it cannot be fully eliminated.

**Classification bias:** Automated signal classifications (Adopt/Trial/Assess/Hold, impact
levels, sentiment) reflect patterns in the AI model's training data. These classifications
may be biased in ways that are not always visible.

**Incomplete context:** If the question requires context not present in the indexed
documents, the AI may fill gaps with plausible-sounding but unsupported content.

---

## What Requires Human Review Before Acting

The following outputs always require a human to read and validate before being used:

- Technology radar classifications (Adopt / Trial / Assess / Hold)
- Competitor signal summaries and impact assessments
- Regulatory change analyses and impact classifications
- LinkedIn post drafts (the platform never publishes automatically)
- Any answer used to inform a business decision or recommendation

---

## What This Platform Is NOT

- Not a source of legal advice
- Not a source of financial or investment advice
- Not a source of medical or health advice
- Not a replacement for professional judgment in any regulated domain
- Not an authoritative source on any topic — it is a retrieval and summarisation tool
- Not a decision-maker — it surfaces information, humans decide what to do with it

---

## How to Handle AI Errors

If an AI-generated output appears wrong or misleading:

1. Check the cited sources — verify the underlying documents support the answer
2. Re-phrase the question — different wording often produces more accurate results
3. Do not act on the output without independent verification
4. Report persistent issues to the platform owner (<OWNER_EMAIL>)

---

*For technical details on the AI models used, see [MODEL_CARD.md](MODEL_CARD.md).*
