# Mom R10 — restrained lip form, not a stronger pose slider

User asks to continue with more professional work/closer likeness. Actual R9
review: mouth still pouts; lower vermilion too pale/matte. R10 addresses these
specific findings without resetting supported nose/cheeks/eyes/ears.

Eight original indexed oral cage targets only: closed corners up1.875mm,
seam up0.6mm/back0.6mm, lower lip up2.1mm/back2.4mm, Cupid peaks back1.125mm/
down0.6mm, upper center back1.125mm/down0.525mm, border down0.375mm. No further
mouth widening. Same original source/83anchors/25keys; same ACT smile amount0.4
for controlled comparisons. Source rest/control migration is still pending;
unchanged source rig is not a claim of final anatomy or performance quality.

Original render UVMap/tile1003 retained. Upper/lower source-rest pigment masks
unchanged from R9; warmer lower pigment#E17A60, upper#B95C49. Same canonical
skin#E8B48F. Packed linear PBR image uses explicit independent RGB channels:
R roughness(.40upper/.29lower/.47skin), G coat weight(.05upper/.17lower/0skin),
B coat roughness(.22). SeparateColor links are inspected on binary reopen;
localized vermilion sheen, not global gloss or output-frame paint.

Source-coordinate sampled determinant minimum0.1800064556; maximum local
R9→R10 Basis cage change3.86743mm. These are bounded numerical checks, not
continuous invertibility, anatomy, likeness or cinema-quality approval. At authoring, actual
native rebuild/multi-view/pose/reopen and visual review were pending; actual results below. Failed
attempts will be preserved. Canonical masters and frozen R9 recipe unchanged.

Known blink/lash failure, full face/ear rest migration, canonical hair/frame,
body/wardrobe and complete acting remain open. No user/art/production approval.
Private photos not read/published.

Credit: Rain Rig (CC) Blender Foundation | studio.blender.org, modified CC BY4.0.

## Actual primary native result

[41779442779](https://github.com/PandaGarry/docuflow/actions/runs/41779442779)
SUCCESS3m30s/job126407376188/publish1735308. Artifact13298308136,
86,863,271bytes, expiry2026-11-18T05:31:42Z. `mom-head-form-r10.blend` SHA256
`3b90652155d8d408e196cec54af76dbd45e3db6db4709d015b1cbaa82076beea`.
19packed images; separate-process same-worker saved-binary reopen verifies
geometry/UV/PBR channel links/packed bytes and original pose restore. Native
success is not final appearance approval.

- [Canonical / R9 / R10](../studio/reviews/mom-head-form-r10/comparison-identity.png)
- [Isolated clay form](../studio/reviews/mom-head-form-r10/comparison-form.png)
- [Three actual views](../studio/reviews/mom-head-form-r10/color-three-views.png)
- [Local lip detail](../studio/reviews/mom-head-form-r10/comparison-lips.png)
- [Inspected visual findings](../studio/reviews/mom-head-form-r10/visual-review.json)

Clay confirms locally smaller lower lip/reduced projection; color is warmer and
less chalky. Corner/expression improvement is modest; canonical closed-smile
line, fine Cupid contour and lower highlight still differ. Do not infer a full
smile correction from moving the authored targets.

381local tests PASS20.666s;31task validate/checklist/diff PASS. At this checkpoint a separate fresh
worker was prepared to download actual published R9/R10 `.blend` files,
verify them without acquiring original Rain, independently rerender R10 neutral
pixels, then compare both under identical 1024²/96sample portrait lighting.
Light and material presentation must not be counted as geometry improvement.
No altered lookdev blend or new character acceptance is implied.


## Independent downloaded-binary result and controlled portrait light

[41780052780](https://github.com/PandaGarry/docuflow/actions/runs/41780052780)
SUCCESS5m1s/job126409296083/publish5ffc609. Unlike primary same-worker reopen,
this fresh worker downloads the actual R9/R10 published artifacts and does NOT
acquire/rebuild original Rain. Both binary SHA256 values match committed
reports; geometry/rest/weights/keys/UV/map bytes/packed files survive, all19
images packed per asset. Neutral geometry max coordinate error0 and pose restore0
for both; independently rerendered R10 neutral RGB MAE/p99=0 before changing light.

Then 1024²/96sample Cycles/AgX portrait renders use the same lights/camera and
native0.4smile for both versions. No mesh, shader, palette or source `.blend`
bytes altered by this light-only stage. Artifact13298852829 is4,775,568bytes,
expires2026-11-18T05:39:08Z (review frames/receipt, not another character binary).

- [Canonical / identically lit R9 / R10](../studio/reviews/mom-head-lookdev-r10/comparison-portrait.png)
- [SAME R10 under diagnostic and portrait light](../studio/reviews/mom-head-lookdev-r10/comparison-lighting.png)
- [Portrait-light three views](../studio/reviews/mom-head-lookdev-r10/portrait-three-views.png)
- [Independent native receipt](../studio/reviews/mom-head-lookdev-r10/report.json)
- [Actual visual findings](../studio/reviews/mom-head-lookdev-r10/visual-review.json)

Visible form progress is modest, lower pigment warmer. The held-light comparison
reveals upper lip still too heavy/protruding, under-lip shadow too strong and no
canonical lower-lip highlight yet. The PBR settings are not proof that the
intended visible response succeeded. Softer closed-smile seam/perioral transitions
remain the art focus. Light-only improvement is explicitly not another form pass.
No finished-face, full anatomy, exact-likeness, acting or cinema-quality acceptance.

Final local verification:386tests PASS21.468s;31task validate/checklist/diff PASS.
