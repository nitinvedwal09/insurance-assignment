# Escalation Rules — When to Flag for a Human Adjuster

The agent should escalate a case to a human adjuster (rather than resolving it autonomously) whenever any of the following conditions are met.

## Mandatory Escalation Triggers
1. **Unreadable or missing VIN after 2 OCR attempts.** If the customer has re-uploaded a VIN plate/door-jamb photo once already and OCR still fails to extract a legible 17-character VIN, do not guess — escalate.
2. **Safety-relevant damage.** Any `broken` classification involving Glass Shatter, or a `cracked` windshield that obstructs the driver's line of sight, must be escalated with a note recommending the customer avoid or limit driving until repaired.
3. **Conflicting evidence.** If the image classifier and the customer's text description disagree substantially (e.g., classifier says `minor_scratch` but the customer describes the vehicle as undrivable or totaled), escalate rather than resolving from the image alone.
4. **Indication of injury or an active accident scene.** If the customer's query mentions injuries, another party, police involvement, or the accident just occurred, escalate immediately — this is a claims-intake/FNOL (First Notice of Loss) situation, not a routine damage-assessment query.
5. **Coverage tier is missing or ambiguous.** If the VIN resolves to a vehicle with no Collision/Comprehensive coverage on file, or the registry lookup is incomplete, escalate rather than auto-denying.
6. **Repeat claims.** If the VIN has 2 or more prior claims on file within the policy period, escalate to check for a pattern (potential fraud flag, high-risk vehicle, or recurring issue).
7. **Explicit customer request.** If the customer asks to speak to a person, or expresses frustration/dissatisfaction with the automated response, escalate immediately.
8. **Low-confidence classification.** If the damage classifier's confidence score falls below the model's minimum reliability threshold, treat the category as uncertain and escalate rather than acting on a low-confidence label.

## Non-Escalation (Agent Can Resolve Autonomously)
- Clear `minor_scratch` cases with a valid, high-confidence VIN, no injury/accident-scene language, and the customer is just asking about deductible tradeoffs (not filing).
- `no_damage` cases where the query is purely informational (e.g., "does my policy cover glass?").
- Clear `cracked` (chip-only, non-obstructing) or `broken` (single-cause, e.g. simple tire puncture) cases with unambiguous coverage determination — the agent may auto-generate a shop referral and estimated deductible.

## Escalation Output Format
When escalating, produce a structured handoff summary containing: transaction ID, damage category and confidence, OCR-extracted VIN (or "unreadable"), the specific escalation trigger that fired, and a one-line recommended action for the human adjuster.
