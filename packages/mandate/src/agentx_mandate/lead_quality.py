"""Pure, deterministic lead enrichment and actionability rules."""

from __future__ import annotations

import re
from typing import cast
from urllib.parse import urljoin, urlparse

from agentx_contracts.jsontypes import JsonObject, JsonValue

_BLOCKED_HOSTS = (
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "facebook.com",
    "linkedin.com",
    "reddit.com",
    "medium.com",
    "substack.com",
    "wikipedia.org",
    "practo.com",
    "zocdoc.com",
    "justdial.com",
    "eka.care",
)
_CONTENT_TITLE_MARKERS = (
    "how to ",
    "best ",
    "top ",
    "guide",
    "list of",
    "places to",
    "youtube",
    "podcast",
)
_GENERIC_TITLE_PARTS = (
    "contact",
    "contact us",
    "about",
    "about us",
    "book appointment",
    "book an appointment",
    "appointment booking",
    "schedule consultation",
    "home",
)
_SIGNAL_MARKERS = (
    "accepting new",
    "teleconsulting",
    "appointment setting",
    "grow your pipeline",
    "sales pipeline",
    "multiple locations",
    "now hiring",
    "growing our team",
    "book an appointment",
    "book appointment",
    "appointment booking",
    "schedule a consultation",
    "schedule consultation",
    "request an appointment",
    "online booking",
    "consult online",
    "book a call",
    "schedule a call",
    "get started",
    "serving",
    "lead generation",
)
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_DOCTOR_RE = re.compile(r"\bDr\.?\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})")
_PERSON_ROLE_RE = re.compile(
    r"\b([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})\s*[,|—-]\s*"
    r"(Founder|Owner|CEO|Managing Director|Practice Manager|Clinic Manager)\b",
    re.IGNORECASE,
)
_CTA_LABEL_RE = re.compile(
    r"\b(contact(?: us)?|book(?: a call| an appointment)?|appointment|schedule|"
    r"get started|talk to(?: sales)?)\b",
    re.IGNORECASE,
)


