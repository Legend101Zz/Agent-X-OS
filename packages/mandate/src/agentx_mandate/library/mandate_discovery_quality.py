"""Pure, deterministic mandate-discovery gates (HERMES_BUILD_PLAN §Phase 12 — mandate-discovery).

This module is the *rules* rung of mandate-discovery's verification ladder. The
playbook yields PainSignal / MandateCandidate / MoatAssessment / BuyerChannel
*proposals*; the F2 / F3 / F4 / F5 faculties emit them as JSON-shaped scratchpad
data. This module's functions are the deterministic filters that turn those
proposals into committed facts:

  - ``filter_pain_signals`` (F2 gate) — drop pain below severity/frequency bar.
  - ``cluster_pain_signals`` (F2 output) — group surviving signals into clusters.
  - ``filter_mandate_candidates`` (F3 gate) — drop input==output, non-recurring, low pain.
  - ``filter_moat_assessments`` (F4 gate) — drop saturated+no-moat (the dead-zone).
  - ``filter_buyer_channels`` (F5 gate) — drop channels with no reachable audience.
  - ``rank_portfolio`` (F6 ranking) — score surviving shortlist by pain × moat × audience.
  - ``enforce_verification_ladder`` (Rung 1) — the postcondition gate; returns the
    passed/failed conditions for the kernel's rules-verifier to consume.

Every function is pure (no I/O, no Mongo, no LLM) so the unit tests can exercise
all four deterministic gates in <1 second. The LLM faculties feed these
proposals in; the F6 builder then claims provenance-stamped facts for the
surviving portfolio.

Discipline: NO business logic lives in the playbook or in any faculty — every
gate is here, deterministic, and unit-testable. The faculties are PROPOSERS; this
module is the DISPOSER. (The mandate-pattern invariant: the LLM proposes,
deterministic code disposes.)
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# --- The deterministic thresholds (the "moat bar", the "diversity bar", etc.) ---
# These are the constitution of the mandate — they are what the user signs up to
# when they trust the discovery output. Bumping them is a one-line change here +
# a test update + a CHANGELOG note. They are NOT buried in a faculty.

# F2 pain filter: drop pain below this severity AND below this frequency.
PAIN_SEVERITY_MIN: int = 3  # 1-5 scale; <3 is "nice to have", not a real mandate
PAIN_FREQUENCY_MIN: int = 2  # 1-5 scale; <2 is "happens once a year"

# F2 cluster gate: each cluster must have at least this many distinct sources.
# A mono-source mandate is biased — the F1 sampling rule (>=4 distinct community
# sources) exists to feed this gate. A real pain cluster should be corroborated
# across >=2 distinct community sources, not one biased subreddit.
CLUSTER_MIN_DISTINCT_SOURCES: int = 2

# F3 candidate gate: drop if input==output (transformation, not process),
# not recurring, or pain_score below this bar.
MANDATE_PAIN_SCORE_MIN: float = 0.4  # 0-1 scale

# F4 moat gate: drop if saturation AND defensibility are both bad. The
# dead-zone: saturated AND no moat = no opportunity.
MOAT_SATURATION_MAX: float = 0.7  # >0.7 = "tools exist, no room"
MOAT_DEFENSIBILITY_MIN: float = 0.3  # <0.3 = "anyone can copy in a weekend"

# F5 buyer gate: drop if no channel has a non-zero audience_size_estimate.
# Zero reachable buyers = no opportunity (we'd build a mandate with no one to sell to).

# F6 portfolio gate: the shortlist must be at least 1; an empty shortlist is a
# valid outcome (the market has spoken), not a failure.
PORTFOLIO_SHORTLIST_MIN: int = 0  # 0 is valid (the doc postconditions assert >=0)

# F6 anti-portfolio: any candidate whose name matches an anti-portfolio entry
# is auto-deferred. (Tested in ``is_anti_portfolio`` in the domain pack module.)


# =============================================================================
# F2 — pain signals and clusters
# =============================================================================


def filter_pain_signals(
    pain_signals: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The F2 deterministic gate — drop pain below the severity/frequency bar.

    Each pain signal must have:
      - ``who_has_problem`` (str, non-empty)
      - ``exact_quotes`` (list of {text, source_url, author, timestamp})
      - ``workaround_used`` (str, optional)
      - ``willingness_to_pay_signal`` (str or number, optional)
      - ``segment`` (str)
      - ``severity_1to5`` (int, 1-5)
      - ``frequency_score`` (int, 1-5)

    Drops if:
      - severity_1to5 < PAIN_SEVERITY_MIN
      - frequency_score < PAIN_FREQUENCY_MIN
      - no exact_quote with a real author + URL (the "no fabrication" rule)
    """
    surviving: list[dict[str, Any]] = []
    for signal in pain_signals:
        if not isinstance(signal, dict):
            continue
        severity = signal.get("severity_1to5")
        frequency = signal.get("frequency_score")
        if not isinstance(severity, int) or severity < PAIN_SEVERITY_MIN:
            continue
        if not isinstance(frequency, int) or frequency < PAIN_FREQUENCY_MIN:
            continue
        if not _has_real_quote(signal):
            continue
        surviving.append(signal)
    return surviving


