# Part-Specific Notes by Raw Model Label

The vision model's six native labels collapse into the four claim categories used elsewhere in this knowledge base, but each raw label carries part-specific nuance worth surfacing at retrieval time.

## Crack → `cracked`
Most often windshield/glass or bumper/panel stress cracking. Windshield crack length and position relative to the driver's sightline determine whether it's a simple resin chip repair or a full replacement, and whether it's a safety escalation (see `escalation_rules.md`).

## Scratch → `minor_scratch`
Paint/clear-coat only in the vast majority of cases. No safety implication. Primary decision point is self-pay vs. filing, based on deductible comparison.

## Tire Flat → `broken`
Treated as a wear item unless sudden puncture/blowout is confirmed. Mobility is the immediate concern — check drivability before discussing coverage. Roadside assistance dispatch may be the first tool call, before any coverage determination.

## Dent → `cracked` (mapped)
Body panel dents. Severity ranges from cosmetic (Paintless Dent Repair candidate) to structural (frame/panel replacement) depending on depth and whether paint is compromised at the dent site. Hail-caused dents are common multi-panel claims — ask if more than one panel is affected.

## Glass Shatter → `broken`
Always a safety escalation. Full pane replacement is standard; partial "repair" is not typically offered for shattered (as opposed to cracked) glass.

## Lamp Broken → `broken`
Headlight/taillight housing or lens damage. Distinguish housing/lens (parts damage, generally covered) from bulb-only failure (wear item, generally not covered). Nighttime drivability and local vehicle-equipment law may make prompt repair a safety/legal recommendation even when coverage is in question.
