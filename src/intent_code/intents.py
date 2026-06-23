"""The default code-intent pack.

The same query is ranked differently depending on the agent's current phase.
Registered after the first full index so each intent's lens fits against real
corpus statistics (intent-db computes corpus stats at registration time).
"""

from __future__ import annotations

CODE_INTENTS: list[dict] = [
    {
        "name": "debugging",
        "description": (
            "Diagnosing a bug, error, crash, or unexpected behaviour: error "
            "handling, failure paths, edge cases, recent changes, and known "
            "gotchas."
        ),
        "instruction": "Find code and notes that help diagnose a bug or failure",
        "exemplars": [
            "why does this throw an exception",
            "where is the error handled",
            "what happens on failure or timeout",
            "trace the crash in this request path",
            "known gotcha or footgun in this module",
            "edge case that breaks this function",
        ],
    },
    {
        "name": "extending",
        "description": (
            "Adding a feature or changing behaviour: public interfaces, "
            "function signatures, extension points, call sites, and similar "
            "existing patterns to follow."
        ),
        "instruction": "Find the interfaces, signatures, and patterns to extend",
        "exemplars": [
            "how do I add a new option here",
            "what is the public API for this",
            "where is this function called from",
            "the extension point or hook to plug into",
            "an existing implementation to copy the pattern from",
            "the signature and parameters of this",
        ],
    },
    {
        "name": "reviewing",
        "description": (
            "Reviewing or validating code: invariants, constraints, tests, "
            "conventions, and decisions that must not be regressed."
        ),
        "instruction": "Find invariants, tests, and conventions to review against",
        "exemplars": [
            "what invariant must this preserve",
            "which tests cover this behaviour",
            "the convention or rule this must follow",
            "what must not be changed or regressed here",
            "validation and constraint checks",
            "why was this decision made",
        ],
    },
    {
        "name": "onboarding",
        "description": (
            "Understanding the codebase at a high level: entry points, overall "
            "control and data flow, module responsibilities, and architecture."
        ),
        "instruction": "Find high-level structure, entry points, and overall flow",
        "exemplars": [
            "how does this system work overall",
            "where does execution start",
            "what is the high-level data flow",
            "what is this module responsible for",
            "how do the main components fit together",
            "give me an overview of the architecture",
        ],
    },
]

CODE_INTENT_NAMES = [it["name"] for it in CODE_INTENTS]


def register_code_intents(idb) -> list[str]:
    """Register (or redefine) the code-intent pack over the current corpus."""
    for it in CODE_INTENTS:
        idb.register_intent(
            it["name"],
            description=it["description"],
            exemplars=it["exemplars"],
            instruction=it["instruction"],
        )
    return CODE_INTENT_NAMES
