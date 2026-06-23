"""Phase-1 kernel bootstrap — the entry point the integration seam-proof drives."""

from agentx_contracts.protocols import SyscallRegistry
from agentx_mandate.harness import HarnessRunner

from .books_review import BooksReviewResolver
from .gateway import Gateway
from .hydration import HydrationLoader
from .ports import JournalStore, ProjectionStore
from .projections import Projections
from .run_loop import Phase1RunInvoker
from .settlement import SettlementCommitter
from .stores.memory import (
    InMemoryJournalStore,
    InMemoryProjectionStore,
    InMemoryRunContinuationStore,
    InMemorySyscallReceiptStore,
    InMemoryVault,
)
from .verifier import RulesVerifier


def build_phase1_runinvoker(
    registry: SyscallRegistry | None = None,
    runner: HarnessRunner | None = None,
) -> Phase1RunInvoker:
    """Construct the Phase-1 live/sim ``RunInvoker`` wired to the syscall ``registry`` and ``runner``.

    Session B: in ``sim`` mode the swarm passes a registry of SimAdapters; in ``live`` mode the kernel
    passes the production registry. The loop is identical — only the registry differs. ``runner`` selects
    the harness driving the trajectory (G1): when ``None``, sim falls back to ``OwnHarness`` + playbook;
    a live caller passes the Hermes runner.
    """
    journal = InMemoryJournalStore()
    projection_store = InMemoryProjectionStore()
    projections = Projections(projection_store, journal)
    gateway = Gateway(
        journal=journal,
        vault=InMemoryVault(),
        registry=registry,
        receipts=InMemorySyscallReceiptStore(),
    )
    hydration = HydrationLoader(projection_store, journal)
    settlement = SettlementCommitter(journal=journal, projections=projections)
    return Phase1RunInvoker(
        journal=journal,
        projections=projections,
        hydration=hydration,
        gateway=gateway,
        settlement=settlement,
        verifier=RulesVerifier(),
        continuations=InMemoryRunContinuationStore(),
        runner=runner,
    )


def build_books_review_resolver(
    *,
    journal: JournalStore | None = None,
    projection_store: ProjectionStore | None = None,
) -> BooksReviewResolver:
    """Construct the per-row CA-review ``BooksReviewResolver`` (books-prep Flag #1).

    Pass the SAME ``journal`` + ``projection_store`` the live kernel uses (the api edge injects its
    Mongo-backed ``MongoJournalStore`` / ``MongoProjectionStore``) so the resolver commits CA-approved
    rows to the same heap, journals the same ledger, and writes gym cases the rest of the kernel reads.
    With both omitted it defaults to in-memory stores — convenient for sim runs, scripts, and tests.

    The resolver is independent of the run-loop: a CA decision is a tiny settlement micro-run, not a
    syscall, so no gateway / registry / hydration wiring is needed here.
    """
    return BooksReviewResolver(
        journal=journal or InMemoryJournalStore(),
        projection_store=projection_store or InMemoryProjectionStore(),
    )
