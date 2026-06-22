"""The live Hermes runner — MiniMax drives the run trajectory via OpenAI-style tool calling (G1).

Lives kernel-side because it holds the model transport (credentialed); it implements the mandate-defined
``HarnessRunner`` Protocol so the run-loop can drive it exactly like the ``own`` double. The LLM PROPOSES
one action per step (think / call_tool / claim_facts / finish); the kernel DISPOSES (ring-checks + journals
effectful Calls through the gateway, fulfils reads + feeds the SyscallResult back, stamps run-provenance on
claimed facts, verifies + settles). Invariant #4: no brain in the live kernel — the brain proposes, scoped.

MiniMax M2/M3 are interleaved-thinking models: their assistant turns (``<think>…</think>`` in ``content``,
plus ``tool_calls``) are preserved verbatim in history across turns, and every ``tool_call_id`` is answered
with a ``role:"tool"`` message — the real ``SyscallResult`` for a ``call_tool``, a synthetic ack otherwise.
(API shape confirmed by research — see findings.md "Session F".)
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Protocol, cast, runtime_checkable

from agentx_contracts.enums import HarnessKind, RiskClass
from agentx_contracts.faculty import Faculty
from agentx_contracts.jsontypes import JsonObject, JsonValue
from agentx_contracts.mandate import MandateType
from agentx_contracts.memory import Fact, Provenance
from agentx_contracts.syscall import SyscallRequest, SyscallResult
from agentx_contracts.toolschema import TOOL_SCHEMAS, ToolSchema
from agentx_mandate.harness import Call, Claim, FacultyContext, Finish, HarnessAction, Think
from agentx_mandate.skill_packs import domain_pack_fragment, skill_pack_fragment


class HermesProtocolError(RuntimeError):
    """The model transport returned a response we cannot interpret as a chat completion."""


@runtime_checkable
class ChatTransport(Protocol):
    """An OpenAI-compatible chat-completions transport (HermesClient in live; a fake in tests)."""

    async def complete_chat(
        self, *, messages: list[JsonObject], tools: list[JsonObject]
    ) -> JsonObject: ...


# --- Control tools (harness-control, NOT syscalls) — defined here, not in the registry --------------
# These three are the same for every mandate. The syscall tools between ``think`` and ``claim_facts``
# are built per-mandate from the faculties' tool_manifests (see ``_build_tools``).
_THINK_TOOL: JsonObject = {
    "type": "function",
    "function": {
        "name": "think",
        "description": "Record a brief private reasoning note. No real-world effect.",
        "parameters": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    },
}

# Syscall risk classes mirror the gateway policy (the gateway re-stamps authoritatively; this lets the
# run-loop route read vs effectful before the gateway call).
_RISK_BY_SYSCALL: dict[str, RiskClass] = {
    "lead_research_batch": "read",
    "read_url": "read",
    "deep_research": "read",
    "score_lead": "read",
    "queue_manual_action": "read",
    "mark_outcome": "reversible_write",
    "draft_email": "external_message",
}

# Read-class tools whose name passes straight through to the same-named syscall
# (the mandate-discovery F1/F4/F5 reads, plus the shared in-OS deep_research). The
# LLM is told these are its tools; the runner forwards name + args to the gateway.
_MANDATE_DISCOVERY_READ_TOOLS: frozenset[str] = frozenset({
    "community_source_sample",
    "competitor_search",
    "buyer_channel_discovery",
    "deep_research",
})


def _resolve_tool_risk_map(ctx: FacultyContext) -> dict[str, RiskClass]:
    """Pick a per-mandate-type risk map when ``ctx.target['tool_risk_map']`` is set.

    Mandate-discovery's read adapters (community_source_sample, competitor_search,
    buyer_channel_discovery) are all read-class; the lead-finder defaults would
    misclassify them as ``read`` only by accident. Per-mandate-type override is
    the principled way.
    """
    override = ctx.target.get("tool_risk_map")
    if isinstance(override, dict):
        result: dict[str, RiskClass] = {}
        _valid_risks = {"read", "external_message", "reversible_write", "money", "irreversible"}
        for name, risk in override.items():
            if isinstance(name, str) and isinstance(risk, str) and risk in _valid_risks:
                result[name] = cast(RiskClass, risk)
        return result
    return _RISK_BY_SYSCALL

_CLAIM_FACTS_TOOL: JsonObject = {
    "type": "function",
    "function": {
        "name": "claim_facts",
        "description": (
            "Commit verified facts to memory. For the chosen lead claim predicate 'actionable_lead' "
            "(object=company) and 'qualified_lead_score' (object=score 0..1). evidence MUST quote text "
            "you actually read."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "facts": {
                "type": "array",
                "items": {
                        "type": "object",
                        "properties": {
                            "subject": {"type": "string"},
                            "predicate": {"type": "string"},
                            "object": {"type": "string"},
                            "confidence": {"type": "number"},
                            "evidence": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["subject", "predicate", "object", "evidence"],
                },
                }
            },
            "required": ["facts"],
        },
    },
}

_FINISH_TOOL: JsonObject = {
    "type": "function",
    "function": {
        "name": "finish",
        "description": "End the run. Provide a short summary of the outcome.",
        "parameters": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    },
}


def _exposed_syscalls(faculties: list[Faculty]) -> list[str]:
    """The ordered union of the faculties' tool_manifest syscalls that have a ToolSchema.

    First-seen order across faculties (in binding order) is preserved, so the generated tool list is
    deterministic. A manifest syscall with no ToolSchema (e.g. ``score_lead``, computed natively) is
    deliberately omitted — it is not exposed to the LLM.
    """
    seen: list[str] = []
    for faculty in faculties:
        for syscall in faculty.tool_manifest:
            if syscall in TOOL_SCHEMAS and syscall not in seen:
                seen.append(syscall)
    return seen


def _build_tools(faculties: list[Faculty]) -> tuple[list[JsonObject], dict[str, ToolSchema]]:
    """Build the OpenAI tool list + a tool_name→ToolSchema index FROM the mandate's faculties.

    Layout: ``think`` first, then one function per exposed syscall (registry schema), then
    ``claim_facts`` + ``finish``. For lead-finder this reproduces the legacy six tools byte-for-byte.
    """
    tools: list[JsonObject] = [_THINK_TOOL]
    index: dict[str, ToolSchema] = {}
    for syscall in _exposed_syscalls(faculties):
        schema = TOOL_SCHEMAS[syscall]
        tools.append(schema.as_tool())
        index[schema.tool_name] = schema
    tools.append(_CLAIM_FACTS_TOOL)
    tools.append(_FINISH_TOOL)
    return tools, index


def _build_prompts(
    mandate: MandateType | None, faculties: list[Faculty], ctx: FacultyContext
) -> tuple[str, str]:
    """Compose (system, user) prompts FROM the mandate.

    Lead-finder (and the no-mandate back-compat default) use the LEGACY renderers verbatim, so the live
    lead-finder prompt is byte-identical (regression-locked). Every other mandate uses the GENERIC
    composer: ``charter.goal`` + the faculties' skill-pack fragments + constraints + tool list + target.
    """
    if mandate is None or mandate.name == "lead-finder":
        return _system_prompt(ctx), _user_prompt(ctx)
    return _compose_system_prompt(mandate, faculties, ctx), _compose_user_prompt(mandate)


def _compose_system_prompt(mandate: MandateType, faculties: list[Faculty], ctx: FacultyContext) -> str:
    charter = mandate.charter
    lines: list[str] = [charter.goal.strip(), ""]
    fragments = [skill_pack_fragment(f.skill_pack).strip() for f in faculties]
    domain_fragment = domain_pack_fragment(mandate.domain_pack.name).strip()
    if domain_fragment:
        fragments.append(domain_fragment)
    fragments = [frag for frag in fragments if frag]
    if fragments:
        lines.append("\n\n".join(fragments))
        lines.append("")
    if charter.constraints:
        lines.append("Hard constraints:")
        lines.extend(f"  - {constraint}" for constraint in charter.constraints)
        lines.append("")
    lines.append("Act ONE STEP AT A TIME — call exactly ONE tool per turn. Tools:")
    lines.append("  - think(summary): a brief plan / reasoning note.")
    for syscall in _exposed_syscalls(faculties):
        schema = TOOL_SCHEMAS[syscall]
        lines.append(f"  - {schema.tool_name}: {schema.description}")
    lines.append(
        "  - claim_facts(facts): commit verified facts (subject, predicate, object, confidence, evidence)."
    )
    lines.append("  - finish(summary): end the run.")
    lines.append("")
    lines.append(f"Target: {json.dumps(ctx.target, sort_keys=True)}")
    return "\n".join(lines).strip()


def _compose_user_prompt(mandate: MandateType) -> str:
    return (
        "Begin. Plan briefly with think, then take it one tool call at a time; I will return each "
        "tool's result."
    )


def _normalize_args(ref: str | None, args: JsonObject) -> JsonObject:
    """Apply the named kernel-side arg-normalizer (default identity).

    The normalizers reproduce the legacy lead-finder arg shaping exactly so the generated syscall
    requests are byte-identical. New syscalls use identity (tool args pass straight through).
    """
    if ref == "search_leads":
        return _normalize_search_leads(args)
    if ref == "read_url":
        return _normalize_read_url(args)
    if ref == "draft_email":
        return _normalize_draft_email(args)
    return dict(args)


def _normalize_search_leads(args: JsonObject) -> JsonObject:
    criteria: JsonObject = {}
    for key in ("icp", "location", "query"):
        value = args.get(key)
        if isinstance(value, str) and value:
            criteria[key] = value
    excluded = args.get("exclude_domains")
    if isinstance(excluded, list):
        criteria["exclude_domains"] = [host for host in excluded if isinstance(host, str) and host]
    raw_count = args.get("count")
    count = raw_count if isinstance(raw_count, int) and raw_count > 0 else 5
    return {"criteria": criteria, "count": count}


def _normalize_read_url(args: JsonObject) -> JsonObject:
    return {"lead_id": str(args.get("lead_id", "")), "url": str(args.get("url", ""))}


def _normalize_draft_email(args: JsonObject) -> JsonObject:
    return {
        "to": str(args.get("to", "founder-review@agent-x.local")),
        "subject": str(args.get("subject", "")),
        "body": str(args.get("body", "")),
        "lead_id": str(args.get("lead_id", "")),
        "mode": "draft",
    }


def _system_prompt(ctx: FacultyContext) -> str:
    """Build the live LLM's system prompt.

    If ``ctx.target['system_prompt_override']`` is set (per-mandate-type), use
    it. ``${segment}``, ``${geography}``, and ``${time_window}`` placeholders
    in the override are substituted from the target — that's how a generic
    mandate-discovery prompt template becomes per-run personalised.

    This is the principled way for a new mandate type to teach the LLM its
    own vocabulary: the lead-finder default below assumes the LLM is running
    a research-and-draft loop, which is wrong for read-only mandates like
    mandate-discovery.
    """
    override = ctx.target.get("system_prompt_override")
    if isinstance(override, str) and override.strip():
        target = ctx.target
        return (
            override
            .replace("${segment}", str(target.get("segment", "")))
            .replace("${geography}", str(target.get("geography", "")))
            .replace("${time_window}", str(target.get("time_window", "")))
        )
    target = ctx.target
    icp = str(target.get("icp", "qualified B2B prospects"))
    location = str(target.get("location", ""))
    count = target.get("count", 1)
    lead_url = str(target.get("lead_url", "")).strip()
    lead_company = str(target.get("lead_company", "")).strip()
    task = str(target.get("task", "")).strip()
    target_instructions = (
        (
            "A specific lead was supplied by the operator. Work ONLY on this lead; do not replace it with "
            "another prospect.\n"
            f"Lead company: {lead_company or 'unknown — determine from the supplied site'}.\n"
            f"Lead URL: {lead_url}.\n"
            f"Operator task: {task or 'research, qualify, and draft grounded outreach'}.\n"
            "Start by calling read_url with lead_id='provided_lead' and the exact supplied URL. You may read "
            "additional pages on the same organisation if needed, but do not search for unrelated leads.\n\n"
        )
        if lead_url
        else f"Target ICP: {icp}. Location: {location or 'any'}. Leads wanted: {count}.\n\n"
    )
    return (
        "You are the lead-finder faculty of Agent-X, an accountable agent OS. Find ONE genuinely "
        "founder-SENDABLE B2B lead for the target ICP and draft a grounded outreach email for owner approval.\n\n"
        f"{target_instructions}"
        "Act ONE STEP AT A TIME — call exactly ONE tool per turn. Tools:\n"
        "  - think(summary): a brief plan / reasoning note.\n"
        "  - search_leads(query, icp, location, exclude_domains, count): web-search for real prospect "
        "businesses' OWN websites. Pass a SPECIFIC query; exclude_domains is a flat list of hostnames.\n"
        "  - read_url(lead_id, url): read ONE candidate's page — copy lead_id and url verbatim from a "
        "search result — to extract a named decision-maker/role, a reachable contact path, and a buying signal.\n"
        "  - draft_email(to, subject, body, lead_id): DRAFT (never send) personalised outreach.\n"
        "  - claim_facts(facts): commit verified facts for the chosen lead.\n"
        "  - finish(summary): end the run.\n"
        "If a tool returns an error or empty/irrelevant results, refine the query and retry — never repeat the "
        "same failing call.\n\n"
        "Hard rules:\n"
        "1. Research (read-only) BEFORE drafting. Ground EVERY claim and the email in text you actually read — "
        "never invent a name, signal, or URL.\n"
        "2. If the ICP describes someone who would BUY an AI lead-finder (founders, agencies, SMB operators), do "
        "NOT return other lead-generation vendors/agencies — they are COMPETITORS, not buyers. Pick a real CUSTOMER.\n"
        "3. A sendable lead needs a real organisation, a named decision-maker or specific role, a reachable "
        "contact URL, and a citable buying signal. If you cannot ground all four, finish and say so honestly.\n"
        "4. draft_email is DRAFT ONLY (it parks for human approval). Address the real person/role, cite the real "
        "signal, include the reachable URL.\n"
        "5. Claim the chosen lead's facts with claim_facts (predicates actionable_lead + qualified_lead_score, "
        "evidence quoted from what you actually read) BEFORE you call draft_email — drafting pauses the run for "
        "human approval, so the claims must be committed first."
    )


def _resolve_tools(ctx: FacultyContext) -> list[JsonObject]:
    """Pick per-mandate-type tool definitions when ``ctx.target['tools']`` is set.

    The lead-finder defaults assume a research-and-draft flow; read-only
    mandates like mandate-discovery need to declare their own tool list
    (community_source_sample, competitor_search, buyer_channel_discovery)
    so the LLM can call them.
    """
    override = ctx.target.get("tools")
    if isinstance(override, list) and all(isinstance(item, dict) for item in override):
        return cast(list[JsonObject], override)
    return _LEAD_FINDER_DEFAULT_TOOLS


# Lead-finder default tool list — six OpenAI tools: think, search_leads, read_url,
# draft_email, claim_facts, finish. Defined as a list (not a generator) so the bytes
# match the pre-generalization runner and the regression-lock test holds.
_LEAD_FINDER_DEFAULT_TOOLS: list[JsonObject] = [
    _THINK_TOOL,
    {
        "type": "function",
        "function": {
            "name": "search_leads",
            "description": (
                "Web-search for candidate prospect ORGANISATIONS. Pass a SPECIFIC query targeting real "
                "businesses' OWN websites — never articles, 'top 10' listicles, directories, or social media."
            ),
            "parameters": {
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
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_url",
            "description": "Read ONE candidate's page. Copy lead_id and url verbatim from a search result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string", "description": "id of a lead from the last search result"},
                    "url": {"type": "string", "description": "that lead's url"},
                },
                "required": ["lead_id", "url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_email",
            "description": "DRAFT (never send) personalised outreach. Parks for human approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "lead_id": {"type": "string"},
                },
                "required": ["subject", "body", "lead_id"],
            },
        },
    },
    _CLAIM_FACTS_TOOL,
    _FINISH_TOOL,
]


def _user_prompt(ctx: FacultyContext) -> str:
    lead_url = ctx.target.get("lead_url")
    if isinstance(lead_url, str) and lead_url.strip():
        return (
            "Begin. Plan briefly with think, then call read_url for lead_id='provided_lead' and the exact "
            "operator-supplied URL. Research only this organisation, claim grounded facts, then draft for approval."
        )
    return (
        "Begin. Plan briefly with think, then call_tool lead_research_batch with a specific query for the ICP. "
        "Take it one tool call at a time; I will return each tool's result."
    )


@dataclass
class HermesSession:
    """One run's MiniMax-driven session. Holds the message history and maps each turn to one HarnessAction."""

    transport: ChatTransport
    ctx: FacultyContext
    tools: list[JsonObject]
    tool_index: dict[str, ToolSchema]
    system_prompt: str
    user_prompt: str
    cursor: int = 0
    _messages: list[JsonObject] = field(default_factory=list, init=False)
    _started: bool = field(default=False, init=False)
    _pending_call_id: str | None = field(default=None, init=False)
    _call_index: int = field(default=0, init=False)

    def export_state(self) -> JsonObject:
        """Return the complete process-safe continuation state for a parked live run."""
        return {
            "messages": cast(JsonValue, deepcopy(self._messages)),
            "started": self._started,
            "pending_call_id": self._pending_call_id,
            "call_index": self._call_index,
            "cursor": self.cursor,
        }

    def restore_state(self, state: JsonObject) -> None:
        """Restore history exactly; no prior paid/model turn is regenerated during resume."""
        raw_messages = state.get("messages")
        if not isinstance(raw_messages, list) or not all(isinstance(message, dict) for message in raw_messages):
            raise HermesProtocolError("persisted Hermes state has invalid messages")
        raw_started = state.get("started")
        raw_pending = state.get("pending_call_id")
        raw_call_index = state.get("call_index")
        raw_cursor = state.get("cursor")
        if not isinstance(raw_started, bool):
            raise HermesProtocolError("persisted Hermes state has invalid started flag")
        if raw_pending is not None and not isinstance(raw_pending, str):
            raise HermesProtocolError("persisted Hermes state has invalid pending call id")
        if not isinstance(raw_call_index, int) or not isinstance(raw_cursor, int):
            raise HermesProtocolError("persisted Hermes state has invalid counters")
        self._messages = deepcopy(cast(list[JsonObject], raw_messages))
        self._started = raw_started
        self._pending_call_id = raw_pending
        self._call_index = raw_call_index
        self.cursor = raw_cursor

    async def step(self, observation: SyscallResult | None) -> HarnessAction:
        if observation is not None and self._pending_call_id is not None:
            self._messages.append(
                {
                "role": "tool",
                "tool_call_id": self._pending_call_id,
                "content": _bounded_tool_content(
                        {
                            "status": observation.status,
                            "fulfilled_by": observation.fulfilled_by,
                            "output": observation.output,
                            "error": observation.error,
                        }
                ),
                }
            )
            self._pending_call_id = None

        if not self._started:
            self._messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": self.user_prompt},
            ]
            self._started = True

        response = await self.transport.complete_chat(messages=self._messages, tools=self.tools)
        message = _sanitize_message_tool_calls(_first_message(response))
        self._messages.append(message)  # preserve the full assistant turn (incl. reasoning) — interleaved thinking
        self.cursor += 1

        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            content = message.get("content")
            summary = _strip_think(content) if isinstance(content, str) else ""
            return Think(summary=summary or "(no content returned)")

        # one action per turn: take the first tool call; ack any extras so history stays valid.
        for extra in tool_calls[1:]:
            extra_id = _tool_call_id(extra)
            if extra_id:
                self._messages.append(
                {"role": "tool", "tool_call_id": extra_id, "content": "ignored: one action per turn"}
                )

        call_id, name, args = _parse_tool_call(tool_calls[0])
        action = self._to_action(name, args)
        if isinstance(action, Call):
            self._pending_call_id = call_id  # the real SyscallResult answers this tool_call next step
        else:
            # think / claim_facts / finish produce no syscall result — synthetic ack keeps the history valid.
            self._messages.append({"role": "tool", "tool_call_id": call_id, "content": "acknowledged"})
        return action

    def _to_action(self, name: str, args: JsonObject) -> HarnessAction:
        if name == "think":
            return Think(summary=str(args.get("summary", "")) or "(empty)", detail=_json_obj(args.get("detail")))
        if name == "finish":
            output = _json_obj(args.get("output"))
            if not output:
                output = {"summary": str(args.get("summary", ""))}
            return Finish(output=output)
        if name == "claim_facts":
            raw = args.get("facts")
            return Claim(facts=self._to_facts(raw if isinstance(raw, list) else []))
        # Lead-finder regression lock (main): explicit branches reproduce the byte-identical
        # arg shaping for search_leads / read_url / draft_email so the legacy live LLM keeps working.
        if name == "search_leads":
            criteria: JsonObject = {}
            for key in ("icp", "location", "query"):
                value = args.get(key)
                if isinstance(value, str) and value:
                    criteria[key] = value
            excluded = args.get("exclude_domains")
            if isinstance(excluded, list):
                criteria["exclude_domains"] = [host for host in excluded if isinstance(host, str) and host]
            raw_count = args.get("count")
            count = raw_count if isinstance(raw_count, int) and raw_count > 0 else 5
            return self._call("lead_research_batch", {"criteria": criteria, "count": count})
        if name == "read_url":
            return self._call(
                "read_url", {"lead_id": str(args.get("lead_id", "")), "url": str(args.get("url", ""))}
            )
        if name == "draft_email":
            return self._call(
                "draft_email",
                {
                "to": str(args.get("to", "founder-review@agent-x.local")),
                "subject": str(args.get("subject", "")),
                "body": str(args.get("body", "")),
                "lead_id": str(args.get("lead_id", "")),
                "mode": "draft",
                },
            )
        # Mandate-discovery tool names → same-name syscalls (main). The runner's per-mandate
        # tool list (set via ``ctx.target['tools']``) declares these tools with the
        # EXACT names of the discovery_adapters' read syscalls, so a direct
        # name pass-through is the right routing here. The risk-class comes
        # from ``_resolve_tool_risk_map`` (above) which honours the per-mandate
        # ``tool_risk_map`` override.
        if name in _MANDATE_DISCOVERY_READ_TOOLS:
            return self._call(name, _json_obj(args))
        # Generic fallback (books-prep design): if no explicit branch matched, look the tool up in
        # the per-session index (built from the mandate's faculties' tool_manifests). This is how
        # new syscalls (ingest_document, export_ledger, queue_manual_action, …) get routed without
        # adding branches here. Default risk_class comes from TOOL_SCHEMAS[syscall].risk_class.
        schema = self.tool_index.get(name)
        if schema is not None:
            return self._call(schema.syscall_name, _normalize_args(schema.arg_normalizer_ref, args))
        # defensive: an unrecognised tool name is recorded as a thought rather than crashing the run.
        return Think(summary=f"unrecognised tool: {name}", detail={"args": _json_obj(args)})

    def _call(self, syscall: str, args: JsonObject) -> Call:
        self._call_index += 1
        # Per-mandate override (main) wins; otherwise TOOL_SCHEMAS is the source of truth (books-prep).
        risk_map = _resolve_tool_risk_map(self.ctx)
        schema = TOOL_SCHEMAS.get(syscall)
        if (
            schema is not None
            and schema.risk_class in {"read", "external_message", "reversible_write", "money", "irreversible"}
        ):
            risk_class: RiskClass = schema.risk_class
        else:
            risk_class = risk_map.get(syscall, "read")
        return Call(
            request=SyscallRequest(
                name=syscall,
                args=args,
                instance_id=self.ctx.instance_id,
                run_id=self.ctx.run_id,
                idempotency_key=f"{self.ctx.run_id}:{syscall}:{self._call_index}",
                ring=self.ctx.ring,
                risk_class=risk_class,
            )
        )

    def _to_facts(self, raw_facts: list[JsonValue]) -> list[Fact]:
        facts: list[Fact] = []
        for raw in raw_facts:
            if not isinstance(raw, dict):
                continue
            subject = str(raw.get("subject", "")).strip()
            predicate = str(raw.get("predicate", "")).strip()
            if not subject or not predicate:
                continue
            obj = str(raw.get("object", "")).strip()
            confidence = raw.get("confidence")
            conf = float(confidence) if isinstance(confidence, int | float) else 0.5
            conf = max(0.0, min(conf, 1.0))
            evidence = [item for item in _as_list(raw.get("evidence")) if item]
            if not evidence:
                evidence = [f"hermes:{self.ctx.run_id}:{subject}:{predicate}"]
            facts.append(
                Fact(
                id=f"{self.ctx.run_id}:{subject}:{predicate}",
                instance_id=self.ctx.instance_id,
                subject=subject,
                predicate=predicate,
                object=obj,
                confidence=conf,
                source="agent-inferred",
                provenance=Provenance(
                        run_id=self.ctx.run_id,
                        evidence=evidence,
                        note=f"hermes claim: {predicate}",
                ),
                status="probation",
                created_at=self.ctx.now,
                )
            )
        return facts