def is_candidate_url(url: str, title: str = "") -> bool:
    """Return whether a search result is plausible as an official prospect page."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = parsed.netloc.lower().removeprefix("www.")
    if any(host == blocked or host.endswith(f".{blocked}") for blocked in _BLOCKED_HOSTS):
        return False
    normalized_title = title.strip().lower()
    return not any(marker in normalized_title for marker in _CONTENT_TITLE_MARKERS)


def enrich_lead(lead: object, page: object, target: JsonObject) -> JsonObject:
    """Merge one page read into a structured lead and fail closed when evidence is incomplete."""

    lead_map = lead if isinstance(lead, dict) else {}
    page_map = page if isinstance(page, dict) else {}
    lead_id = _text(lead_map.get("id"))
    source_url = _text(page_map.get("url")) or _text(lead_map.get("url"))
    title = _text(page_map.get("title")) or _text(lead_map.get("company")) or _text(lead_map.get("name"))
    markdown = _text(page_map.get("markdown"))
    company = _company_name(title)
    contact_name = _contact_name(markdown)
    contact_role = _contact_role(markdown, target)
    contact_url = _contact_url(markdown, source_url)
    signal = _buying_signal(markdown)
    evidence = _string_list(lead_map.get("evidence"))
    evidence.extend(_string_list(page_map.get("evidence")))
    if signal and signal not in evidence:
        evidence.append(signal)
    if source_url and source_url not in evidence:
        evidence.append(source_url)

    enriched: JsonObject = {
        **_json_object(lead_map),
        "id": lead_id,
        "company": company,
        "url": source_url,
        "contact_name": contact_name,
        "contact_role": contact_role,
        "contact_url": contact_url,
        "buying_signal": signal,
        "buying_signal_evidence": signal,
        "evidence": [entry for entry in evidence],
    }
    enriched["actionable"] = is_actionable_lead(enriched)
    return enriched


def is_actionable_lead(lead: object) -> bool:
    """Require an organization, role/person, reachable path, and cited buying signal."""

    if not isinstance(lead, dict):
        return False
    company = _text(lead.get("company"))
    url = _text(lead.get("url"))
    contact_name = _text(lead.get("contact_name"))
    contact_role = _text(lead.get("contact_role"))
    contact_url = _text(lead.get("contact_url"))
    signal = _text(lead.get("buying_signal"))
    signal_evidence = _text(lead.get("buying_signal_evidence"))
    synthetic = bool(lead.get("origin") == "synthetic")
    reachable = is_candidate_url(contact_url or url, company) or (
        synthetic and (contact_url.startswith("sim://") or url.startswith("sim://"))
    )
    return bool(
        company
        and (contact_name or contact_role)
        and reachable
        and signal
        and signal_evidence
        and signal_evidence == signal
        and signal in _string_list(lead.get("evidence"))
    )


def score_lead(lead: object) -> tuple[float, str]:
    """Score the four actionability dimensions; non-actionable candidates score zero."""

    if not is_actionable_lead(lead) or not isinstance(lead, dict):
        return 0.0, "rejected: missing actionable prospect evidence"
    dimensions = {
        "organization": bool(_text(lead.get("company")) and _text(lead.get("url"))),
        "decision_maker": bool(_text(lead.get("contact_name")) or _text(lead.get("contact_role"))),
        "contact_path": bool(_text(lead.get("contact_url"))),
        "buying_signal": bool(_text(lead.get("buying_signal_evidence"))),
    }
    score = sum(1.0 for present in dimensions.values() if present) / len(dimensions)
    return score, "actionable: " + ", ".join(name for name, present in dimensions.items() if present)


def _company_name(title: str) -> str:
    parts = [part.strip() for part in re.split(r"\s+[|—-]\s+|:", title) if part.strip()]
    for part in parts:
        if part.lower() not in _GENERIC_TITLE_PARTS and not any(
            marker in part.lower() for marker in _CONTENT_TITLE_MARKERS
        ):
            return part
    return title.strip()


def _contact_name(markdown: str) -> str:
    doctor = _DOCTOR_RE.search(markdown)
    if doctor is not None:
        return f"Dr. {doctor.group(1)}"
    person = _PERSON_ROLE_RE.search(markdown)
    return person.group(1) if person is not None else ""


def _contact_role(markdown: str, target: JsonObject) -> str:
    person = _PERSON_ROLE_RE.search(markdown)
    if person is not None:
        return person.group(2)
    icp = _text(target.get("icp")).lower()
    if any(token in icp for token in ("dental", "clinic", "doctor", "healthcare")):
        return "Practice owner or clinic manager"
    if any(token in icp for token in ("agency", "founder", "smb", "operator")):
        return "Founder or growth lead"
    return "Business owner"


def _contact_url(markdown: str, base_url: str) -> str:
    for label, href in _LINK_RE.findall(markdown):
        label_text = label.lower()
        parsed = urlparse(urljoin(base_url, href.strip()))
        path = parsed.path.lower()
        href_text = href.lower()
        label_match = len(label_text) <= 100 and _CTA_LABEL_RE.search(label_text) is not None
        path_match = any(
            token in path
            for token in ("/contact", "/book", "/appointment", "/schedule", "/consultation", "/demo")
        )
        direct_match = (
            href_text.startswith(("mailto:", "tel:"))
            or "wa.me/" in href_text
            or "whatsapp.com/" in href_text
        )
        if label_match or path_match or direct_match:
            return cast(str, urljoin(base_url, href.strip()))
    if any(marker in markdown.lower() for marker in _SIGNAL_MARKERS):
        return base_url
    return ""


def _buying_signal(markdown: str) -> str:
    candidates: list[tuple[int, str]] = []
    for raw_line in markdown.splitlines():
        line = re.sub(r"\s+", " ", raw_line.strip(" #*>-\t"))
        if not line or len(line) > 300 or line.count("](") > 2:
            continue
        matched = [index for index, marker in enumerate(_SIGNAL_MARKERS) if marker in line.lower()]
        if matched:
            candidates.append((min(matched), line))
    if not candidates:
        return ""
    best_priority = min(priority for priority, _line in candidates)
    return max((line for priority, line in candidates if priority == best_priority), key=len)


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _json_object(value: dict[object, object]) -> JsonObject:
    result: JsonObject = {}
    for key, item in value.items():
        if isinstance(key, str) and _is_json_value(item):
            result[key] = cast(JsonValue, item)
    return result


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, str | bool | int | float):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False