def _has_real_quote(signal: dict[str, Any]) -> bool:
    """A real quote has a URL AND an author. Empty arrays don't count."""
    quotes = signal.get("exact_quotes")
    if not isinstance(quotes, list):
        return False
    for entry in quotes:
        if not isinstance(entry, dict):
            continue
        url = entry.get("source_url")
        author = entry.get("author")
        if isinstance(url, str) and url.strip() and isinstance(author, str) and author.strip():
            return True
    return False


def cluster_pain_signals(
    pain_signals: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group surviving pain signals into clusters by topic + who_has_problem.

    This is the deterministic equivalent of an LLM "semantic similarity" pass.
    The key is ``(topic_normalised, who_normalised)``; collision = same cluster.

    Each cluster carries:
      - ``cluster_id`` (str, deterministic from the key)
      - ``topic`` (str, the surface label — e.g. "revops_too_small_for_dedicated_team")
      - ``who_has_problem`` (str)
      - ``signals`` (list of the original pain signals)
      - ``distinct_sources`` (list of unique source domains, for the diversity bar)
      - ``severity_avg`` (float, mean severity across the cluster)
      - ``frequency_avg`` (float, mean frequency across the cluster)

    The diversity bar is enforced AFTER clustering: a cluster with only one
    distinct source is dropped (``enforce_cluster_diversity``). F2's gate is the
    severity/frequency filter; F2's diversity check is here.
    """
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for signal in pain_signals:
        if not isinstance(signal, dict):
            continue
        topic = _normalise_topic(str(signal.get("topic", "")))
        who = _normalise_who(str(signal.get("who_has_problem", "")))
        if not topic or not who:
            continue
        buckets.setdefault((topic, who), []).append(signal)

    clusters: list[dict[str, Any]] = []
    for (topic, who), signals in buckets.items():
        cluster = _build_cluster(topic, who, signals)
        clusters.append(cluster)
    # Sort by severity × frequency, descending — the strongest cluster first.
    clusters.sort(key=lambda c: (c["severity_avg"] * c["frequency_avg"]), reverse=True)
    return clusters


def _normalise_topic(topic: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace. "Noisy" -> "noisy"."""
    if not topic:
        return ""
    out = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in topic.lower())
    return " ".join(out.split())


def _normalise_who(who: str) -> str:
    return _normalise_topic(who)


