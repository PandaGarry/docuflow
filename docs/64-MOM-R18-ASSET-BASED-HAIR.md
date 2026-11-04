# R18 — asset-based hair fitting and coordinated face finish

## Actual R17 comparison, before new work

R17 front partly follows the canonical silhouette, but3/4/profile expose scalp
and disconnected parallel tresses. The construction is rejected, not a base for
another thickness/density tweak. Canonical hair has connected coverage, broad
soft wave masses and fine strand detail. Nose/alar transitions remain angular,
lip contour differs and skin is too pale/desaturated compared with reference.

## Acquired assets, not promises of assets

Two actual MakeHuman hair meshes (`bob02`, `long01`) reconstructed from the
pinned HumanGen Web CC0 data conversion, which explicitly identifies its source
as the MakeHuman **CC0 system asset pack**. Their source render topology, UV and
alpha strand textures are retained. See
`studio/assets/external/makehuman-hair-r18/manifest.json` for source commit,
paths, hashes and license provenance. CC0 data are separate from MIT app code.
Old AGPL asset checkout is NOT used in the character.

- `bob02`: side-parted fringe; candidate for lengthening and shoulder waves.
- `long01`: continuous long hair coverage; alternate candidate.

Only hair is imported. Original Rain head/body/eyes/rig are not replaced.
Candidates must be shown as actual fitted native frames, not accepted by name.
The fitting is a smooth3D scale/deformation retaining asset UV and transparency,
not canonical texture projection. Original assets and R8–R17 history stay frozen.

## Work and acceptance

Use actual verified R17 binary, not rebuilding earlier recipes. Native probe
will inspect actual albedo sampling on the nose before more color guessing.
A coordinated bounded face fairing/material pass must preserve topology,
weights/key names/UV/rest and check all actual original corrective surfaces.

Keep preview versus full native render/reopen separate. No art/user/production
approval or automatic merge follows from passing technical checks. Clothes and
known full acting/blink/dynamics limitations remain explicit unless actually
changed and tested. All actual renders and honest review must be committed.

Credit Rain Rig (CC) Blender Foundation | studio.blender.org, modified CC BY4.0.
Hair mesh/texture: MakeHuman system assets, CC0; pinned conversion provenance
and legal text distributed with vendored data. This is not MakeHuman endorsement.

## Actual completed R18 evidence and rejection

[Canonical / R17 / R18](../studio/reviews/mom-character-r18/comparison-face-hair.png) ·
[Actual four views](../studio/reviews/mom-character-r18/portrait-views.png) ·
[Held-light face](../studio/reviews/mom-character-r18/comparison-held-light-face.png) ·
[Actual review](../studio/reviews/mom-character-r18/visual-review.md).

Run41871456981 / job126719396386 /11m39s succeeded,9 fresh build frames plus
reopened neutral (RGB MAE0). NativeSHA
`9411af2239504c05a1d902c29358d6c46c411c341dfb0862fcf03d7e4439d99c`.
[Editable native artifact13346560157](https://github.com/PandaGarry/docuflow/actions/runs/41871456981/artifacts/13346560157),
103118169bytes, expires2026-11-18T17:01:38Z. Separate-process reopen on same
worker, NOT independent redownload. Original25 keys; actual max head edit2.978mm.

Both eyes open, rear coverage improved, source alar pigment actually measured;
warmer linear skin energy(.72) and matching body pigment, new alar volume and
continuous wider collar were genuinely saved. Original head topology, weights,
UV, key names, eye/cornea coordinates and rig rest retained. Actual full hair
coordinate/polygon/UV/packed-image/ramp/response state verified on reopen.

**Still visually rejected:** rigid outlined hair ribbons and angular tips;
face/skin/lip/brow likeness incomplete. Art/user/production=false, full blink
visual failure unchanged. R18 is not the completed requested character.

Failed first fitting and first full attempt remain frozen in`preview/` and
`attempt-1/`. One follow-up validation caught width expansion wrongly applied
to the hidden long01 alternative; source corrected without relaxing its bound.
Run41871208139 cancelled, not a successful render or art evidence.

## Additional software actually used

Local bpy4.5.0 now imports and constructs the acquired source mesh/material.
Seven missing native libraries were built from pinned public Xorg/xkbcommon/
GLVND sources in disposable cache; no system replacement or binaries committed.
[Actual local asset preflight](../studio/reviews/mom-character-r18/local-preflight.json)
records engine, dependency pins, geometry/UV/material fingerprints and six clear
foreground-eye rays. It explicitly did NOT load the original character rig and
is not a full native-character or GPU certificate. Full original-rig evidence
comes from the worker above. GitHub release/artifact direct downloads remain
blocked by sandbox host restrictions; worker downloads are available.

Next: R19 uses the acquired surfaces as3D growth guides, not finished ribbon
hair, and creates real fine native HAIR curves. R18 original face/look/rig stay
unchanged for that groom-only comparison. See docs/65-MOM-R19-FINE-SURFACE-HAIR.md.
