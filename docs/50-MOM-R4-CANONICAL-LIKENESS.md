# Mom R4 — canonical likeness study

## User direction and visual hypothesis

The user supports the R2 direction but explicitly requests more likeness, not
merely a technically functioning rig. R4 is a targeted form study, not a reset.
Canonical public `studio/characters/mom/master/face.png` remains the identity
reference; private photos are neither read nor published.

Observed differences in the pupil-aligned R3 review: the mouth reads lower and
narrower than the portrait, the lower jaw reads squarer, and the nasal tip needs
rounder side volume. These are **visual judgments**, not calibrated 3D
measurements or a numerical likeness score. Expression, camera and material
remain confounders. Hair/framing also remain a large unresolved identity cue.

## Authored change

- Raise the lip complex 3–3.5 mm, corners 4 mm; widen corners 2.5 mm per side.
  Shorten the visual philtrum rather than simply adding lip relief. Give lower
  lip 1 mm more forward volume.
- Round nasal tip shoulders by 1.2 mm per side and raise tip 1.5 mm; alae and
  nostril supports follow by smaller offsets. Do not enlarge the entire nose.
- Taper jaw angles 2.5 mm and jaw/chin transitions 1.5 mm per side; retain chin
  position and rounded upper cheeks.
- Keep all authored eye/canthus/lid/brow targets and brow centerline unchanged.
  The cage has continuous support, so nearby surface movement is possible;
  unchanged control targets do not imply every nearby vertex is identical.

`studio/authoring/mom-head-form-r4.json` records every delta from R3. The fresh
original Rain head is rebuilt once with the revised cage, never by stacking
R1–R3 edits. Original topology, weights and keys are retained. Existing neutral
and balanced warm-smile views are rendered in front, three-quarter and profile.
The same warm-smile helper is used; expression improvements must not be
misrepresented as neutral identity changes.

## Verification / current status

Native [41707828875](https://github.com/PandaGarry/docuflow/actions/runs/41707828875)
**success, 10m47s**, published `ba17810`. Eight actual frames: three neutral,
three warm-smile views and two known-failing blink diagnostics. A separate
process reopened the actual saved `.blend`: Basis/evaluated errors **0 m**,
neutral pixel MAE **0**, pose restore **0 m**, all **17** images packed. This is a
same-worker saved-file check, **not** an independent downloaded-artifact check.

- [Canonical / R3 / R4, neutral](../studio/reviews/mom-head-form-r4/comparison-identity.png)
- [Same smile controls, canonical / R3 / R4](../studio/reviews/mom-head-form-r4/comparison-warm.png)
- [R3/R4 in front, three-quarter and profile](../studio/reviews/mom-head-form-r4/comparison-clay.png)
- [Visual review and remaining defects](../studio/reviews/mom-head-form-r4/visual-review.json)
- [Native result](../studio/reviews/mom-head-form-r4/report.json) /
  [reopen receipt](../studio/reviews/mom-head-form-r4/reopen/verification.json)

Editable binary: [artifact13266881865](https://github.com/PandaGarry/docuflow/actions/runs/41707828875/artifacts/13266881865),
`mom-head-form-r4-native-wip`, 71,773,001 bytes, expires **2026-11-17 20:05 UTC**.
Inside archive `.cache/rain-v3/mom-head-form-r4.blend` (hidden `.cache` directory).
SHA256 `558a416ab2f9a13915ed34158dabba3f4915a5f533cc18496a4bf3fac79ec2c6`.
Saved neutral clay study, body/hair retained but hidden; smile frames are posed
separately, not default saved animation. Recipes and review images persist in Git.

### Visual assessment, separate from technical verification

Neutral mouth placement/width is closer to the portrait by visual inspection;
less square lower jaw preserves the supported direction. Changes remain
coherent in side/three-quarter, but this is not a complete anatomy sign-off.
Rounded tip is a modest improvement; alar/nostril underside remains too hard.

**Still not enough likeness:** upper-lip seam/Cupid bow reads too flat, philtrum
secondary planes are underdefined. The warm smile now reads broader and more
crescent-shaped than the portrait's restrained smile. Do not present it as a
completed canonical expression. Equal controls are for fair before/after, not
proof of the same expression. Target hair/framing/materials are still missing.
Next art work should address these specific forms and expression range rather
than repeatedly shrinking the jaw or widening the mouth.

Sampled cage determinant stays positive; this is mathematical sample safety,
not continuous invertibility, likeness, good anatomy or film quality.

Blink/lash failure remains explicit, unchanged and unapproved. Full facial
rest/attachment migration, acting, hair, body, skin lookdev and wardrobe are not
complete. `art_approved=false`, `production_swap_allowed=false`.

Historical R1/R2/R3 recipes and review receipts are preserved.

Credit: **Rain Rig (CC) Blender Foundation | studio.blender.org**, modified,
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). No endorsement.
