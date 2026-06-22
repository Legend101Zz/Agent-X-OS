"""Extraction faculty (books-prep) — proposes one ``ingest_document`` READ intent per provided doc.

Thin like ``research``: it only emits the read intent. The rows are produced where the read is
FULFILLED — in live mode the gateway routes ``ingest_document`` to the deterministic
``IngestDocumentAdapter`` (pdfplumber/openpyxl); in sim mode the kernel fulfils it natively with
clearly-synthetic transactions. Either way the parsed rows land in ``ctx.scratchpad['transactions']``
for the categoriser. NEVER invents rows (invariant #4: the brain does no I/O).
"""

from __future__ import annotations

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.syscall import SyscallRequest

from agentx_mandate.harness import Call, FacultyContext, HarnessAction

FACULTY = Faculty(
    name="extraction",
    skill_pack="skill_pack:books-prep/extraction@0.1.0",
    tool_manifest=["ingest_document"],
    eval_slice="gym:books-prep/extraction",
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["document_parsing"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def _documents(target: JsonObject) -> list[JsonObject]:
    """Normalise ``target.documents`` (list of str doc_ids or {doc_id,path} dicts) to arg dicts."""
    raw = target.get("documents")
    if not isinstance(raw, list):
        return []
    docs: list[JsonObject] = []
    for entry in raw:
        if isinstance(entry, str) and entry:
            docs.append({"doc_id": entry})
        elif isinstance(entry, dict):
            doc_id = entry.get("doc_id") or entry.get("path")
            if isinstance(doc_id, str) and doc_id:
                args: JsonObject = {"doc_id": doc_id}
                path = entry.get("path")
                if isinstance(path, str) and path:
                    args["path"] = path
                docs.append(args)
    return docs


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    actions: list[HarnessAction] = []
    for index, args in enumerate(_documents(ctx.target), start=1):
        actions.append(
            Call(
                request=SyscallRequest(
                    name="ingest_document",
                    args=args,
                    instance_id=ctx.instance_id,
                    run_id=ctx.run_id,
                    idempotency_key=f"{ctx.run_id}:extraction:ingest_document:{index}",
                    ring=ctx.ring,
                    risk_class="read",
                )
            )
        )
    return actions
