# Engineering Instructions

## Workflow

Keep small, isolated, low-risk, and read-only work single-agent unless delegation is requested. Use `junior_engineer` only when a small implementation task benefits from delegation.

For substantial or risky implementation:

1. Use `backend_architect` only for cross-file planning, external dependencies, architecture, or unclear contracts.
2. Use exactly one implementation owner: `senior_swe` by default; `principal_swe` for risky, ambiguous, architectural, cross-system, security-sensitive, difficult, or failed work.
3. After implementation, use only applicable reviewers: `frontend_reviewer` for user-facing changes, `security_reviewer` for risky or behaviorally significant changes, and `test_engineer` for targeted verification or test-gap analysis.
4. Return actionable findings to the implementation owner; repeat only needed review or verification.

Reuse findings. Do not run overlapping broad investigations. Parallelize only independent read-only investigations within the same phase.

Use `$fan-out` only for broad codebase discovery with at least three independent questions where parallel search clearly saves time or context.

## Documentation Preflight

Before implementing a feature that materially depends on an external library, framework, SDK, API, or platform, consult current documentation through Context7.

Resolve the correct Context7 library ID, inspect APIs and version-specific constraints, and apply relevant findings before editing code.

Do not send proprietary source code, credentials, personal data, or secrets to Context7. If Context7 lacks coverage, use repository-pinned versions, local documentation, authoritative upstream sources, and existing codebase patterns.

Skip documentation lookup when external API behavior is irrelevant or already current in repository documentation.

## Context Hygiene

When Headroom is available, use it for bulky local outputs and context. Do not commit its stores, caches, logs, sessions, learned local files, or machine-specific paths.

## Engineering Standards

Follow repository architecture, conventions, formatting, and established patterns.

Prefer simple, focused, testable designs. Avoid duplication, premature abstractions, speculative scaling, unrelated refactors, and behavior changes outside requested scope.

Use clear names, deliberate error handling, named constants for behavior-shaping values, and accurate documentation for public or non-obvious behavior.

Validate work with relevant tests, type checking, linting, builds, or direct inspection. Do not claim success without evidence.

## Resource Hygiene

Close local servers, test servers, background services, and opened ports after verification. Remove temporary artifacts when no longer needed. Do not modify or delete unrelated user files.

## Communication Style

Default to Caveman full. Follow Caveman skill exceptions and user-selected overrides. Keep code, commits, PRs, and documentation professional.
