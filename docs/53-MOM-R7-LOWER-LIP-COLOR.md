# Mom R7 — retain compact ears, complete current lower-lip color correction

Continuation of the same user request. R5 established compact original ears and
attached colors. R6 corrected upper pigment boundary/iris but actual native
frames exposed an overly pale lower vermilion. Do not label either as finished.

R7 keeps **all R6 geometry and ear settings identical**. It restores original
anatomical lower-lip deform-weight color below the seam, while retaining R6's
explicit upper boundary. Coral lower lip follows the real rigged surface.
Roughness uses a separate POINT FLOAT attribute (.39lip/.47skin), albedo alpha
stays1. It does not reuse alpha for material response. Original eye UV/texture,
globe geometry, gray-blue ramp, brows and source rig retained.

## Actual result and current review

[Native41719835416](https://github.com/PandaGarry/docuflow/actions/runs/41719835416)
**SUCCESS8m28s**, publish `a5424ad`:11actual clay/color/pose frames. A second
process reopened the saved `.blend`: Basis/evaluated error0m, neutral pixel MAE0,
pose restore0m,17images packed. Actual albedo hash, separate roughness attribute
and shader link survived saving. This is same-worker saved-file verification,
not an independent uploaded-artifact download/reopen.

- [Canonical / actual neutral form / color](../studio/reviews/mom-head-form-r7/comparison-identity.png)
- [Restrained native portrait smile](../studio/reviews/mom-head-form-r7/comparison-portrait.png)
- [Ears before/after, three matched native views](../studio/reviews/mom-head-form-r7/comparison-ears.png)
- [Color in front/three-quarter/profile](../studio/reviews/mom-head-form-r7/color-three-views.png)
- [Honest visual findings](../studio/reviews/mom-head-form-r7/visual-review.json)
- [Native report](../studio/reviews/mom-head-form-r7/report.json) /
  [saved-file receipt](../studio/reviews/mom-head-form-r7/reopen/verification.json)

Editable [artifact13271961756](https://github.com/PandaGarry/docuflow/actions/runs/41719835416/artifacts/13271961756),
`mom-head-form-r7-native-wip`,72,722,621bytes, expires **2026-11-17 21:21UTC**.
Inside `.cache/rain-v3/mom-head-form-r7.blend` (hidden `.cache` directory).
SHA256 `959dc66df1376241d9d664d17fdbbbeb6e04bfc1607b64244cc0007790a1779f`.
Opens colored/neutral, front camera; body/hair retained but hidden. Separate
smile renders/helper are not default saved animation. Source/frames persist in Git.

### Visual assessment — partial progress, not finished likeness

Ears are visibly more compact, with outer-X reduction7.74mm per side and roughly
6.46mm less height in the fixed ear subset. These are actual geometry diagnostics,
not portrait-calibrated ear dimensions (reference ears are largely hidden).
R7 lower vermilion is pink/coral again, unlike pale R6. Upper color border and
muted gray-blue iris read closer than first R5 colors. Original topology/eyes/
rig retained; materials follow the actual mesh, not painted onto rendered pixels.

**Still unfinished:** skin/cheek/nostril warmth and light contrast weaker than
canonical portrait; upper-lip edge/philtrum and button-nose secondary forms need
more art work. Eyelid/lash integration and blink remain blocked. Missing target
hair/frame is a major identity difference. No exact likeness, completed face,
full acting or film-quality claim. R7 geometry is exactly R6 (Basis/evaluated
arrays equal), so color progress is not mislabeled as new form reconstruction.
The native recipe's inherited `new_geometry_created` flag describes a fresh
source mesh rebuild; review explicitly records no R6-to-R7 shape change.

346local tests PASS17.505s,31task planning/checklist/diff checks PASS. These tests
check actual provenance, persistence, masked color and geometry intent, not art.
 No private inputs, no generated replacement, no render paint-over.
Known blink/lash failure, full facial/ear rest migration, canonical hair/body/
wardrobe and exact likeness/film-quality acceptance remain open. Production
swap=false. Historical R5/R6 recipes, failed color frames and receipts preserved.

Credit: Rain Rig (CC) Blender Foundation | studio.blender.org, modified CC BY4.0.
