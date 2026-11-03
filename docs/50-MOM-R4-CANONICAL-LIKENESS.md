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

Implementation and pure tests prepared; native run and visual review pending.
A separate process will reopen the actual saved `.blend` and check its geometry,
packed textures, rig rest, neutral render and smile restoration. This is a
same-worker saved-file check, **not** an independent downloaded-artifact check.

Sampled cage determinant stays positive; this is mathematical sample safety,
not continuous invertibility, likeness, good anatomy or film quality.

Blink/lash failure remains explicit, unchanged and unapproved. Full facial
rest/attachment migration, acting, hair, body, skin lookdev and wardrobe are not
complete. `art_approved=false`, `production_swap_allowed=false`.

Historical R1/R2/R3 recipes and review receipts are preserved.

Credit: **Rain Rig (CC) Blender Foundation | studio.blender.org**, modified,
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). No endorsement.
