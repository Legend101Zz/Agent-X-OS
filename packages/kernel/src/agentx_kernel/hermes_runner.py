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
from agentx_contracts.memory import Fact, Provenance
from agentx_contracts.syscall import SyscallRequest, SyscallResult
from agentx_mandate.harness import Call, Claim, FacultyContext, Finish, HarnessAction, Think


class HermesProtocolError(RuntimeError):
    """The model transport returned a response we cannot interpret as a chat completion."""


@runtime_checkable
class ChatTransport(Protocol):
    """An OpenAI-compatible chat-completions transport (HermesClient in live; a fake in tests)."""

    async def complete_chat(
        self, *, messages: list[JsonObject], tools: list[JsonObject]
    ) -> JsonObject: ...


# Syscall risk classes mirror the gateway policy (the gateway re-stamps authoritatively; this lets the
# run-loop route read vs effectful before the gateway call).
_RISK_BY_SYSCALL: dict[str, RiskClass] = {
    "lead_research_batch": "read",
    "read_url": "read",
    "score_lead": "read",
    "queue_manual_action": "read",
    "mark_outcome": "reversible_write",
    "draft_email": "external_message",
}

_TOOLS: list[JsonObject] = [
    {
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
    },
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
    {
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
    },
    {
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
    },
]


def _system_prompt(ctx: FacultyContext) -> str:
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
                    "content": json.dumps(
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
                {"role": "system", "content": _system_prompt(self.ctx)},
                {"role": "user", "content": _user_prompt(self.ctx)},
            ]
            self._started = True

        response = await self.transport.complete_chat(messages=self._messages, tools=_TOOLS)
        message = _first_message(response)
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
        # defensive: an unrecognised tool name is recorded as a thought rather than crashing the run.
        return Think(summary=f"unrecognised tool: {name}", detail={"args": _json_obj(args)})

    def _call(self, syscall: str, args: JsonObject) -> Call:
        self._call_index += 1
        return Call(
            request=SyscallRequest(
                name=syscall,
                args=args,
                instance_id=self.ctx.instance_id,
                run_id=self.ctx.run_id,
                idempotency_key=f"{self.ctx.run_id}:{syscall}:{self._call_index}",
                ring=self.ctx.ring,
                risk_class=_RISK_BY_SYSCALL.get(syscall, "read"),
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

    def start(self, *, context: FacultyContext, faculties: list[Faculty], cursor: int = 0) -> HermesSession:
        return HermesSession(transport=self.transport, ctx=context, cursor=cursor)


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


def _as_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str)]


def _strip_think(content: str) -> str:
    import re

    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
