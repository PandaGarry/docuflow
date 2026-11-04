# R19 — actual fine native hair, not completed canonical likeness

[Canonical / R18 / R19](../studio/reviews/mom-character-r19/comparison-face-hair.png) ·
[Four actual views](../studio/reviews/mom-character-r19/portrait-views.png) ·
[Actual review](../studio/reviews/mom-character-r19/visual-review.md) ·
[Native receipt](../studio/reviews/mom-character-r19/report.json) ·
[Separate-process reopen](../studio/reviews/mom-character-r19/verification.json).

## Method and editable inputs

Actual verified R18 binary SHA
`9411af2239504c05a1d902c29358d6c46c411c341dfb0862fcf03d7e4439d99c`
is loaded. Original Rain face, eyes/cornea,25 head keys, UV, weights/rest and
skin maps are retained exactly. This revision changes groom only; no claimed
new face improvement or fake new anatomy frames.

`studio/tools/mom_groom_r19.py` walks fitted CC0 mesh UV islands separately,
rasterizes barycentric3D guide positions/normals, splits discontinuities/alpha
outside real source strands, resamples1374 paths to40 points and grows16000
seeded fine native HAIR curves(640000 points). Radius3.8–62micrometres. These
are not R17's thick procedural tubes. Real Principled Hair melanin/reflection;
source mesh retained as dark coverage. Original DEF-Head attachment preserved;
no shoulder/hair dynamics certification. Separate island processing prevents
reused source UV from erasing overlapping cards. No canonical pixels sampled.

Sources: MakeHuman CC0 system pack via pinned HumanGen conversion, receipts in
`studio/assets/external/makehuman-hair-r18/`. The app's MIT code is not copied.
No raw AGPL stock hair used. Rain credit/license retained, modified CC BY4.0.

## Actual outcome

**Surface finish visibly improves; macro hair design and identity still fail.**
Fine strands/reflection replace the pale flat ribbon appearance, but source
bob-derived large forms, crown/part continuity, rear flow and pointed shoulder
ends do not match canonical soft broad S-waves. Color too dark/banded. Increasing
fiber count or recoloring again would not fix those structural errors. R18
face/nose/lip/brow/skin differences remain. No artistic or production approval.

## Native deliverable and limitations

Run41902535932/job126828466087,9m50s, native SUCCESS; bpy4.5.0.
Four fresh portrait views plus saved/reopened neutral:6 fresh frames. Four raw
bare/clay frames explicitly reused from unchanged R18, not new R19 renders.
Full hair coordinates/radii/shader and undercoat state verified on reopen,
original head/look/rest match; pose restore0m, RGB MAE0;19 packed images.
Separate process same worker, NOT independent redownload. Full blink/acting,
wardrobe and hair/cloth dynamics unapproved. No automatic merge/master swap.

[Editable `.blend` artifact13358264061](https://github.com/PandaGarry/docuflow/actions/runs/41902535932/artifacts/13358264061),
97008854bytes, expires2026-11-18T20:10:56Z. Native SHA:
`c0b83d504951d646e91b035c723c76966d00d69548807fd8d5f0feac7592d43b`.
Large native binaries remain in external artifacts, not Git; actual frames,
source and rejection reviews are durable in repository. PR3 stays open.