def _build_cluster(topic: str, who: str, signals: list[dict[str, Any]]) -> dict[str, Any]:
    severities = [int(s.get("severity_1to5", 0)) for s in signals if isinstance(s.get("severity_1to5"), int)]
    frequencies = [int(s.get("frequency_score", 0)) for s in signals if isinstance(s.get("frequency_score"), int)]
    sources: set[str] = set()
    for signal in signals:
        for quote in signal.get("exact_quotes", []):
            if isinstance(quote, dict):
                url = quote.get("source_url")
                domain = _domain_of(url) if isinstance(url, str) else ""
                if domain:
                    sources.add(domain)
    return {
        "cluster_id": f"cluster:{_slug(topic)}:{_slug(who)}",
        "topic": topic,
        "who_has_problem": who,
        "signals": signals,
        "distinct_sources": sorted(sources),
        "severity_avg": sum(severities) / len(severities) if severities else 0.0,
        "frequency_avg": sum(frequencies) / len(frequencies) if frequencies else 0.0,
    }


def _domain_of(url: str) -> str:
    """Extract the registrable domain from a URL. ``https://reddit.com/r/x`` -> ``reddit.com``.

    Best-effort: no urllib.parse needed; this just strips scheme + path. Used to
    bucket sources for the diversity bar; we only need the host part.
    """
    if not isinstance(url, str):
        return ""
    raw = url.strip()
    if not raw:
        return ""
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.split("/", 1)[0]
    if raw.startswith("www."):
        raw = raw[4:]
    return raw.lower()


