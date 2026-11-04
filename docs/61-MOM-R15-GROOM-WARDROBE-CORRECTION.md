# R15 — correct actual first groom/wardrobe faults, preserve face progress

R14 rendered actual frames but was rejected: angular pale pupil artifacts,
sparse pale overly long hair with stepped roots, inward vest offset, floating
collar/sleeves, mismatched chest skin. It also failed combined restore guard
(no completed native reopen). Source and failure frames/manifest remain frozen.

R15 rebuilds from the verified downloaded R13 binary, retaining all R14 head
proportion/ear/brow targets and original25keys/weights/UV/rest. Corrections:

- Keep original R13 cornea, highlight dots, eye material and UV sampler intact.
  Increase only original front iris/eye mesh radially8% in XZ, smoothly holding
  outer globe; no depth change or replacement eye. Aperture refinement retained.
-13864native tapered HAIR curves (not mesh cap), curved root envelope, denser
  waves, asymmetric swept fringe. Compress lower length to shoulder level from
  normalized canonical eye-to-hair-tip guidance (~2.1IPD). Physical melanin
  fiber shading instead of R14's overly pale direct-color fiber result.
- Orient original garment normals OUTWARDS before14mm vest offset; original
  garment contains inward-facing surfaces. Wider sleeve overlap, folded collar
  closer to vest. Match original body/chest skin to head palette.
- Restore ONLY the two ACT corner locations actually changed by smile, not all
 2166driven/constrained pose bones. Strict roundtrip checks before expensive
  renders, and a recorded post-render integrity check; thresholds not relaxed.

New native Cycles front at1024×1280/64samples;3Q/profile768×960/48samples; separate
bare clay/head evidence. Separate-process native reopen and neutral render
comparison required. Actual result/visual review pending at source publication.

Still no approved full acting, blink, hair/shoulder dynamics, cloth simulation,
exact likeness or production swap. Rain Rig (CC) Blender Foundation |
studio.blender.org, modified CC BY4.0. Art/user/production=false.

## Actual result: native verified, appearance still needs refinement

Run41827110660 SUCCESS6m59s; artifact13320506111 (95,233,769bytes), until
2026-11-18T12:18:13Z. ACT-only restore error0; saved-native reopen pixel MAE0.
Original head/eyes are now coherent, softer oval/ears/brows retained, vest visible
and skin matched. But actual multiview inspection still rejects floating/gapped
part roots, aligned lower-hair kinks/tips, tubular collar and jagged piping.
These are not final canonical/film-quality hair/clothes. Freeze R15; next pass
will edit appearance on this actual verified binary without rebuilding the face.
