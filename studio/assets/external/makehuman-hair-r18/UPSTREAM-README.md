# HumanGen Web

Standalone WebGL human generator, built from the [mpfb2](https://github.com/makehumancommunity/mpfb2)
(MakeHuman for Blender) base mesh and morph targets. No Blender, no server logic: a static site.

- Macro sliders (gender, age, muscle, weight, height, proportions, cup size, firmness, race) using
  the same target-blending rules as mpfb2's `TargetService`.
- 234 detail sliders (head, nose, torso, ...) and 34 expression face units (blended by race like mpfb2).
- 22 MakeHuman skin textures (auto-picked from age/race/gender or chosen manually), tint colour,
  high-poly eyes fitted onto the body via the `.mhclo` weights, 9 iris textures,
  12 eyebrow, 4 eyelash, 10 hair, 6 teeth, 1 tongue and 20 clothes proxies (same fitting, alpha-textured
  WebP, normal maps where MakeHuman ships them, hair tint). Clothes hide the body faces they cover
  (`delete_verts`).
- Optional rig (mpfb2 `game_engine` or `default`): joints are placed from the morphed mesh, skin weights
  are mpfb2's (top 4 per vertex), proxies inherit weights from the vertices they are fitted to. Bones have
  identity rotation; importers derive bone direction from the hierarchy.
- Poses: 43 CC0 BVH poses (MakeHuman repo + poses01/poses02 packs) or your own `.bvh`. Applied directly
  to the `default` rig, retargeted to `game_engine` by world rotation of the matching chain end. Multi-frame
  BVH files get a frame slider and playback; the GLB then carries the animation. OBJ exports the current frame.
- Download as OBJ (body + all proxies, quads + UVs) or GLB with textures and skeleton, save/load presets as
  JSON, import MakeHuman `.mhm` files (modifiers, skin, eyes, brows, lashes, hair, clothes, skeleton).

Live: https://nastyffm.github.io/HumanGenWeb/ (GitHub Pages, deployed from `main`).

## Run

Any static file server, e.g.

```bash
python -m http.server 8123
```

then open http://localhost:8123. three.js is loaded from jsDelivr.

## Rebuild the data

Needs `pip install pillow`. Assets come from the mpfb2 checkout plus the MakeHuman CC0 asset pack:

```bash
git clone --depth 1 https://github.com/makehumancommunity/mpfb2
# assets/eyes/: high-poly.obj + high-poly.mhclo from github.com/makehumancommunity/makehuman (makehuman/data/eyes/high-poly)
#               plus *_eye.png from eyes/materials in the asset pack below
# assets/skins/, eyebrows/, eyelashes/, hair/, teeth/, tongue/, clothes/: those folders of
#   https://files.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip
# assets/poses/*.bvh: makehuman repo data/poses plus the .bvh files of
#   https://files.makehumancommunity.org/asset_packs/poses01/poses01_cc0.zip and poses02/poses02_cc0.zip
python build_data.py mpfb2 assets
```

Writes `data/` (base mesh as binary, one sparse `.bin` per target, eye proxy, skins downscaled to
2048 px JPEG, slider metadata). Targets are fetched on demand, so only the ones in use are downloaded.

## Licence

Mesh and targets come from MakeHuman / mpfb2 and are CC0. App code: MIT.
