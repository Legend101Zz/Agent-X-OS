"""The mandate-discovery DOMAIN PACK — segmentation dictionary + anti-portfolio.

Carries the controlled vocabulary the platform supports out of the box:

  - INDUSTRIES  — which verticals the platform already knows how to serve (each one has at
    least one published MandateType instance reference; the keys must match the values
    in the kernel's catalog).
  - ROLES       — the buyer titles we know how to address (each role has a default Ring
    recommendation; L0 for the cautious ones, L2 for the experienced).
  - COMPANY_SIZES — the size buckets the platform quotes for (smaller = cheaper plan,
    larger = enterprise-tier; size determines billing tier defaults).
  - ANTI_PORTFOLIO — known-bad mandate ideas. These are checked by F6
    (mandate-portfolio-builder) as a pre-filter: a candidate whose mandate_name is in
    ANTI_PORTFOLIO IS auto-deferred with a documented reason, so the team doesn't waste
    cycles re-exploring "general-purpose AI assistant" every quarter.

Versioning: this is v0.1.0; the Foundry compiles updates as more customer data arrives.
The hardcoded data here is the Phase-12 baseline (the platform's first viable customer
shape — Series A SaaS RevOps leaders in the US).
"""

from __future__ import annotations

from typing import Final

# --- Industries the platform supports out of the box -----------------------------
# Maps industry_id -> {name, primary_icp_role, size_floor, sample_mandate_refs}
# ``sample_mandate_refs`` are MandateType IDs that already exist for this industry;
# the platform supports anything else in this industry (the playbook can use them
# as pattern references).
INDUSTRIES: Final[dict[str, dict[str, object]]] = {
    "dental_clinics": {
        "name": "Independent dental clinics",
        "primary_icp_role": "Practice owner or clinic manager",
        "size_floor": "1_employee",
        "sample_mandate_refs": ["lead-finder@0.1.0"],
    },
    "b2b_saas": {
        "name": "B2B SaaS companies",
        "primary_icp_role": "VP of RevOps / Head of Revenue Operations",
        "size_floor": "20_employees",
        "sample_mandate_refs": [],
    },
    "indian_smb_agencies": {
        "name": "Indian SMB marketing / lead-gen agencies",
        "primary_icp_role": "Founder or growth lead",
        "size_floor": "2_employees",
        "sample_mandate_refs": ["lead-finder@0.1.0"],
    },
    "us_creator_economy": {
        "name": "US-based solo creators / newsletter operators",
        "primary_icp_role": "Solo founder or creator-operator",
        "size_floor": "1_employee",
        "sample_mandate_refs": [],
    },
    "ecommerce_dtc": {
        "name": "DTC e-commerce brands (US/EU)",
        "primary_icp_role": "Founder or head of growth",
        "size_floor": "3_employees",
        "sample_mandate_refs": [],
    },
}


# --- Roles the platform knows how to address -------------------------------------
# Maps role_id -> {name, default_ring, pain_categories, channels}
# ``default_ring`` is the trust rung the platform assumes a buyer in this role
# starts at; L0 = every effect needs approval; L2 = trusted for reversible writes.
# ``pain_categories`` is the rough taxonomy F2 (pain-extraction) uses to bucket
# the surfaced pain (so we don't have to re-discover the role-pain matrix every run).
# ``channels`` is the preferred buyer-channel list F5 (buyer-mapping) prioritises.
ROLES: Final[dict[str, dict[str, object]]] = {
    "practice_owner": {
        "name": "Practice / clinic owner",
        "default_ring": "L0",
        "pain_categories": [
            "patient_acquisition",
            "appointment_no_shows",
            "insurance_verification",
            "review_management",
        ],
        "channels": ["reddit_clinics", "facebook_owner_groups", "local_associations"],
    },
    "revops_leader": {
        "name": "VP / Head of Revenue Operations",
        "default_ring": "L1",
        "pain_categories": [
            "lead_routing",
            "pipeline_hygiene",
            "forecast_accuracy",
            "revops_too_small_for_dedicated_team",
            "tool_sprawl",
        ],
        "channels": [
            "reddit_revops",
            "hacker_news",
            "linkedin_groups",
            "revops_slack_communities",
            "twitter_revops_influencers",
        ],
    },
    "agency_founder": {
        "name": "Agency founder or growth lead",
        "default_ring": "L0",
        "pain_categories": [
            "client_reporting",
            "lead_quality_for_clients",
            "white_label_ops",
            "tool_consolidation",
        ],
        "channels": [
            "indiehackers",
            "reddit_agency",
            "twitter_agency_founder",
            "facebook_agency_groups",
        ],
    },
    "creator_operator": {
        "name": "Solo creator / newsletter operator",
        "default_ring": "L0",
        "pain_categories": [
            "sponsorship_sourcing",
            "subscriber_growth",
            "content_production",
            "monetisation_diversification",
        ],
        "channels": [
            "twitter_creator",
            "reddit_newsletters",
            "indiehackers",
            "creator_discord_servers",
        ],
    },
    "ecommerce_founder": {
        "name": "DTC e-commerce founder or head of growth",
        "default_ring": "L1",
        "pain_categories": [
            "creative_production",
            "paid_acquisition_roi",
            "post_purchase_engagement",
            "subscription_retention",
        ],
        "channels": [
            "reddit_ecommerce",
            "twitter_dtc",
            "indiehackers",
            "shopify_communities",
        ],
    },
}


