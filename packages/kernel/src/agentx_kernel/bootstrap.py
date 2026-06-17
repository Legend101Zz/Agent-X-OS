"""Phase-1 kernel bootstrap — the entry point the integration seam-proof drives."""

from agentx_contracts.protocols import RunInvoker, SyscallRegistry

from .gateway import Gateway
from .hydration import HydrationLoader
from .projections import Projections
from .run_loop import Phase1RunInvoker
from .settlement import SettlementCommitter
from .stores.memory import InMemoryJournalStore, InMemoryProjectionStore, InMemoryVault
from .verifier import RulesVerifier


def build_phase1_runinvoker(registry: SyscallRegistry | None = None) -> RunInvoker:
    """Construct the Phase-1 live/sim ``RunInvoker`` wired to the syscall ``registry``.

    Session B: in ``sim`` mode the swarm passes a registry of SimAdapters; in ``live`` mode the kernel
    passes the production registry. The loop is identical — only the registry differs.
    """
    journal = InMemoryJournalStore()
    projection_store = InMemoryProjectionStore()
    projections = Projections(projection_store, journal)
    gateway = Gateway(journal=journal, vault=InMemoryVault(), registry=registry)
    hydration = HydrationLoader(projection_store, journal)
    settlement = SettlementCommitter(journal=journal, projections=projections)
    return Phase1RunInvoker(
        journal=journal,
        projections=projections,
        hydration=hydration,
        gateway=gateway,
        settlement=settlement,
        verifier=RulesVerifier(),
    )