def _slug(text: str) -> str:
    """A filesystem-safe slug. ``"Hello World!"`` -> ``"hello-world"``."""
    out = "".join(ch if ch.isalnum() else "-" for ch in text.lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def enforce_cluster_diversity(
    clusters: Iterable[dict[str, Any]],
    *,
    min_distinct_sources: int = CLUSTER_MIN_DISTINCT_SOURCES,
) -> list[dict[str, Any]]:
    """Drop clusters with fewer than ``min_distinct_sources`` distinct sources.

    The diversity bar: a mono-source mandate is biased. We want each cluster
    backed by 2+ distinct community sources (Reddit + HN + X + a forum, etc.).
    The hard cap (>=4 sources overall for the F1 sampling rule) is upstream;
    this is the per-cluster enforcement.

    NOTE: this gate is part of the *deterministic* own-harness path. Real
    semantic clustering of unlabelled community posts into diverse pain themes
    is an LLM job (the hermes harness); the deterministic path is an honest
    smoke test that parks when it cannot find >=3 diverse clusters rather than
    fabricating single-source ones.
    """
    surviving: list[dict[str, Any]] = []
    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        sources = cluster.get("distinct_sources", [])
        if not isinstance(sources, list):
            continue
        if len(sources) < min_distinct_sources:
            continue
        surviving.append(cluster)
    return surviving


# =============================================================================
# F3 — mandate candidates
# =============================================================================


def filter_mandate_candidates(
    candidates: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The F3 deterministic gate — turn pain clusters into mandate-shaped opportunities.

    Each candidate must have:
      - ``mandate_name`` (str, non-empty)
      - ``input_artifact`` (str, what goes IN)
      - ``output_artifact`` (str, what comes OUT)
      - ``recurring_or_oneoff`` (str in {"recurring", "oneoff"})

    Drops if:
      - input_artifact == output_artifact (transformation, not process)
      - not recurring (one-off work is a feature or consulting, not a mandate)
      - pain_score_0to1 < MANDATE_PAIN_SCORE_MIN
      - mandate_name is in the anti-portfolio
    """
    from .mandate_discovery_domain_pack import is_anti_portfolio  # local import — avoid cycle

    surviving: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        name = candidate.get("mandate_name")
        if not isinstance(name, str) or not name.strip():
            continue
        in_art = candidate.get("input_artifact")
        out_art = candidate.get("output_artifact")
        recurring = candidate.get("recurring_or_oneoff")
        pain = candidate.get("pain_score_0to1")

        if not (isinstance(in_art, str) and in_art.strip()):
            continue
        if not (isinstance(out_art, str) and out_art.strip()):
            continue
        if in_art.strip() == out_art.strip():
            continue  # transformation, not process — out of scope
        if recurring != "recurring":
            continue  # one-off = feature or consulting, not a mandate
        if not isinstance(pain, (int, float)) or pain < MANDATE_PAIN_SCORE_MIN:
            continue
        if is_anti_portfolio(name) is not None:
            continue
        surviving.append(candidate)
    return surviving


# =============================================================================
# F4 — moat (competitor stress test)
# =============================================================================


def filter_moat_assessments(
    candidates: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The F4 deterministic gate — drop saturated+no-moat (the dead-zone).

    Each candidate carries its F4 moat assessment in the same dict:
      - ``saturation_score_0to1`` (float, 0-1) — how crowded the market is
      - ``defensibility_0to1`` (float, 0-1) — how hard it is to copy
      - ``differentiation_axis`` (str) — what makes this mandate defensible
      - ``existing_solutions`` (list of {name, url, pricing, weakness})
      - ``build_cost_estimate_story_points`` (int)

    Drops if:
      - saturation > MOAT_SATURATION_MAX AND defensibility < MOAT_DEFENSIBILITY_MIN
      - that is: the market is crowded AND the moat is weak = no opportunity
    """
    surviving: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        saturation = candidate.get("saturation_score_0to1")
        defensibility = candidate.get("defensibility_0to1")
        if not isinstance(saturation, (int, float)) or not isinstance(defensibility, (int, float)):
            continue
        if saturation > MOAT_SATURATION_MAX and defensibility < MOAT_DEFENSIBILITY_MIN:
            continue
        surviving.append(candidate)
    return surviving


# =============================================================================
# F5 — buyer channels
# =============================================================================


def filter_buyer_channels(
    candidates: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The F5 deterministic gate — drop candidates with no reachable audience.

    Each candidate carries its F5 buyer manifest in the same dict:
      - ``channels`` (list of {type, name_or_url, audience_size_estimate,
        engagement_quality, entry_post_strategy, conversion_signal,
        first_100_prospect_source_query})

    Drops if:
      - channels is empty
      - no channel has audience_size_estimate > 0 (zero reachable = no opportunity)
      - no channel has first_100_prospect_source_query (the "go-to-market bar")
    """
    surviving: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        channels = candidate.get("channels")
        if not isinstance(channels, list) or not channels:
            continue
        has_reachable = False
        has_query = False
        for channel in channels:
            if not isinstance(channel, dict):
                continue
            audience = channel.get("audience_size_estimate")
            query = channel.get("first_100_prospect_source_query")
            if isinstance(audience, (int, float)) and audience > 0:
                has_reachable = True
            if isinstance(query, str) and query.strip():
                has_query = True
        if not (has_reachable and has_query):
            continue
        surviving.append(candidate)
    return surviving


# =============================================================================
# F6 — portfolio ranking + verification ladder
# =============================================================================


def rank_portfolio(
    candidates: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rank surviving candidates by pain × moat × reachable audience.

    Score = pain_score_0to1 × defensibility_0to1 × (1 - saturation_score_0to1)
            × min(1.0, log10(audience_size_estimate + 1) / 6.0)

    The audience term is bounded to 1.0 once audience_size_estimate reaches ~10^6
    (a million-person channel isn't 100x better than a 100k-person one for our
    purpose — we cap it to keep the ranking robust to noise).
    """
    import math

    scored: list[tuple[float, dict[str, Any]]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        pain = float(candidate.get("pain_score_0to1", 0.0) or 0.0)
        defensibility = float(candidate.get("defensibility_0to1", 0.0) or 0.0)
        saturation = float(candidate.get("saturation_score_0to1", 0.0) or 0.0)
        channels = candidate.get("channels", [])
        audience = 0
        if isinstance(channels, list):
            for channel in channels:
                if isinstance(channel, dict):
                    raw = channel.get("audience_size_estimate")
                    if isinstance(raw, (int, float)) and raw > audience:
                        audience = int(raw)
        audience_factor = min(1.0, math.log10(audience + 1) / 6.0) if audience > 0 else 0.0
        score = pain * defensibility * (1.0 - saturation) * audience_factor
        candidate_with_score = dict(candidate)
        candidate_with_score["portfolio_score"] = score
        scored.append((score, candidate_with_score))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [candidate for _, candidate in scored]


def enforce_verification_ladder(
    *,
    pain_cluster_count: int,
    mandate_candidate_count: int,
    moat_pass_count: int,
    buyer_mapped_count: int,
    shortlist_count: int,
    portfolio_committed: bool,
) -> dict[str, bool]:
    """Rung 1 — the rules rung of the verification ladder.

    Returns ``{postcondition_id: passed}`` for the five charter postconditions.
    The kernel's ``RulesVerifier`` consumes this map; the playbook claims
    provenance-stamped facts whose predicates match these IDs.

    Invariant: ``pain_cluster_count`` MUST be computed against clusters that
    already passed the diversity gate (this is the caller's job). Similarly
    ``moat_pass_count`` is after the F4 gate, ``buyer_mapped_count`` is after
    the F5 gate.
    """
    return {
        "pain_clusters_at_least_three": pain_cluster_count >= 3,
        "mandate_candidates_at_least_one": mandate_candidate_count >= 1,
        "moat_pass_count_at_least_one": moat_pass_count >= 1,
        "buyer_source_manifest_present": buyer_mapped_count == shortlist_count and shortlist_count > 0,
        "mandate_portfolio_committed": bool(portfolio_committed),
    }


def build_mandate_portfolio(
    *,
    shortlist: list[dict[str, Any]],
    deferred: list[dict[str, Any]],
    anti_portfolio: list[dict[str, Any]],
    evidence_pack_url: str,
    run_id: str,
    segment: str,
    created_at_iso: str,
) -> dict[str, Any]:
    """The single atomic fact F6 commits to the heap.

    Returns a typed dict the playbook's ``Claim`` action will use to build a
    provenance-stamped ``Fact`` with predicate ``mandate_portfolio``. The
    structure is the platform's interface contract — ``service_ports=mandate_opportunities``
    is what consumes it.

    Schema:
      - ``shortlist``: ranked candidates (each with mandate_spec, build_spec, gtm_motion,
        buyer_source_manifest, evidence_pack_url, first_validation_experiment)
      - ``deferred``: candidates that didn't make the shortlist with reasons
      - ``anti_portfolio``: pains that looked interesting but failed a gate
        (so we don't re-explore)
      - ``evidence_pack_url``: a single URL where the full evidence pack lives
      - ``provenance``: run_id + segment + created_at
    """
    return {
        "shortlist": shortlist,
        "deferred": deferred,
        "anti_portfolio": anti_portfolio,
        "evidence_pack_url": evidence_pack_url,
        "provenance": {
            "run_id": run_id,
            "segment": segment,
            "created_at": created_at_iso,
        },
    }


__all__ = [
    # constants
    "PAIN_SEVERITY_MIN",
    "PAIN_FREQUENCY_MIN",
    "CLUSTER_MIN_DISTINCT_SOURCES",
    "MANDATE_PAIN_SCORE_MIN",
    "MOAT_SATURATION_MAX",
    "MOAT_DEFENSIBILITY_MIN",
    "PORTFOLIO_SHORTLIST_MIN",
    # F2
    "filter_pain_signals",
    "cluster_pain_signals",
    "enforce_cluster_diversity",
    # F3
    "filter_mandate_candidates",
    # F4
    "filter_moat_assessments",
    # F5
    "filter_buyer_channels",
    # F6
    "rank_portfolio",
    "enforce_verification_ladder",
    "build_mandate_portfolio",
]
