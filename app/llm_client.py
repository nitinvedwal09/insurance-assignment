import re
from typing import Optional

import httpx

from app import config

# Small local models sometimes ignore the "Detected damage: X" context line and
# fall back to a generic "no visible damage" phrase from their training data.
# Catch that specific contradiction deterministically rather than trusting the
# model to always follow the prompt's instruction not to do this.
_NO_DAMAGE_PHRASE = re.compile(r"no[\s_-]*(?:visible\s+)?(?:physical\s+)?damage", re.IGNORECASE)


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
        # image-only scenario: no question was asked, just describe what was found
        return context or "No damage or text was detected in the photo."
    return f"{context}\n\nQuestion: {query}" if context else query


def _contradicts_damage_category(answer: str, damage_category: str) -> bool:
    return damage_category != "no_damage" and bool(_NO_DAMAGE_PHRASE.search(answer))


def _fallback_answer(
    damage_category: str,
    label_info: Optional[dict],
    policy_info: Optional[dict],
    escalation_info: Optional[dict],
) -> str:
    sentences = [f"We detected {damage_category.replace('_', ' ')} damage on your vehicle."]
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

    if damage_category and _contradicts_damage_category(answer, damage_category):
        return _fallback_answer(damage_category, label_info, policy_info, escalation_info)
    return answer
