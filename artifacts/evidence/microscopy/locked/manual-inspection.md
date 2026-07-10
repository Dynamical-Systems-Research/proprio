# Locked microscopy record inspection

Inspector: Codex agent

Inspection date: 2026-07-10 UTC
Human countersign: Jarrod Barnes approved the inspection record in the build session on
2026-07-09 EDT.

The three PNGs and their corresponding NumPy arrays were opened directly from the locked
OpenFlexure capture. This was a fresh simulator process after the calibration session.

| Frame | SHA-256 | Hand inspection |
|---|---|---|
| `baseline` | `92b74c827d5d33990c58c373e87f171fb2ac06534404460f2fe4bce20a0789e5` | Nearly uniform purple field with no resolved particle boundaries; consistent with a large focus offset. |
| `underfocused` | `65bb01f47f6b6eb1e8b6c097afed6964ebfb4afb68e388451f547c9e1ed90cf9` | Particle-scale structure is visible, but edges and internal rings remain strongly diffuse; consistent with an autofocus sweep that approached but did not cover the calibrated plane. |
| `focused` | `da16b53f8a5f35019b150de9082bb881dc95bc68f94234bd5f2ae79f8fcaafb8` | Circular particle outlines, overlaps, and internal rings are sharply resolved across the field. No blank, truncated, or visibly saturated region is present. |

The raw visual state agrees with the canonical records: the 2,000-step sweep was rejected by
the calibrated-plane, FFT-focus, and Laplacian-focus checks; the 3,200-step sweep was admitted.
The locked 2,700-case verifier battery recorded zero false-valids and one false rejection among
300 valid cases. The images support the labels used by that battery and do not reveal a
hardcoded or inverted measurement state.
