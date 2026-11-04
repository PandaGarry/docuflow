# R17 — coordinated face identity and new volumetric hair

Native evidence pending at the first source checkpoint; no final likeness claim.
This revision is a coherent head/hair/material pass on the **actual saved R16
Rain asset**, not another reconstruction from an obsolete source or a new head.

## Design corrections

- Raise the oral region ~4.3 mm, reduce projection ~2.2 mm and relax the corners;
  reevaluate the smooth spatial deformation on all 25 original head blocks.
  A shared, locally attenuated displacement was visually rejected in preview 1.
- Contract the physical pupil/iris surface **only in XZ** with a smooth held
  sclera boundary. Preserve original cornea, UVs, sampled eye texture and Y.
  Lighter blue-gray iris response and larger original catchlight geometry.
- Rounded nasal guide/fairing with apex approximately held; small smooth naris
  rim + inner-wall contraction instead of pulling only the visible wall.
- Raise inner brow more than outer brow and retain original brow strip/fibers.
- Author new 2048px packed floating-point original-UV albedo/PBR maps: soft rosy
  nasal tip/cheeks, coral-pink lips, separate roughness and controlled skin SSS.
  The canonical portrait is **never loaded as a model texture**.
- Replace R16's sparse cable-like groom with 19 independent **closed sculpted
  locks**, asymmetric broad fringe and overlapping long wave flows. Longitudinal
  ridges, UV strand detail and fine native surface fibers follow these volumes.
  There is **no single solid crown/cap object**. This is authored geometry, not
  an acquired third-party hair asset. Depth is independently designed in 3D;
  manual canonical XZ flow points are not a calibrated reconstruction.

## Evidence policy

The first worker run makes actual Cycles front/three-quarter and unobscured face
previews for inspection. The final worker adds higher-resolution three-view
portraits, unobscured clay views, a saved/reopened neutral pair and exact native
head/UV/eye/rig persistence checks. Preview success is not final acceptance.
Boards use only uniform pupil registration: no feature warping, canonical-image
projection or render repainting. A head/hair-focused crop is explicitly labeled;
raw frames include the unchanged, unfinished R16 wardrobe.

Clothing is deliberately unchanged. The existing blink/lash visual failure,
full facial corrective/rest migration, acting/lip-sync, shoulder hair dynamics
and clothing are **not certified** by neutral likeness work or geometry tests.
No user/art acceptance, production swap, merge or delivery approval is inferred.

Source: actual R16 run `41829196725`; binary SHA-256
`439818d40c59b5edbe0b2e2271438a7fb74b77453e79e17dfd9436e77d5823e2`.
Original Rain head topology, weights, original 25 key names and rig rest retained.
Canonical and private inputs are not modified. Historical R8–R16 packages frozen.

Credit: **Rain Rig (CC) Blender Foundation | studio.blender.org**, modified,
CC BY 4.0. Original reference art is a design guide, not a reusable texture.

## Native development checks

- `41837832725`: correctly stopped by an original corrective orientation check;
  no frame was produced. Basis-only pure checks did not detect that corrective.
- `41838231030`: jointly bounded against all 25 original blocks (174 locally
  attenuated vertices, minimum signed area ratio .058), then stopped on Blender's
  actual anisotropy socket name before rendering. No visual success claimed.
  Both logs are preserved under `studio/reviews/mom-character-r17/attempts/`.
- Lightweight full suite at source development checkpoint: **455 tests passed**,
  40.279 s. This does not certify native execution or artistic likeness.

## Actual preview inspection and corrective transport change

`41838585578` produced the real first preview successfully. It was **visually
rejected**, not promoted: the shared residual limiter left visible lip folds,
and the hair had ribbon-like volumes, inadequate inner fringe and abrupt layer
intersections. See the frozen `preview/visual-review.md` and native frames.

The next candidate reevaluates the continuous spatial sculpt for each original
corrective, rather than applying discontinuous per-vertex attenuation. The
strict native orientation check still runs against each original block; original
key names, topology, weights, drivers and rig rest remain. Corrective coordinate
deltas are intentionally transported, not claimed bit-identical. Additional
inner fringe, corrected layer depths/outward wave ends, softer strand response
and source-UV pigment calibration address the actual observed errors. The
second preview uses a separate `preview-2/` directory; preview 1 stays intact.
