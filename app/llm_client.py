import re
from typing import Optional

import httpx

from app import config

_NO_DAMAGE_PHRASE = re.compile(r"no[\s_-]*(?:visible\s+)?(?:physical\s+)?damage", re.IGNORECASE)
_DAMAGE_MENTION_RE = re.compile(
    r"\b(scratch(?:ed)?|dent(?:ed)?|crack(?:ed)?|shatter(?:ed)?|broken|flat tire|glass damage)\b",
    re.IGNORECASE,
)
_ESCALATION_MENTION_RE = re.compile(r"escalat|specialist|human adjuster", re.IGNORECASE)


def _format_policy(policy_info: dict) -> str:
    return (
        f"VIN {policy_info['vin']}, a {policy_info['year']} {policy_info['make']} {policy_info['model']}, "
        f"insurance last covered in {policy_info['last_covered']}."
    )


def _format_label(label_info: dict) -> str:
    parts = []
    if label_info.get("vin"):
        parts.append(f"VIN {label_info['vin']}")
    if label_info.get("year"):
        parts.append(f"year {label_info['year']}")
    return ", ".join(parts)


def _format_escalation(escalation_info: dict) -> str:
    return f"Reason: {escalation_info['trigger']}. Guidance for the customer: {escalation_info['recommended_action']}"


def _build_prompt(
    query: str,
    damage_category: Optional[str],
    label_info: Optional[dict],
    rag_chunks: Optional[list[str]],
    policy_info: Optional[dict] = None,
    escalation_info: Optional[dict] = None,
) -> str:
    context_lines = []
    if damage_category:
        context_lines.append(f"Detected damage: {damage_category}")
    if label_info:
        context_lines.append(f"Extracted label: {_format_label(label_info)}")
    if policy_info:
        context_lines.append(f"Policy lookup (authoritative, do not contradict): {_format_policy(policy_info)}")
    if escalation_info:
        context_lines.append(
            f"This case has been escalated to a specialist for review. {_format_escalation(escalation_info)}"
        )
    if rag_chunks:
        context_lines.append("Relevant knowledge base excerpts:\n" + "\n---\n".join(rag_chunks))
    context = "\n".join(context_lines)

    if not query:
        return context or "No damage or text was detected in the photo."
    return f"{context}\n\nQuestion: {query}" if context else query


def _contradicts_damage_category(answer: str, damage_category: str) -> bool:
    if damage_category != "no_damage":
        return bool(_NO_DAMAGE_PHRASE.search(answer))
    # The reverse failure: classifier says nothing's wrong, but the answer
    # describes real damage anyway (e.g. picked up from the customer's own
    # wording or off-topic RAG hits pulled in despite no grounding rewrite).
    return bool(_DAMAGE_MENTION_RE.search(answer))


def _omits_escalation(answer: str, escalation_info: Optional[dict]) -> bool:
    # An active escalation is safety-relevant -- never let the model silently
    # drop it from a customer-facing answer just because other context (a
    # damage category, RAG excerpts) dominated the generation.
    return bool(escalation_info) and not _ESCALATION_MENTION_RE.search(answer)


def _category_phrase(damage_category: str) -> str:
    if damage_category == "no_damage":
        return "no damage on your vehicle"
    return f"{damage_category.replace('_', ' ')} damage on your vehicle"


def _fallback_answer(
    damage_category: Optional[str],
    label_info: Optional[dict],
    policy_info: Optional[dict],
    escalation_info: Optional[dict],
) -> str:
    sentences = []
    if damage_category:
        sentences.append(f"We detected {_category_phrase(damage_category)}.")
    if label_info and _format_label(label_info):
        sentences.append(f"We read {_format_label(label_info)} from the photo.")
    if policy_info:
        sentences.append(f"Your policy lookup shows: {_format_policy(policy_info)}")
    if escalation_info:
        sentences.append(
            f"This case has been escalated to a specialist for review. {_format_escalation(escalation_info)}"
        )
    return " ".join(sentences)


def _select_system_prompt(has_image: bool, has_query: bool, rag_grounded: bool) -> str:
    if has_image and has_query:
        return config.SYSTEM_PROMPT_FULL
    if has_image:
        return config.SYSTEM_PROMPT_IMAGE_ONLY
    return config.SYSTEM_PROMPT_QUERY_ONLY_GROUNDED if rag_grounded else config.SYSTEM_PROMPT_QUERY_ONLY_UNGROUNDED


async def generate_answer(
    query: str,
    model: str,
    damage_category: Optional[str] = None,
    label_info: Optional[dict] = None,
    rag_chunks: Optional[list[str]] = None,
    has_image: bool = False,
    rag_grounded: bool = True,
    policy_info: Optional[dict] = None,
    escalation_info: Optional[dict] = None,
) -> str:
    has_query = bool(query)
    system_prompt = _select_system_prompt(has_image, has_query, rag_grounded)
    prompt = _build_prompt(query, damage_category, label_info, rag_chunks, policy_info, escalation_info)

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            config.OLLAMA_URL,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "options": {"temperature": config.TEMPERATURE},
                "stream": False,
            },
        )
        response.raise_for_status()
        answer = response.json().get("message", {}).get("content", "")

    if _omits_escalation(answer, escalation_info):
        return _fallback_answer(damage_category, label_info, policy_info, escalation_info)
    if damage_category and _contradicts_damage_category(answer, damage_category):
        return _fallback_answer(damage_category, label_info, policy_info, escalation_info)
    return answer
