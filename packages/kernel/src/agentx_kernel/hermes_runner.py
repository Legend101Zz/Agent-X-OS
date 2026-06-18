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
from dataclasses import dataclass, field
from typing import Protocol, cast, runtime_checkable

from agentx_contracts.enums import HarnessKind, RiskClass
from agentx_contracts.faculty import Faculty
from agentx_contracts.jsontypes import JsonObject, JsonValue
from agentx_contracts.memory import Fact, Provenance
from agentx_contracts.syscall import SyscallRequest, SyscallResult
from agentx_mandate.harness import Call, Claim, FacultyContext, Finish, HarnessAction, HarnessSession, Think


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
            "name": "call_tool",
            "description": (
                "Propose a syscall INTENT (the kernel executes it and returns the result). "
                "name is one of: lead_research_batch, read_url, draft_email."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "enum": ["lead_research_batch", "read_url", "draft_email"],
                    },
                    "args": {"type": "object"},
                },
                "required": ["name", "args"],
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
    return (
        "You are the lead-finder faculty of Agent-X, an accountable agent OS. Find ONE genuinely "
        "founder-SENDABLE B2B lead for the target ICP and draft a grounded outreach email for owner approval.\n\n"
        f"Target ICP: {icp}. Location: {location or 'any'}. Leads wanted: {count}.\n\n"
        "Act ONE STEP AT A TIME — call exactly ONE tool per turn (think, call_tool, claim_facts, finish).\n"
        "Available syscalls for call_tool:\n"
        "  - lead_research_batch(criteria, count): web search for candidate prospect ORGANISATIONS. "
        "criteria = {icp, location, query, exclude_domains?}. Form a SPECIFIC query targeting real "
        "businesses' OWN websites — never articles, 'top 10' listicles, directories, or social media.\n"
        "  - read_url(lead_id, url): read ONE candidate's official page to extract a named decision-maker "
        "or specific role, a reachable contact path (contact/booking/mailto/tel), and a concrete buying signal.\n"
        "  - draft_email(to, subject, body, lead_id, mode='draft'): DRAFT (never send) personalised outreach.\n\n"
        "Hard rules:\n"
        "1. Research (read-only) BEFORE drafting. Ground EVERY claim and the email in text you actually read — "
        "never invent a name, signal, or URL.\n"
        "2. If the ICP describes someone who would BUY an AI lead-finder (founders, agencies, SMB operators), do "
        "NOT return other lead-generation vendors/agencies — they are COMPETITORS, not buyers. Pick a real CUSTOMER.\n"
        "3. A sendable lead needs a real organisation, a named decision-maker or specific role, a reachable "
        "contact URL, and a citable buying signal. If you cannot ground all four, finish and say so honestly.\n"
        "4. draft_email is DRAFT ONLY (it parks for human approval). Address the real person/role, cite the real "
        "signal, include the reachable URL.\n"
        "5. Before finishing successfully, claim_facts for the chosen lead (actionable_lead + qualified_lead_score)."
    )


def _user_prompt(ctx: FacultyContext) -> str:
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
        if name == "call_tool":
            syscall = str(args.get("name", ""))
            self._call_index += 1
            return Call(
                request=SyscallRequest(
                    name=syscall,
                    args=_json_obj(args.get("args")),
                    instance_id=self.ctx.instance_id,
                    run_id=self.ctx.run_id,
                    idempotency_key=f"{self.ctx.run_id}:{syscall}:{self._call_index}",
                    ring=self.ctx.ring,
                    risk_class=_RISK_BY_SYSCALL.get(syscall, "read"),
                )
            )
        # defensive: an unrecognised tool name is recorded as a thought rather than crashing the run.
        return Think(summary=f"unrecognised tool: {name}", detail={"args": _json_obj(args)})

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

    def start(self, *, context: FacultyContext, faculties: list[Faculty], cursor: int = 0) -> HarnessSession:
        # cursor>0 (parked-run resume) is Step B (G2); live runs start fresh.
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
