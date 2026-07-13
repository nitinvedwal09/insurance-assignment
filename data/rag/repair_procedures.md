# Repair Procedures by Damage Category

This document defines the recommended next step for each damage category returned by `DamageClassifier`, and notes where the underlying raw model label (Crack, Scratch, Tire Flat, Dent, Glass Shatter, Lamp Broken) changes the handling even after collapsing into the 4-category schema.

## no_damage
No repair action needed. If the customer submitted a photo but the classifier returned `no_damage`, ask a clarifying question — the customer's text query may describe a problem not visible in a static photo (a noise, a warning light, a functional issue like a door not sealing).

## minor_scratch (raw label: Scratch)
Cosmetic paint/clear-coat scratches, typically not affecting drivability.

**Steps:**
1. Determine scratch depth from the customer's description: surface-only (clear coat) scratches can often be buffed out; scratches down to primer or metal require body shop paint work.
2. Compare estimated repair cost against the policy's Collision deductible — for most minor scratches, self-pay is cheaper than filing a claim and it does not go on the customer's claims history.
3. Recommend a certified body shop for a free estimate before deciding whether to file.
4. Do not open a formal claim automatically; present the deductible tradeoff and let the customer decide.

## cracked (raw labels: Crack, Dent)
Covers surface cracking (typically windshield/glass or panel stress cracks) and dents which are mapped into this category.

**Steps:**
1. **If windshield/glass crack:** check policy for glass coverage under Comprehensive — many policies cover a chip repair at no cost, and a full replacement if the crack exceeds a certain length or is within the driver's direct line of sight (a safety/legal driving concern in most states).
2. **If body panel dent:** ask whether paint is also cracked/chipped at the dent site (affects whether just Paintless Dent Repair (PDR) suffices, or full bodywork + paint is needed).
3. Route to Collision coverage if caused by impact (door ding, hail, collision); route to Comprehensive if hail or falling-object caused.
4. Windshield cracks that obstruct the driver's field of view should be flagged as a **safety escalation** — recommend the customer avoid driving until repaired.

## broken (raw labels: Tire Flat, Glass Shatter, Lamp Broken)
The most urgent category; always verify VIN and coverage before authorizing repair.

**Tire Flat:**
1. Ask whether the cause was a puncture/blowout (sudden, generally coverable) vs. wear-related (not coverable).
2. If drivable to a shop, provide nearest approved tire shop; if not drivable, offer roadside assistance/towing dispatch as a mock tool call.
3. Confirm spare tire availability with the customer if immediate mobility is needed.

**Glass Shatter:**
1. Always a safety escalation — advise the customer not to drive with severely compromised visibility or an unsecured window opening.
2. Route to Comprehensive — Glass coverage; confirm VIN and glass coverage tier before authorizing replacement.
3. If caused by a collision (not just glass failure), also check Collision coverage for surrounding body damage.

**Lamp Broken (headlight/taillight):**
1. Confirm whether it's the housing/lens (covered as parts damage) vs. only the bulb (a wear item, typically not covered).
2. Flag as a safety/legal item if the vehicle is not roadworthy at night without the lamp — recommend prompt repair.
3. Route to Collision if caused by impact, Comprehensive if vandalism or falling debris.
