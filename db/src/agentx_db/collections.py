"""Phase-1 MongoDB collection names (BUILD-KIT §4).

One ``Final`` constant per collection so call sites never stringly-type a collection name.
"""

from typing import Final

# --- Catalog / registry (long-lived) ---
MANDATE_TYPE: Final = "mandate_type"
MANDATE_INSTANCE: Final = "mandate_instance"
MANDATE_RUN: Final = "mandate_run"

# --- The append-only SOURCE OF TRUTH ---
JOURNAL: Final = "journal"

# --- Projections built from the journal ---
HEAP_FACT: Final = "heap_fact"
THREAD: Final = "thread"
RESUME: Final = "resume"
WATCH: Final = "watch"
SYSCALL_TRACE: Final = "syscall_trace"
BILLING_LINE: Final = "billing_line"

# --- Quality engine ---
EVAL_CASE: Final = "eval_case"

SOURCE_OF_TRUTH: Final = JOURNAL

PROJECTIONS: Final[tuple[str, ...]] = (
    HEAP_FACT,
    THREAD,
    RESUME,
    WATCH,
    SYSCALL_TRACE,
    BILLING_LINE,
)

ALL_COLLECTIONS: Final[tuple[str, ...]] = (
    MANDATE_TYPE,
    MANDATE_INSTANCE,
    MANDATE_RUN,
    JOURNAL,
    HEAP_FACT,
    THREAD,
    RESUME,
    WATCH,
    SYSCALL_TRACE,
    BILLING_LINE,
    EVAL_CASE,
)
