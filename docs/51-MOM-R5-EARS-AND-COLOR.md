# Mom R5 — smaller ears, lip refinement, canonical face colors

User agrees with the R4 direction and explicitly asks for slightly smaller,
less projecting ears, closer face likeness and canonical colors. This is not
full-character approval. Original Rain geometry/rig remains the actual asset.

## Implementation

- Original ear surface: 10% local scale reduction with 4 mm lateral tuck and
  1.5 mm posterior tuck. Fixed source ear deform-weight mask with lateral gate
  protects the cheek/skull. Same attached vertex map on all 25 head keys.
  Sampled maximum outer-X reduction about7.74mm, not a uniform whole-head scale.
- Cupid peaks moved inward1.7mm, forward0.7mm, up0.9mm. Upper-lip center receives
  1mm forward volume; upper lip/philtrum border softened0.8mm. Nose underside
  support softened by submillimetre offsets. No further mouth widening/jaw shrink.
- Canonical skin `#E8B48F`, gray-blue iris `#73879A`, warm brown brows, rose/coral
  lips and subtle cheek/tip warmth. Editable linear-space shader colors, not
  guaranteed screen pixel matches under lighting/AgX.
- Lip color uses original lip-deform vertex weights with feathered border,
  stored as a POINT color attribute on the actual rigged mesh. It follows poses;
  no face-photo projection, rectangular lipstick patch or render retouch.
- Original eye texture/UVs and globe/cornea geometry preserved. Texture luminance
  maps to gray-blue iris ramp with neutral black pupil/white sclera endpoints.
- Restrained smile uses the existing bilateral native helper at amount0.4,
  instead of R4's stronger1.0. Do not label expression changes geometry progress.

Fresh-source rebuild, matched three-view clay **and** color renders, native
blink diagnostics and a separate-process saved-binary reopen are prepared.
Native41716230087 **success9m33s**, published809bed5. Eleven actual renders,
packed binary artifact13270168708 (expires2026-11-17T20:59:18Z). Separate-process
reopen checks passed including actual attached colors/material assignments.

**Visual review requires correction:** ears are more compact as requested, but
first upper-lip pigment is too high/diffuse, skin too pale/beige, iris too blue.
Deform weights alone did not define a finished lip border. Do not present R5 as
finished. R6 addresses these actual observed errors; preserve R5 evidence.
[Actual first-color review](../studio/reviews/mom-head-form-r5/comparison-identity.png)
/ [visual findings](../studio/reviews/mom-head-form-r5/visual-review.json). The saved file
will be colored and neutral with front camera; original body/hair retained but
hidden. This is still a face study, not completed hair/body/wardrobe.

## Limitations

Ear rest/control migration and full facial acting/lip-sync remain unapproved.
Known blink/lash failure not fixed or concealed. Positive sampled cage
Jacobians/triangle orientations are not complete anatomy/collision guarantees.
Art/production swap remain false. Canonical reference art/history unchanged;
private inputs neither read nor published.

Credit: **Rain Rig (CC) Blender Foundation | studio.blender.org**, modified,
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). No endorsement.