@dataclass
class HermesRunner:
    """``HarnessKind="hermes"`` — drives MiniMax over the injected chat transport."""

    transport: ChatTransport
    name: HarnessKind = "hermes"

    def start(
        self,
        *,
        context: FacultyContext,
        faculties: list[Faculty],
        cursor: int = 0,
        mandate: MandateType | None = None,
    ) -> HermesSession:
        # Hybrid tool/prompt resolution (rebase of books-prep onto main, Phase 13.5):
        #   1. If the operator set ``ctx.target['tools']`` (mandate-discovery pattern), use the
        #      override list verbatim — main's per-mandate-type behaviour. We still build an index
        #      so the generic fallback in ``_to_action`` can route any matching ToolSchema.
        #   2. Else, use our faculty-based builder — books-prep's pattern.
        override_tools = context.target.get("tools")
        if isinstance(override_tools, list) and all(isinstance(t, dict) for t in override_tools):
            tools = cast(list[JsonObject], override_tools)
            tool_index = _build_tool_index_from_overrides(cast(list[JsonObject], override_tools))
        else:
            tools, tool_index = _build_tools(faculties)
        system_prompt, user_prompt = _build_prompts(mandate, faculties, context)
        return HermesSession(
            transport=self.transport,
            ctx=context,
            tools=tools,
            tool_index=tool_index,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cursor=cursor,
        )


