"""Stage 05: risk fusion. Check signals plus call context into a 0 to 100 score, under 30 ms.

Continuous scoring, roughly once a second, never a single start-of-call decision.
Policy rules are per deployment (contracts.context.PolicyRef).
"""