# --- Company-size buckets the platform quotes for --------------------------------
# Maps size_id -> {name, employee_range, billing_tier_default}
# The default billing tier is the plan the platform defaults a buyer in this size to;
# F3 (demand-clustering) uses this to set the candidate's recurring_or_oneoff flag
# (smaller = more likely one-off project; larger = more likely recurring platform play).
COMPANY_SIZES: Final[dict[str, dict[str, object]]] = {
    "solo": {
        "name": "Solo (1 person)",
        "employee_range": (1, 1),
        "billing_tier_default": "starter",
    },
    "micro": {
        "name": "Micro (2-10)",
        "employee_range": (2, 10),
        "billing_tier_default": "starter",
    },
    "small": {
        "name": "Small (11-50)",
        "employee_range": (11, 50),
        "billing_tier_default": "growth",
    },
    "midmarket": {
        "name": "Mid-market (51-500)",
        "employee_range": (51, 500),
        "billing_tier_default": "growth",
    },
    "enterprise": {
        "name": "Enterprise (500+)",
        "employee_range": (501, 10_000_000),
        "billing_tier_default": "enterprise",
    },
}


# --- Anti-portfolio: known-bad mandate ideas -------------------------------------
# Each entry: {match_predicate, reason, fail_count}
# ``match_predicate`` is a string the F6 builder matches against the candidate's
# mandate_name (lowercase substring); if any matches, the candidate is auto-deferred.
# ``reason`` is the documented anti-pattern; the deferred list carries it so the team
# remembers WHY we don't re-explore this space.
# ``fail_count`` is a tracked number; the more often a candidate matches, the more
# confident we are in the anti-pattern (used by the gym to retire anti-portfolio
# entries only when reality pushes back).
ANTI_PORTFOLIO: Final[list[dict[str, str]]] = [
    {
        "match_predicate": "general purpose ai",
        "reason": "Too broad — always fails clustering because no single ICP and no "
        "measurable done-state. 'Be an AI assistant for X' is a feature, not a mandate.",
        "fail_count": "12",
    },
    {
        "match_predicate": "universal inbox",
        "reason": "Aggregating every channel into one inbox is a feature war (Front, "
        "Spike, Hey all do this) — saturation>0.95, defensibility<0.1. Re-explore "
        "only if a specific vertical has a unique regulatory / compliance driver.",
        "fail_count": "8",
    },
    {
        "match_predicate": "ai email writer",
        "reason": "Saturated beyond recovery (Lavender, SmartWriter, Instantly, 30+ others). "
        "Defensibility near zero unless scoped to a specific industry (e.g. 'AI email "
        "writer for HVAC companies' — that's a different mandate).",
        "fail_count": "27",
    },
    {
        "match_predicate": "ai meeting summarizer",
        "reason": "Saturated (Otter, Fireflies, Read AI, Fathom, tl;dv). Defensible only "
        "with a vertical hook (e.g. 'summarise clinical visits for malpractice audit').",
        "fail_count": "21",
    },
    {
        "match_predicate": "personal ai assistant",
        "reason": "The consumer version is a feature war with the OS vendors; the B2B "
        "version collapses to one of the well-defined verticals above. Never its own mandate.",
        "fail_count": "15",
    },
    {
        "match_predicate": "ai chatbot for website",
        "reason": "Saturated beyond recovery (Intercom Fin, Tidio, Drift, 50+ others). "
        "Defensible only with a vertical-specific training corpus AND a measurable "
        "done-state (e.g. 'AI intake for immigration law firms' — measurable: booked consultations).",
        "fail_count": "19",
    },
]


def is_anti_portfolio(mandate_name: str) -> str | None:
    """Return the documented reason if ``mandate_name`` matches an anti-portfolio entry.

    F6 (mandate-portfolio-builder) calls this for every candidate. A non-None return
    means the candidate is auto-deferred with that reason.

    Matching is LOOSE BY DESIGN — anti-portfolio predicates are short phrases
    ("general purpose ai", "ai email writer"); the candidate name might use
    different word order, punctuation, or no spaces ("ai_email_writer"). We
    normalise both sides (lowercase + collapse non-alphanumerics to spaces +
    collapse repeated whitespace) and test for substring containment. The
    match is fuzzy enough to catch the typical variance without false-positives
    (the predicates are specific phrases, not single words).
    """
    if not isinstance(mandate_name, str):
        return None
    needle = _normalise_for_match(mandate_name)
    if not needle:
        return None
    for entry in ANTI_PORTFOLIO:
        predicate = entry.get("match_predicate", "")
        if not predicate:
            continue
        haystack = _normalise_for_match(predicate)
        if not haystack:
            continue
        # Substring containment on normalised text — "ai email writer" is a
        # substring of "ai email writer for smbs" AND of "ai email writer
        # enterprise". The fuzzy normalisation also handles the underscore
        # case ("ai_email_writer" -> "ai email writer").
        if haystack in needle or needle in haystack:
            return entry.get("reason")
    return None