def _build_tool_index_from_overrides(override_tools: list[JsonObject]) -> dict[str, ToolSchema]:
    """Build a tool_name → ToolSchema index from an operator-supplied tool list.

    Only known ToolSchemas (from the contracts registry) end up in the index — the
    generic fallback in ``_to_action`` uses it to route the LLM's tool call to the
    correct syscall name. The function helps mypy narrow the JsonValue type at the
    call sites.
    """
    override_names: set[str] = set()
    for t in override_tools:
        if not isinstance(t, dict):
            continue
        func = t.get("function")
        if isinstance(func, dict):
            name = func.get("name")
            if isinstance(name, str):
                override_names.add(name)
    return {
        schema.tool_name: schema
        for schema in TOOL_SCHEMAS.values()
        if schema.tool_name in override_names
    }


def _first_message(response: JsonObject) -> JsonObject:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise HermesProtocolError("Hermes response had no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise HermesProtocolError("Hermes choice was not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise HermesProtocolError("Hermes choice had no message object")
    return message


def _sanitize_message_tool_calls(message: JsonObject) -> JsonObject:
    """Normalise every tool_call's ``function.arguments`` to a valid JSON string.

    MiniMax truncates a tool_call's arguments when generation hits max_tokens,
    producing an invalid JSON string. Re-submitting that assistant message makes
    MiniMax reject the ENTIRE next request with HTTP 400 ("invalid function
    arguments json string, tool_call_id: …"), crashing the run. We rewrite each
    arguments field to canonical JSON (or ``{}`` if unparseable) so the
    conversation history is always replayable. Mutates and returns ``message``.
    """
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return message
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function")
        if not isinstance(fn, dict):
            continue
        raw = fn.get("arguments")
        if isinstance(raw, str):
            try:
                fn["arguments"] = json.dumps(json.loads(raw))
            except (json.JSONDecodeError, ValueError):
                fn["arguments"] = "{}"
        elif isinstance(raw, dict):
            fn["arguments"] = json.dumps(raw)
        elif raw is None:
            fn["arguments"] = "{}"
    return message


def _parse_tool_call(tool_call: JsonValue) -> tuple[str, str, JsonObject]:
    call_id = _tool_call_id(tool_call)
    name = ""
    args: JsonObject = {}
    if isinstance(tool_call, dict):
        function = tool_call.get("function")
        if isinstance(function, dict):
            name = str(function.get("name", ""))
            raw_args = function.get("arguments")
            if isinstance(raw_args, str):
                try:
                    parsed = json.loads(raw_args)
                except json.JSONDecodeError:
                    parsed = {}
                if isinstance(parsed, dict):
                    args = cast(JsonObject, parsed)
            elif isinstance(raw_args, dict):
                args = raw_args
    return call_id, name, args


def _tool_call_id(tool_call: JsonValue) -> str:
    if isinstance(tool_call, dict):
        call_id = tool_call.get("id")
        if isinstance(call_id, str):
            return call_id
    return ""


def _json_obj(value: JsonValue | None) -> JsonObject:
    return value if isinstance(value, dict) else {}


# A syscall result is fed back into the LLM's message history every step. Large
# read payloads (an F1 community-source sample is dozens of posts × long
# body_text) accumulate across steps until the request exceeds MiniMax's context
# window and the API returns HTTP 400. The kernel's receipt store keeps the FULL
# output; the LLM only needs a bounded, skimmable view to reason over.
_TOOL_STR_CLIP = 320  # max chars per string field shown to the LLM
_TOOL_LIST_CLIP = 25  # max items per list shown to the LLM
_TOOL_CONTENT_MAX = 16_000  # hard cap on the serialized tool message (chars)


def _shrink_for_context(value: object, *, depth: int = 0) -> object:
    """Recursively clip strings/lists so a tool payload can't blow the context window."""
    if isinstance(value, str):
        return value if len(value) <= _TOOL_STR_CLIP else value[:_TOOL_STR_CLIP] + "…"
    if isinstance(value, dict):
        if depth >= 6:
            return {"…": f"{len(value)} keys"}
        return {str(k): _shrink_for_context(v, depth=depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        if depth >= 6:
            return f"[{len(value)} items]"
        clipped = [_shrink_for_context(v, depth=depth + 1) for v in list(value)[:_TOOL_LIST_CLIP]]
        if len(value) > _TOOL_LIST_CLIP:
            clipped.append(f"…(+{len(value) - _TOOL_LIST_CLIP} more items omitted)")
        return clipped
    return value


def _bounded_tool_content(payload: dict[str, object]) -> str:
    """Serialize a tool result for the LLM, bounded in size (per-field + total)."""
    shrunk = _shrink_for_context(payload)
    text = json.dumps(shrunk, default=str)
    if len(text) > _TOOL_CONTENT_MAX:
        text = text[:_TOOL_CONTENT_MAX] + ' …"(truncated for context budget)"'
    return text


def _as_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str)]


def _strip_think(content: str) -> str:
    import re

    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
