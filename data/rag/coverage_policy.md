# Vehicle Damage Coverage Policy

## Policy Basis
SmartInspect handles claims against a standard **Auto Physical Damage (APD) policy**, which bundles Collision coverage and Comprehensive coverage. Coverage determination depends on the damage category detected by the vision pipeline and the cause described by the policyholder.

## Coverage by Damage Category
| Damage Category | Typical Cause | Coverage Path | Notes |
|---|---|---|---|
| `no_damage` | N/A | N/A | Informational query only; no claim opened |
| `minor_scratch` | Curb scrape, shopping cart, minor contact | Collision (if at-fault contact) or self-pay | Deductible usually exceeds repair cost — flag this to the customer before opening a claim |
| `cracked` | Windshield chip/crack, dent stress-cracking, panel cracking | Comprehensive (glass) or Collision (impact) | Glass cracks typically fall under **Comprehensive — Glass**, often with a $0 glass deductible depending on state and policy tier |
| `broken` | Shattered glass, flat/blown tire, broken headlamp/taillamp, collision impact | Collision or Comprehensive depending on cause | Requires cause-of-loss interview; a "broken" finding from the image alone does not determine fault or peril type |

## Comprehensive vs. Collision (Why the Distinction Matters)
- **Comprehensive** covers non-collision perils: glass shatter from road debris, vandalism, weather, fire, theft, animal strikes. Usually has a separate, often lower or waived deductible for glass.
- **Collision** covers impact with another vehicle or object, including single-vehicle accidents (hitting a curb, pothole, guardrail). Standard collision deductible applies (commonly $500-$1,000).
- The agent should never assume peril type from the image alone. A broken headlamp could be a collision event (hit something) or a comprehensive event (vandalism, fallen debris). Ask the customer for the cause if it isn't in the query text.

## What Is NOT Covered
- Mechanical breakdown unrelated to the reported damage event (engine, transmission failure) — route to a separate mechanical warranty product, not APD.
- Wear-and-tear tire damage (tread wear, dry rot) as opposed to a sudden flat from puncture/blowout — only sudden/accidental tire failure is claimable.
- Pre-existing damage present before the policy's effective date.
- Damage where the VIN cannot be verified against the insured vehicle on file (see VIN Verification below) — these must be escalated, not auto-approved or auto-denied.
- Cosmetic-only scratches where the customer explicitly states they do not want to file a claim (common once the deductible is explained).

## VIN Verification
Every claim requires a VIN extracted from the vehicle (via OCR from a dashboard VIN plate, door-jamb sticker, or registration document photo) to confirm:
1. The vehicle is listed on the policyholder's active policy.
2. The policy's coverage tier (liability-only vehicles have no APD coverage at all, so no claim can proceed).
3. Current deductible amounts for Collision and Comprehensive separately.

If OCR cannot extract a legible 17-character VIN, ask the customer to upload a clearer photo of the VIN plate or door-jamb sticker before proceeding. After two failed attempts, escalate to a human adjuster.
