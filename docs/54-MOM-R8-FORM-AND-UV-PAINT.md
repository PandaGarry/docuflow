# Mom R8 — real secondary form and original-UV paint

The user requests more professional work and closer canonical resemblance, not
another technical-only or color-only pass. Preserve the supported R2–R4
character direction and compact ears; do not infer finished-face acceptance.

## Visual hypothesis and authored form

Pupil-aligned R7 comparison still reads nose/mouth low, nasal dome flat, anterior
cheek planes insufficiently rounded and lip complex too projecting/soft-edged.
These are visual judgments with unknown reference camera/depth, not calibrated
3D dimensions or a likeness score.

Fresh-source R8 cage revises actual anatomy: nose tip/shoulders up3mm and forward
1.2–1.5mm, nostril/columella support raised/softened, lip complex up2–3.2mm with
reduced central projection, anterior malar volume forward1.5mm, gentle lower
cheek/chin-corner transitions. Declared per-control deltas are in
`studio/authoring/mom-head-form-r8.json`. Original eye/lid/canthus/brow controls,
brow centerline and compact-ear settings unchanged. Same coherent map on all
original key coordinates; this does not complete rest/control migration.

## Material work, separate from form proof

Low-resolution POINT albedo interpolated too softly around the vermilion edge.
R8 paints an editable2048px albedo plus a separate roughness map on the
**original Rain UV layout**. Source-rest surface positions and original lip
weights define anatomically bounded strokes with paired peaks/central valley,
soft cheeks/nose warmth and no R6 lower-lip cutoff. Original UVs are hashed
before geometry edits, after painting and after saved-file reopen.

This is NOT reference-photo projection, generated head replacement, face warp,
or paint-over of rendered frames. Pure UV rasterizer samples source surface at
texel centers; island padding protects seams. The first actual native attempt41726684266 failed at an explicit single-tile
UV assumption, after producing real clay views. Those frames/log/data are
preserved under `studio/reviews/mom-head-form-r8/attempt-1/`; no colored result
or saved-file success is claimed for that attempt.

The corrected painter uses the original **render** UV layer and a bounded,
explicit square source-domain transform in the shader. UV coordinates/layout
are not rewritten, clipped or silently repeated. Uniform domain scale preserves
island proportions. Source domain/min/max/UV hash are exported; actual shader
origin/scale/UV links and packed EXR bytes are checked on reopen. Layouts with
nonfinite coordinates or spans exceeding16UV units fail closed. Actual saved
linear floating-point EXR files are reloaded and packed before material use.
Native saved-state checks verify packed EXR bytes and actual image/UV shader links.
R7 point albedo/roughness remain fallback data, not the active material source.

## Checkpoint

Pure tests and actual native build/reopen prepared; result and visual review
pending. Matched neutral clay views isolate geometry from material changes.
Colored and restrained-smile views are separate. No hair/wardrobe/body reset.

Known blink/lash failure and full facial/ear rest migration remain open. Positive
sample Jacobians are not complete anatomical/collision/acting certification.
No exact likeness/film-quality/completed-face claim. Art/production swap=false.
Canonical masters/history frozen; private inputs not read/published.

Credit: Rain Rig (CC) Blender Foundation | studio.blender.org, modified CC BY4.0.
