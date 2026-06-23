"""The TOOL-SCHEMA registry — the syscall → LLM-tool-schema mapping (harness generalization seam).

Lives in ``agentx_contracts`` (NOT the kernel) on purpose: ``.importlinter`` forbids ``agentx_kernel``
(home of the Hermes runner) from importing ``agentx_syscall``, so the runner cannot read schemas from
the adapters. The shared seam both lanes may import is ``agentx_contracts`` — so the mapping the runner
needs to build its tool set + risk map lives here, and the syscall adapters can read it too.

The runner builds its exposed tools as: the control tools (``think``/``claim_facts``/``finish``, which
are harness-control and stay defined in the runner) PLUS one function per syscall in the union of the
mandate's faculties' ``tool_manifest``s **that has an entry here**. A manifest syscall with no
``ToolSchema`` (e.g. ``score_lead``, computed natively) is deliberately NOT exposed as an LLM tool.

Lead-finder's three entries (``lead_research_batch``→``search_leads``, ``read_url``, ``draft_email``)
reproduce today's hard-coded schemas/descriptions byte-for-byte, so the generalized runner's generated
tools are identical to the legacy ones (regression-locked in the kernel tests).
"""

from __future__ import annotations

from .base import AgentXModel
from .enums import RiskClass
from .jsontypes import JsonObject, JsonSchema


class ToolSchema(AgentXModel):
    """One syscall's exposure as an OpenAI-style function tool (WHAT the LLM may request)."""

    syscall_name: str
    """The kernel syscall / intent name a faculty names in its ``tool_manifest``."""
    tool_name: str
    """The function name exposed to the LLM (often equals ``syscall_name``; lead-research differs)."""
    description: str
    parameters: JsonSchema
    """The JSON-Schema for the function's parameters (the ``function.parameters`` object)."""
    risk_class: RiskClass
    """Mirrors the gateway policy so the run-loop can route read vs effectful before the gateway call."""
    arg_normalizer_ref: str | None = None
    """Optional named kernel-side normalizer that shapes LLM args → syscall args (default: identity)."""

    def as_tool(self) -> JsonObject:
        """Render the OpenAI ``{"type":"function","function":{...}}`` tool object."""
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# Keyed by SYSCALL name (the name a faculty's tool_manifest carries). ``score_lead`` is intentionally
# absent: it is in ``judgment``'s manifest but is computed natively and never exposed as an LLM tool.
TOOL_SCHEMAS: dict[str, ToolSchema] = {
    # --- lead-finder (reproduces the legacy hard-coded schemas byte-for-byte) ---------------
    "lead_research_batch": ToolSchema(
        syscall_name="lead_research_batch",
        tool_name="search_leads",
        description=(
            "Web-search for candidate prospect ORGANISATIONS. Pass a SPECIFIC query targeting real "
            "businesses' OWN websites — never articles, 'top 10' listicles, directories, or social media."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "the search query"},
                "icp": {"type": "string"},
                "location": {"type": "string"},
                "exclude_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "hostnames to exclude, e.g. ['justdial.com','practo.com']",
                },
                "count": {"type": "integer"},
            },
            "required": ["query"],
        },
        risk_class="read",
        arg_normalizer_ref="search_leads",
    ),
    "read_url": ToolSchema(
        syscall_name="read_url",
        tool_name="read_url",
        description="Read ONE candidate's page. Copy lead_id and url verbatim from a search result.",
        parameters={
            "type": "object",
            "properties": {
                "lead_id": {"type": "string", "description": "id of a lead from the last search result"},
                "url": {"type": "string", "description": "that lead's url"},
            },
            "required": ["lead_id", "url"],
        },
        risk_class="read",
        arg_normalizer_ref="read_url",
    ),
    "draft_email": ToolSchema(
        syscall_name="draft_email",
        tool_name="draft_email",
        description="DRAFT (never send) personalised outreach. Parks for human approval.",
        parameters={
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "lead_id": {"type": "string"},
            },
            "required": ["subject", "body", "lead_id"],
        },
        risk_class="external_message",
        arg_normalizer_ref="draft_email",
    ),
    # --- books-prep ------------------------------------------------------------------------
    "ingest_document": ToolSchema(
        syscall_name="ingest_document",
        tool_name="ingest_document",
        description=(
            "Parse ONE provided financial document (digital-text PDF bank statement, Excel, or CSV) into "
            "structured transaction rows with a per-row source citation. Deterministic — never invent rows. "
            "A scanned/image PDF (no extractable text) returns an error so the document routes to the queue."
        ),
        parameters={
            "type": "object",
            "properties": {
                "doc_id": {
                    "type": "string",
                    "description": "id/name of the document to parse (from the provided document list)",
                },
                "path": {"type": "string", "description": "the document path or ref to ingest, if known"},
            },
            "required": ["doc_id"],
        },
        risk_class="read",
    ),
    "export_ledger": ToolSchema(
        syscall_name="export_ledger",
        tool_name="export_ledger",
        description=(
            "Write the categorized, source-cited transactions to a clean .xlsx ledger for CA review. "
            "Parks for human approval (L1). Rows come from the run's categorized transactions; you only "
            "name the output file."
        ),
        parameters={
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "output .xlsx filename for the ledger"},
            },
            "required": [],
        },
        risk_class="reversible_write",
    ),
    "queue_manual_action": ToolSchema(
        syscall_name="queue_manual_action",
        tool_name="queue_manual_action",
        description=(
            "Push a low-confidence or ambiguous transaction to the CA review queue with a reason. "
            "Use for any row below the confidence threshold or flagged as extraction-suspect."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "the review action, e.g. 'review_transaction'"},
                "reason": {"type": "string", "description": "why this item needs CA review"},
                "transaction": {"type": "object", "description": "the flagged transaction row"},
            },
            "required": ["action"],
        },
        risk_class="reversible_write",
    ),
}


def tool_schema_for(syscall_name: str) -> ToolSchema | None:
    """Return the ``ToolSchema`` for a syscall, or ``None`` when it is not LLM-exposed."""
    return TOOL_SCHEMAS.get(syscall_name)
