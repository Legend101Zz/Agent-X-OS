# Agent-X Syscall Tool Landscape Research

Created: 2026-06-17

Purpose: find tools, repos, and infrastructure that can help us build the Agent-X external call layer: how mandates read the world, request actions, execute safely, and settle outcomes.

## Executive Answer

The tool ecosystem already has many useful pieces, but none of them should become the Agent-X kernel.

Use them like this:

```text
Read/perceive:
  Agent Reach, Firecrawl, Crawl4AI, Exa, GitHub CLI/MCP

Act through APIs:
  Composio, Pipedream, Activepieces, Nango, Arcade, official APIs

Act through browser/computer-use:
  Playwright MCP, Stagehand, browser-use, Steel, Hyperbrowser, CUA, Agent S

Execute risky code:
  E2B, Daytona, Modal, Beam, SWE-ReX

Communicate:
  AgentMail, Patter, Vapi, AgentPhone, Kapso, Cloudflare Agentic Inbox

Coordinate/memory:
  Mem0, MCP Agent Mail, Cloudflare Agents, Agent-X's own verified heap

Agent-X owns:
  mandate authority, tenancy, approval policy, syscall registry,
  idempotency, audit, verification, settlement, trust, billing, memory.
```

The right shape is:

```text
MandateRun
  -> asks for capability
Agent-X Gateway
  -> checks ring, policy, tenant, approval, idempotency
Adapter/Tool
  -> calls Composio/Pipedream/browser-use/E2B/etc.
Settlement
  -> records verified effect, memory, trust, billing, and next mandate
```

Do not expose raw third-party tools directly to the harness. Wrap them behind Agent-X syscall contracts.

## MVP Recommendation

For the first Agent-X mandate, do not start with WhatsApp, voice, payments, ads, or full computer-use.

Start with:

```text
Lead Finding Mandate
  read: Agent Reach + Exa/Firecrawl/Crawl4AI
  decide: Agent-X scoring rubric
  output: lead list + evidence + suggested action
  action: manual projection in admin dashboard
  optional: Gmail/AgentMail draft
  settlement: human marks contacted/replied/booked/not-fit
```

Then add:

```text
Approved Email Syscall
  Nango/Composio/Pipedream for auth/tooling
  Agent-X Gateway for approval/idempotency/audit
```

Only after that add browser fallback, sandboxed execution, phone, and WhatsApp.

## The Agent-X Filter

For each repo/tool, ask:

1. Does it help a mandate perceive, act, execute, or verify?
2. Does it handle auth/tenancy, or do we still need to own that?
3. Can it be wrapped behind a typed syscall?
4. Can it run in manual projection, draft, approved, and bounded autonomy modes?
5. Does it create auditable outcomes, or only raw activity logs?
6. Is it stable enough for production, or only good for prototypes?
7. Does it increase our moat, or make us dependent on somebody else's primitive?

## Recommended Stack Map

```text
Reality
  web, GitHub, Reddit, X, email, phone, WhatsApp, CRM, calendar, payments

Perception adapters
  Agent Reach, Firecrawl, Crawl4AI, Exa, GitHub MCP/CLI

Action adapters
  Composio, Pipedream, Activepieces, Nango, Arcade, official APIs

Fallback action layer
  Playwright MCP, Stagehand, browser-use, Steel, Hyperbrowser, CUA, Agent S

Safe execution
  E2B, Daytona, Modal, Beam, SWE-ReX

Agent-X kernel
  syscall registry, gateway policy, approval, audit, verified heap, settlement

Mandates
  lead finding, outbound drafting, inbox handling, scheduling, reporting
```

## Best Immediate Tools For Agent-X

### 1. Agent Reach

Repo: [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach/blob/main/docs/README_en.md)

What it is: a capability layer for agent web/social reading. It chooses access paths for Web, Twitter/X, Reddit, GitHub, YouTube, Bilibili, RSS, Exa search, and more. Its README says it is "one level above any specific implementation" and handles selection, installation, health checks, and routing while upstream tools do the actual reading.

Why it matters for Agent-X:

