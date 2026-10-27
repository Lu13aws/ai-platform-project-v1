# 0003. All LLM calls go through a provider abstraction

- **Status:** Accepted
- **Date:** Phase 1 (2026)

## Context

Model prices, quality and terms change quickly. Tying every agent to one vendor SDK would make
switching expensive and would spread provider-specific code across the codebase.

## Decision

`aiplatform/llm/base.py` defines `LLMProvider`; `OpenAIProvider` and `AnthropicProvider` implement it.
Code obtains a provider through `get_llm_provider()`, which reads `settings.llm_provider` or an explicit
override. No application code imports `openai` or `anthropic` directly.

## Consequences

- Switching the chat model is a configuration change.
- Token counts come back in one shape (`LLMResponse`), which keeps cost tracking uniform.
- Embeddings stay on OpenAI `text-embedding-3-small`; changing the embedding model means re-embedding
  everything, so it is deliberately not a runtime switch.
- Provider-specific features (tool use, caching) are only available through the common interface
  once someone adds them there.