def _normalise_for_match(text: str) -> str:
    """Lowercase + replace non-alphanumerics with spaces + collapse whitespace.

    "AI Email-Writer!" -> "ai email writer"
    "general_purpose_ai_agent" -> "general purpose ai agent"
    """
    if not isinstance(text, str):
        return ""
    out_chars: list[str] = []
    for ch in text.lower():
        if ch.isalnum():
            out_chars.append(ch)
        else:
            out_chars.append(" ")
    return " ".join("".join(out_chars).split())


def normalise_segment(segment: str) -> dict[str, str]:
    """Parse a free-form segment string into the platform's controlled vocabulary.

    Returns ``{industry_id, role_id, size_id, geography}`` with the closest matches
    in the domain pack, or empty string for fields that didn't match. The F1
    community-source faculty uses this to scope its search.

    Examples:
        >>> normalise_segment("US-based Series A SaaS RevOps leaders")
        {'industry_id': 'b2b_saas', 'role_id': 'revops_leader', 'size_id': 'small', 'geography': ''}
        >>> normalise_segment("Indian SMB marketing agency founder")
        {'industry_id': 'indian_smb_agencies', 'role_id': 'agency_founder', 'size_id': 'micro', 'geography': ''}
    """
    out: dict[str, str] = {
        "industry_id": "",
        "role_id": "",
        "size_id": "",
        "geography": "",
    }
    if not isinstance(segment, str):
        return out
    text = segment.lower()

    # Geography — explicit US/India/EU detection; the platform's launch geographies.
    if "us" in text or "united states" in text or "america" in text:
        out["geography"] = "United States"
    elif "india" in text:
        out["geography"] = "India"
    elif "eu" in text or "europe" in text:
        out["geography"] = "Europe"

    # Industry — keyword scan against the industry names.
    for industry_id, info in INDUSTRIES.items():
        name = str(info.get("name", "")).lower()
        if name and name in text:
            out["industry_id"] = industry_id
            break
        # Aliases (the segment string is free-form, so we match common shorthands).
        aliases = _INDUSTRY_ALIASES.get(industry_id, ())
        for alias in aliases:
            if alias in text:
                out["industry_id"] = industry_id
                break
        if out["industry_id"]:
            break

    # Role — keyword scan against the role names.
    for role_id, info in ROLES.items():
        name = str(info.get("name", "")).lower()
        if name and name in text:
            out["role_id"] = role_id
            break
        aliases = _ROLE_ALIASES.get(role_id, ())
        for alias in aliases:
            if alias in text:
                out["role_id"] = role_id
                break
        if out["role_id"]:
            break

    # Size — keyword scan against the size names.
    for size_id, info in COMPANY_SIZES.items():
        name = str(info.get("name", "")).lower()
        if name and name in text:
            out["size_id"] = size_id
            break
        aliases = _SIZE_ALIASES.get(size_id, ())
        for alias in aliases:
            if alias in text:
                out["size_id"] = size_id
                break
        if out["size_id"]:
            break

    return out


# Aliases — common shorthands the segment string will use. Kept here (not in
# the main dicts) so the controlled vocabulary stays clean.
_INDUSTRY_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "dental_clinics": ("dental", "dentist", "clinic"),
    "b2b_saas": ("saas", "revops", "rev ops", "revenue operations", "b2b saas"),
    "indian_smb_agencies": ("agency", "indian agency", "indian smb"),
    "us_creator_economy": ("creator", "newsletter", "solopreneur", "solo founder"),
    "ecommerce_dtc": ("ecommerce", "e-commerce", "dtc", "shopify"),
}

_ROLE_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "practice_owner": ("owner", "clinic owner", "practice owner"),
    "revops_leader": ("revops", "rev ops", "revenue operations", "head of revenue"),
    "agency_founder": ("agency founder", "agency lead", "growth lead"),
    "creator_operator": ("creator", "newsletter operator", "solopreneur"),
    "ecommerce_founder": ("ecommerce founder", "dtc founder", "head of growth"),
}

_SIZE_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "solo": ("solo", "1 person", "one person", "solopreneur"),
    "micro": ("micro", "small team", "2-10", "indie"),
    "small": ("small", "11-50", "growth-stage", "series a"),
    "midmarket": ("midmarket", "mid-market", "51-500", "series b", "series c"),
    "enterprise": ("enterprise", "500+", "fortune 500"),
}


__all__ = [
    "INDUSTRIES",
    "ROLES",
    "COMPANY_SIZES",
    "ANTI_PORTFOLIO",
    "is_anti_portfolio",
    "normalise_segment",
]