- Very aligned with the Agent-X idea of faculties.
- Useful for the `research` and `lead_discovery` faculties.
- Great for Level 0 manual projection: "find leads, collect evidence, score them, queue actions."
- It already encodes the idea of "backend list with fallbacks", which we should copy for syscall adapters.

Where it fits:

```text
Faculty: research
Syscalls:
  search_web()
  read_url()
  search_github()
  search_reddit()
  read_youtube_transcript()
  search_x()
```

Do not use it for:

- sending messages
- updating CRM
- booking calls
- money movement

Agent-X verdict: use early.

### 2. Composio

Repo: [ComposioHQ/composio](https://github.com/ComposioHQ/composio)

What it is: an agent integration platform/SDK. The GitHub repo describes SDKs for Python and TypeScript agentic frameworks and lists provider support across OpenAI, Anthropic, LangChain, LangGraph, LlamaIndex, Gemini, CrewAI, AutoGen, etc.

Why it matters for Agent-X:

- Useful for quick access to many SaaS tools.
- Useful for `send_email`, `calendar`, `crm`, Slack/Notion/GitHub style actions.
- Can help us avoid hand-building every connector in phase 1.

Risk:

- Tool catalog is not the same as mandate authority.
- We still need our own per-tenant permission model, approval, idempotency, and settlement.

Where it fits:

```text
Adapter accelerator:
  composio_adapter.execute(toolkit, action, args)

Agent-X syscall:
  update_crm_lead_status()
  create_calendar_event()
  send_email()
```

Agent-X verdict: use for long-tail SaaS actions, not as the kernel.

### 3. Pipedream

Repo/org: [PipedreamHQ](https://github.com/PipedreamHQ)  
Docs: [Pipedream MCP](https://pipedream.com/docs/connect/mcp)

What it is: serverless integration and compute platform. Its docs position Pipedream MCP for productivity automation, data analysis, content creation, customer support, and developer workflows. Its examples mention access to thousands of APIs/tools.

Why it matters:

- Good for webhooks and long-tail SaaS integrations.
- Good for fast proof-of-concept when a customer uses a random CRM or database.
- Could power Level 1/2 syscalls before we write native adapters.

Risk:

- External dependency.
- Need to normalize errors and audit events into Agent-X.
- We must not let Pipedream actions bypass mandate policy.

Agent-X verdict: useful connector backend for phase 1 and 2.

### 4. Activepieces

Repo: [activepieces/activepieces](https://github.com/activepieces/activepieces)

What it is: open-source automation platform with AI agents, MCPs, and a type-safe "pieces" framework in TypeScript. Their GitHub page says contributed pieces become MCP servers usable through Claude Desktop, Cursor, or Windsurf.

Why it matters:

- Self-hostable automation layer.
- Good reference for how to package integrations as "pieces".
- Useful if we want an open-source connector/workflow substrate.

Agent-X use:

```text
Borrow pattern:
  "piece" = adapter package

Do not copy:
  Zapier-style workflow as the core primitive
```

Agent-X verdict: strong pattern source; possible self-hosted connector substrate.

### 5. Nango

Repo: [NangoHQ/nango](https://github.com/nangohq/nango)

What it is: open-source product integrations platform. Its README says it supports 800+ APIs, handles auth, execution, scaling, and observability, and works with backend languages, AI coding tools, and agent SDKs.

Why it matters:

- Auth and per-customer integration configuration are hard.
- Agent-X needs tenant-owned OAuth connections.
- Nango is more "product integrations" than "agent tool toy", which may fit Agent-X better for SaaS.

Agent-X use:

```text
Use for:
  OAuth
  token refresh
  per-customer config
  syncs/webhooks
  long-tail SaaS adapters
```

Agent-X verdict: high priority to evaluate for tenant auth and sync.

### 6. Arcade

Repo: [ArcadeAI/arcade-mcp](https://github.com/ArcadeAI/arcade-mcp)

What it is: a Python framework for MCP servers and tools; the repo says it powers thousands of prebuilt tools across Arcade's MCP servers. Arcade's ecosystem emphasizes managed auth and user-level tool calls.

Why it matters:

- It is close to the "secure agent authorization" problem.
- Useful reference for user auth and tool execution.
- Could be an adapter backend for some categories.

Agent-X caveat:

- Arcade may solve tool auth/execution, but Agent-X must still own mandate authority, settlement, and business memory.

Agent-X verdict: study carefully; possibly use for auth/tool runtime.

## Read/Search Layer

### Firecrawl

Repo: [firecrawl/firecrawl](https://github.com/firecrawl/firecrawl)

What it is: open-source API for search, scrape, crawl, extract, and agentic web retrieval. Search results describe an `/agent` endpoint where you describe what you need and it searches/navigates/retrieves.

Agent-X fit:

- Lead research
- company page extraction
- pricing extraction
- competitor monitoring
- evidence collection for lead scores

Risk:

- Web data is not verified business outcome.
- Needs provenance and snapshots inside Agent-X.

Verdict: useful perception adapter.

### Crawl4AI

Repo: [unclecode/crawl4ai](https://github.com/unclecode/crawl4ai)

What it is: open-source LLM-friendly web crawler/scraper that turns web pages into clean Markdown for RAG, agents, and data pipelines.

Agent-X fit:

- Self-hosted web extraction.
- Good when we want lower cost and more control than Firecrawl.
- Good for building lead/company profiles.

Verdict: strong open-source read adapter.

### Exa MCP / Exa search

Repo: [exa-labs/exa-mcp-server](https://github.com/exa-labs/exa-mcp-server)

What it is: MCP server for web search, code search, and company research.

Agent-X fit:

- Research faculty.
- Lead discovery.
- Company/person search.
- "Find likely buyers for this mandate" queries.

Verdict: useful, especially when search quality matters.

## Browser Automation / Computer Use Layer

Use browser/computer-use as a fallback when no clean API exists, or for Level 0/1 manual projection and admin tasks. Do not make browser automation the first-class way to do high-risk business effects if an official API exists.

### Playwright MCP

Repo: [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp)  
Docs: [Playwright MCP docs](https://playwright.dev/docs/getting-started-mcp)

What it is: MCP server that gives browser automation through structured accessibility snapshots. The repo says it enables LLMs to interact with web pages without relying on screenshots/vision.

Agent-X fit:

- reliable browser interaction
- SaaS admin tasks
- scraping pages behind login
- UI verification
- fallback for unsupported tools

Verdict: high priority. Use with strict sandbox and approval.

### Stagehand

Repo: [browserbase/stagehand](https://github.com/browserbase/stagehand)  
Docs: [Stagehand intro](https://docs.stagehand.dev/v3/first-steps/introduction)

What it is: browser automation framework combining natural language and code. Browserbase says it provides primitives like act, extract, observe, and agent.

Agent-X fit:

- higher-level browser automation than raw Playwright
- good for admin workflows where code plus natural-language extraction helps

Reddit signal:

One r/AI_Agents thread says browser-use got tasks wrong/hallucinated clicks for the poster, while Stagehand sessions completed more often in that user's specific case. Treat as anecdotal, but it matches the production concern: browser agents need guardrails and verification.

Verdict: evaluate against browser-use for real workflows.

### browser-use

Repo: [browser-use/browser-use](https://github.com/browser-use/browser-use)

What it is: Python browser agent framework. The repo describes the goal as making websites accessible for AI agents.

Agent-X fit:

- fast prototypes
- web task automation
- low-friction demos

Risk:

- Browser agents can hallucinate clicks or get stuck.
- Should run behind approval, screenshots/logs, and replayable traces.

Verdict: good prototype layer; production only after evals.

### Steel Browser

Repo: [steel-dev/steel-browser](https://github.com/steel-dev/steel-browser)

What it is: open-source browser API for AI agents/apps. Search result snippets say it handles sessions, pages, and browser processes so developers avoid browser infrastructure.

Agent-X fit:

- browser session infrastructure
- remote browsers for agents
- possible replacement for building our own browser infra

Verdict: useful for scalable browser action layer.

### Hyperbrowser / HyperAgent

Repo: [hyperbrowserai/HyperAgent](https://github.com/hyperbrowserai/HyperAgent)  
MCP: [Hyperbrowser MCP Server](https://mcpservers.org/servers/hyperbrowserai/mcp)

What it is: AI browser automation and browser infrastructure; MCP server exposes scraping, structured extraction, crawling, and access to browser agents.

Agent-X fit:

- hosted browser automation
- scraping/extraction
- browser action fallback

Verdict: evaluate when browser infra becomes bottleneck.

### Computer-use agents

Repos/docs:

- [openai/openai-cua-sample-app](https://github.com/openai/openai-cua-sample-app)
- [anthropics/anthropic-quickstarts computer-use demo](https://github.com/anthropics/anthropic-quickstarts/blob/main/computer-use-demo/README.md)
- [trycua/cua](https://github.com/trycua/cua)
- [simular-ai/agent-s](https://github.com/simular-ai/agent-s)

What they are: model/computer environments where agents can control GUIs via screenshots, mouse/keyboard, or full desktops.

Agent-X fit:

- fallback when API/browser automation fails
- operating desktop apps
- testing real workflows
- "manual projection plus agent-assisted execution" inside sandbox

Risk:

- slow, brittle, hard to verify
- dangerous if it touches customer systems without policy
- needs strong run snapshots and human approval

Verdict: strategic fallback, not primary syscall path.

## Sandboxed Execution Layer

This layer matters for any mandate that runs code, browser sessions, scraping, generated scripts, or untrusted tools.

### E2B

Repo: [e2b-dev/E2B](https://github.com/e2b-dev/E2B)

What it is: open-source infrastructure for running AI-generated code in secure isolated cloud sandboxes, with JS and Python SDKs. The repo mentions self-hosting on AWS, GCP, Azure, or Linux.

Agent-X fit:

- code execution syscall
- browser/computer-use sandbox
- data extraction scripts
- evaluating generated adapters
- safe execution for mandates

Verdict: high priority.

### Daytona

Repo: [daytonaio/daytona](https://github.com/daytonaio/daytona)

What it is: secure elastic infrastructure for AI-generated code execution and agent workflows. Its README describes isolated sandboxes with kernel, filesystem, network stack, vCPU/RAM/disk, fast startup, and stateful snapshots.

Agent-X fit:

- full development/workflow sandboxes
- long-running mandate runs needing files/processes
- possible environment for worker pods

Verdict: high priority, especially if persistence/snapshots matter.

### Modal Sandboxes

Docs: [Modal coding agent sandbox example](https://modal.com/docs/examples/agent)

What it is: Modal's example shows building a coding agent with Modal Sandboxes and LangGraph.

Agent-X fit:

- code execution
- batch jobs
- agent worker infrastructure

Verdict: useful if we already like Modal's cloud model.

### Beam

Repo: [beam-cloud/beta9](https://github.com/beam-cloud/beta9)  
Site: [Beam](https://www.beam.cloud/)

What it is: open-source/runtime for serverless AI workloads, sandboxes, task queues, GPU workloads. Site says it supports sandboxes and custom model inference.

Agent-X fit:

- GPU + sandbox combined workloads
- code execution and batch jobs

Verdict: watch/evaluate.

### SWE-ReX

Repo: [SWE-agent/SWE-ReX](https://github.com/SWE-agent/SWE-ReX)

What it is: runtime interface for interacting with sandboxed shell environments across local Docker, AWS, Modal, etc.

Agent-X fit:

- if mandates need to run shell commands across interchangeable backends
- possible abstraction layer over sandboxes

Verdict: useful pattern for "sandbox adapter" interface.

## Communication Layer

### AgentMail

Site: [AgentMail](https://www.agentmail.to/)  
Docs repo page: [agentmail-docs introduction](https://github.com/agentmail-to/agentmail-docs/blob/main/fern/pages/get-started/introduction.mdx?plain=1)

What it is: API platform for giving AI agents their own inboxes to send, receive, and act on email.

Agent-X fit:

- easy early communication channel
- lead-finding mandate can produce outbound email drafts
- agent-specific inboxes for testing and internal ops

MVP recommendation:

```text
Use email first before WhatsApp.
Start with draft mode and manual send/approval.
```

Verdict: high priority for early MVP.

### Cloudflare Agentic Inbox

Repo: [cloudflare/agentic-inbox](https://github.com/cloudflare/agentic-inbox)

What it is: AI-powered email agent that can read inbox, search conversations, and draft replies, built on Cloudflare Agents/Workers AI.

Agent-X fit:

- reference architecture for email agent UX
- possible inbox surface for admin/founder workflows

Verdict: pattern source.

### Patter

Repo: [PatterAI/Patter](https://github.com/PatterAI/Patter)

What it is: open-source voice-AI SDK that gives an AI agent a phone number; supports Python/TypeScript, Twilio/Telnyx/Plivo, and handles telephony/STT/TTS/realtime voice.

Agent-X fit:

- call mandates
- phone qualification
- reminder calls
- "voice syscall" adapter

Verdict: strong open-source voice adapter candidate.

### Vapi

Repos: [VapiAI examples](https://github.com/VapiAI/examples)  
Site: [Vapi](https://vapi.ai/)

What it is: developer platform for voice AI agents; examples repo has assistant/tooling samples.

Agent-X fit:

- quick voice demos
- production voice agent infrastructure

Verdict: use if speed matters more than stack ownership.

### AgentPhone

Repo/skill: [AgentPhone-AI/skills](https://github.com/AgentPhone-AI/skills)

What it is: skill/MCP-style layer for AI agents to buy/manage phone numbers, make outbound calls, read SMS, set up webhooks, and check usage.

Agent-X fit:

- prototype phone/SMS syscalls
- learn phone-number-as-agent-identity patterns

Verdict: watch/evaluate.

### Kapso

Site/docs: [Kapso](https://kapso.com/), [Kapso docs MCP](https://docs.kapso.ai/docs/build-with-ai), [OpenClaw Kapso WhatsApp](https://github.com/Enriquefft/openclaw-kapso-whatsapp)

What it is: developer platform around WhatsApp API, messages/templates/webhooks/logs/inbox/functions, plus AI/MCP docs and OpenClaw integration examples.

Agent-X fit:

- WhatsApp sandbox/prototype
- learning WhatsApp API edge cases
- possible managed adapter if direct Meta setup is slow

Risk:

- WhatsApp tenancy/policy remains hard.
- Still need customer-owned identity and opt-in logic for production.

Verdict: useful WhatsApp adapter candidate; not MVP blocker.

## Memory / Coordination / Agent Runtime Layer

### Mem0

Repo: [mem0ai/mem0](https://github.com/mem0ai/mem0)

What it is: universal memory layer for AI agents.

Agent-X fit:

- could support worker/harness memory
- could provide personal/user memory in non-critical areas

But:

- Agent-X verified heap is different.
- Do not let generic memory replace settlement and provenance.

Verdict: useful component, not the moat.

### MCP Agent Mail

Repo: [dicklesworthstone/mcp_agent_mail](https://github.com/dicklesworthstone/mcp_agent_mail)

What it is: mail-like coordination layer for coding agents with inbox/outbox, searchable history, and file reservation leases.

Agent-X fit:

- internal multi-agent coordination
- worker-to-worker handoff patterns
- not customer-facing business memory

Verdict: useful pattern for agent coordination.

### Cloudflare Agents

Repo: [cloudflare/agents](https://github.com/cloudflare/agents)

What it is: stateful execution environments for agentic workloads on Cloudflare Durable Objects, with real-time communication, scheduling, model calls, MCP, workflows.

Agent-X fit:

- possible runtime for lightweight persistent agents
- good reference for state/lifecycle/scheduling

Verdict: pattern source; possible implementation substrate.

## MCP Registries / Tool Discovery

### Official MCP servers and registry

Sources:

- [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)
- [modelcontextprotocol/registry](https://github.com/modelcontextprotocol/registry)
- [MCP Registry about page](https://modelcontextprotocol.io/registry/about)

Why it matters:

- We need discoverable tools.
- We need metadata for tool risk, auth, tenancy, setup, and verification.
- But public MCP discovery is still messy.

### Awesome MCP Servers

Repo: [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers/blob/main/README.md)

What it is: huge community list of MCP servers.

Agent-X fit:

- discovery and inspiration
- not enough for production trust

### Docker MCP Catalog/Gateway

Repo: [docker/mcp-gateway](https://github.com/docker/mcp-gateway)  
Docs: [Docker MCP Catalog](https://docs.docker.com/ai/mcp-catalog-and-toolkit/catalog/)

What it is: Docker MCP Catalog is described as a curated collection of verified MCP servers packaged as Docker images, solving environment conflicts, setup complexity, and security concerns.

Agent-X fit:

- safer way to run MCP servers
- good idea to copy: tool servers should be packaged, isolated, and versioned

Verdict: important pattern source.

## Reddit / Community Signals

These are not authoritative, but they reveal where builders feel pain.

### Signal 1: the "agent employee stack" is forming

A Reddit post on r/AI_Agents lists primitives like AgentMail, AgentPhone, Kapso, Daytona/E2B, Browserbase/browser-use/Hyperbrowser, Firecrawl, Mem0, Composio, Exa, Vapi/ElevenLabs, and says:

> "every capability a human employee takes for granted is being rebuilt as an API."

Agent-X interpretation: this validates our syscall framing. The market is building employee-like primitives, but Agent-X still needs the employment relationship: authority, verification, settlement, trust.

Source: [r/AI_Agents thread](https://www.reddit.com/r/AI_Agents/comments/1s7xuw7/you_can_now_give_an_ai_agent_its_own_email_phone/)

### Signal 2: production reliability is the pain

Same thread has comments emphasizing error handling, latency, state management, observability, and failover. This maps directly to Agent-X kernel responsibilities.

Agent-X interpretation: "having tools" is easy; operating them reliably is the business.

### Signal 3: MCP discovery/setup is messy

A r/LocalLLaMA thread says MCP server discovery/setup feels fragmented: multiple GitHub tools, unclear docs/install steps, compatibility issues, and no quick test before integration.

Agent-X interpretation: do not blindly depend on random MCP servers. Build a verified internal syscall registry with health checks, test fixtures, and risk metadata.

Source: [r/LocalLLaMA thread](https://www.reddit.com/r/LocalLLaMA/comments/1sqif6v/are_ai_agent_tools_like_mcp_servers_too/)

### Signal 4: deploying many MCP servers in production is unclear

A r/AI_Agents post asks how to deploy 10-15+ MCP servers in production and says hosting all of them "seems crazy."

Agent-X interpretation: one more reason for a gateway/adapter layer. The harness should not be handed a pile of raw MCP servers.

Source: [r/AI_Agents thread](https://www.reddit.com/r/AI_Agents/comments/1jzsqhg/whos_using_mcps_in_their_agents/)

### Signal 5: browser automation is useful but brittle

A r/AI_Agents thread comparing Stagehand and browser-use complains about hallucinated clicks in browser-use and says Stagehand worked better for that poster's case. This is anecdotal, but useful.

Agent-X interpretation: browser/computer-use should be behind approval and verification, not trusted like an API syscall.

Source: [Stagehand vs browser-use Reddit thread](https://www.reddit.com/r/AI_Agents/comments/1slvuta/stagehand_vs_browser_use_which_one_actually_works/)

### Signal 6: tool-call batching matters

A r/mcp post argues that agents may make many MCP tool calls when one batch call would reduce round trips, context bloat, latency, and token cost.

Agent-X interpretation: design syscall adapters with batch endpoints:

```text
bad:
  search_leads()
  read_lead()
  score_lead()
  read_lead()
  score_lead()

better:
  lead_research_batch(criteria, count, evidence_schema)
```

Source: [r/mcp thread](https://www.reddit.com/r/mcp/comments/1pp8cse/ai_agents_are_making_10_tool_calls_to_your_mcp/)

## Ranked Build Plan For Agent-X

### Phase 1: Lead-finding mandate with manual projection

Build:

```text
lead_research()
read_company_site()
search_github_or_web()
score_lead()
draft_outreach()
queue_manual_action()
mark_outcome()
settle_manual_result()
```

Use:

- Agent Reach
- Firecrawl or Crawl4AI
- Exa
- GitHub CLI/MCP
- admin dashboard action queue
- email draft/manual send

Avoid:

- WhatsApp automation
- payments/refunds
- ads
- browser CUA as default

### Phase 2: Email/calendar/CRM approved syscalls

Build:

```text
send_email_with_approval()
create_gmail_draft()
check_calendar()
create_calendar_event_with_approval()
update_crm_status()
```

Use:

- Composio or Pipedream for fast connectors
- Nango for tenant auth/sync if needed
- official APIs for core channels
- AgentMail for agent-owned inbox experiments

### Phase 3: Browser fallback and sandbox

Build:

```text
browser_task_request()
browser_task_approval()
browser_task_trace()
sandbox_exec()
artifact_capture()
```

Use:

- Playwright MCP first
- Stagehand/browser-use for prototypes
- Steel/Hyperbrowser when browser infra matters
- E2B/Daytona for sandboxing

### Phase 4: Voice/phone

Build:

```text
start_call_with_approval()
answer_call()
transcribe_call()
call_summary()
call_outcome_watch()
```

Use:

- Patter if open-source ownership matters
- Vapi if speed matters
- AgentPhone for MCP/phone-number patterns
- VoxCPM for TTS experiments, not telephony itself

### Phase 5: WhatsApp and hard channels

Build:

```text
send_whatsapp_template()
send_whatsapp_within_window()
register_opt_in()
register_opt_out()
sync_template_status()
watch_reply_or_booking()
```

Use:

- direct WhatsApp Business Platform when ready
- Kapso as adapter/sandbox/reference
- strict customer-owned identity model

## What To Copy From These Tools

From Agent Reach:

- ordered backend list with fallbacks
- health checks / doctor command
- channel-specific setup notes
- "install only what you use"

From Composio/Pipedream/Activepieces/Nango/Arcade:

- managed auth
- provider adapters
- tool catalogs
- SDK-first integration
- generated or typed tool schemas

From Playwright MCP/Stagehand/browser-use:

- browser as fallback action channel
- structured snapshots
- observe/act/extract split
- traces/screenshots for verification

From E2B/Daytona/Modal/Beam:

- isolated execution
- persistent or ephemeral environments
- snapshots/artifacts
- no untrusted code on production host

From Reddit pain points:

- discovery is messy
- install is messy
- many MCP servers in production is unclear
- browser agents are brittle
- observability and failover matter
- batching matters

## What Agent-X Must Build Itself

Do not outsource:

- mandate authority
- tenant isolation
- risk classes
- trust rings
- approval policies
- syscall registry
- idempotency keys
- audit ledger
- run snapshots
- verification watches
- settlement engine
- verified heap
- manual projection queue
- outcome capture
- adapter health checks
- adapter eval fixtures

These are not boring platform tasks. They are the Agent-X moat.

## Proposed Syscall Plugin Interface

Every new syscall/tool should be installed as:

```text
SyscallPlugin {
  name: "send_email"
  category: "communication"
  maturity_level: 0 | 1 | 2 | 3
  risk_class: "external_message"
  required_ring: "L2"
  tenant_auth: "oauth" | "api_key" | "agent_owned" | "manual"
  input_schema: JSONSchema
  output_schema: JSONSchema
  adapter: function
  dry_run: function
  verify: function
  settle: function
  health_check: function
  fixtures: test cases
}
```

The harness sees:

```text
request_send_email(...)
```

The kernel owns:

```text
send_email(...)
policy(...)
adapter(...)
verify(...)
settle(...)
```

## Shortlist To Evaluate First

1. Agent Reach
2. Exa or Firecrawl
3. Crawl4AI
4. Composio
5. Nango
6. Pipedream
7. Playwright MCP
8. Stagehand
9. E2B
10. Daytona
11. AgentMail
12. Patter
13. Kapso

## Bottom Line

The market is building the agent equivalent of:

```text
eyes: web/search/social readers
hands: SaaS/API connectors
browser hands: browser/computer-use agents
safe rooms: sandboxes
voice: phone/TTS/STT platforms
memory: agent memory stores
```

Agent-X should not rebuild all of those from scratch.

Agent-X should build the layer that decides:

```text
who may use which eye/hand,
for which customer,
under which mandate,
at what trust level,
with what approval,
with what evidence,
and what gets remembered after reality responds.
```

That is the syscall layer. That is how mandates actually do things.

## Source Index

- [Agent Reach README](https://github.com/Panniantong/Agent-Reach/blob/main/docs/README_en.md)
- [Composio GitHub](https://github.com/ComposioHQ/composio)
- [Pipedream GitHub org](https://github.com/pipedreamhq)
- [Pipedream MCP docs](https://pipedream.com/docs/connect/mcp)
- [Activepieces GitHub](https://github.com/activepieces/activepieces)
- [Nango GitHub](https://github.com/nangohq/nango)
- [Arcade MCP GitHub](https://github.com/ArcadeAI/arcade-mcp)
- [Firecrawl GitHub](https://github.com/firecrawl/firecrawl)
- [Crawl4AI GitHub](https://github.com/unclecode/crawl4ai)
- [Exa MCP Server](https://github.com/exa-labs/exa-mcp-server)
- [Playwright MCP](https://github.com/microsoft/playwright-mcp)
- [Stagehand GitHub](https://github.com/browserbase/stagehand)
- [browser-use GitHub](https://github.com/browser-use/browser-use)
- [Steel Browser GitHub](https://github.com/steel-dev/steel-browser)
- [HyperAgent GitHub](https://github.com/hyperbrowserai/HyperAgent)
- [OpenAI CUA sample app](https://github.com/openai/openai-cua-sample-app)
- [Anthropic computer-use demo](https://github.com/anthropics/anthropic-quickstarts/blob/main/computer-use-demo/README.md)
- [trycua/cua](https://github.com/trycua/cua)
- [Agent S](https://github.com/simular-ai/agent-s)
- [E2B GitHub](https://github.com/e2b-dev/E2B)
- [Daytona GitHub](https://github.com/daytonaio/daytona)
- [Modal coding agent sandbox example](https://modal.com/docs/examples/agent)
- [Beam beta9 GitHub](https://github.com/beam-cloud/beta9)
- [SWE-ReX GitHub](https://github.com/SWE-agent/SWE-ReX)
- [AgentMail](https://www.agentmail.to/)
- [Cloudflare Agentic Inbox](https://github.com/cloudflare/agentic-inbox)
- [Patter GitHub](https://github.com/PatterAI/Patter)
- [Vapi examples](https://github.com/VapiAI/examples)
- [AgentPhone skills](https://github.com/AgentPhone-AI/skills)
- [Kapso](https://kapso.com/)
- [OpenClaw Kapso WhatsApp](https://github.com/Enriquefft/openclaw-kapso-whatsapp)
- [VoxCPM GitHub](https://github.com/OpenBMB/VoxCPM)
- [Mem0 GitHub](https://github.com/mem0ai/mem0)
- [MCP Agent Mail](https://github.com/dicklesworthstone/mcp_agent_mail)
- [Cloudflare Agents](https://github.com/cloudflare/agents)
- [MCP servers](https://github.com/modelcontextprotocol/servers)
- [MCP registry](https://github.com/modelcontextprotocol/registry)
- [Awesome MCP servers](https://github.com/punkpeye/awesome-mcp-servers/blob/main/README.md)
- [Docker MCP Gateway](https://github.com/docker/mcp-gateway)
- [Docker MCP Catalog docs](https://docs.docker.com/ai/mcp-catalog-and-toolkit/catalog/)
- [Reddit: agent employee stack](https://www.reddit.com/r/AI_Agents/comments/1s7xuw7/you_can_now_give_an_ai_agent_its_own_email_phone/)
- [Reddit: MCP fragmentation](https://www.reddit.com/r/LocalLLaMA/comments/1sqif6v/are_ai_agent_tools_like_mcp_servers_too/)
- [Reddit: MCP deployment question](https://www.reddit.com/r/AI_Agents/comments/1jzsqhg/whos_using_mcps_in_their_agents/)
- [Reddit: Stagehand vs browser-use](https://www.reddit.com/r/AI_Agents/comments/1slvuta/stagehand_vs_browser_use_which_one_actually_works/)
- [Reddit: MCP batching](https://www.reddit.com/r/mcp/comments/1pp8cse/ai_agents_are_making_10_tool_calls_to_your_mcp/)
