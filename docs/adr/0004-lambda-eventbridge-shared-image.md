# 0004. Lambda + EventBridge with one shared container image

- **Status:** Accepted
- **Date:** Phase 2 (2026)

## Context

Pipelines run weekly or monthly for a few minutes. The APIs see low, bursty traffic.
Always-on compute (ECS services, EC2) would cost money while idle.

## Decision

Every pipeline and API runs on AWS Lambda. EventBridge schedules trigger the pipelines; API Gateway
fronts the APIs through Mangum. All functions share one image in ECR (`Dockerfile.lambda`),
and each function selects its handler with an `ImageConfig.Command` override.

## Consequences

- Compute cost is close to zero between runs.
- One build serves every function, so the shared library is always the same version everywhere.
- Every deploy rebuilds and updates all functions. Images are pushed with a timestamp tag and
  deployed by digest to avoid ECR layer deduplication issues.
- Runs are capped at the 15-minute Lambda limit, which also acts as a cost guard.
- Lambdas in the private VPC need a NAT gateway for outbound calls, which is now the largest fixed cost
  (about 39 USD/month). Revisit if that cost matters more than the isolation it buys.
