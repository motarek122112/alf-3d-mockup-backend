# ALF Uniforms: licensed manufacturer garment asset requirements

**No files in `assets/provisional/` are customer-approved.** Do not rename or copy them into `assets/approved/` and mark them approved.

For each of the seven categories supply the *specific purchasable ALF garment* as a commercial-use-authorized GLB with:

- PBR garment material named `ALF_COLOR_FABRIC...` for recoloring. Non-recolorable trim, buttons, pockets, zippers and insignia must have their own materials.
- Physical garment proportions, collar, sleeves, seams and folds checked against photographs or manufacturer files, and a sensible cloth material with UVs / normal / roughness.
- Existing UV-mapped decal surfaces, named **exactly** `ALF_DECAL_left_chest`, `ALF_DECAL_back`, etc. Positions approved per garment by the owner. Model front faces **-Y**, back faces +Y, Z points up.
- Decal surfaces follow garment curvature, align closely with fabric but stay just above the cloth to avoid z-fighting. UV vertices must have expected image orientation.
- License confirming use in a customer-facing commercial preview and redistribution as an interactive GLB.
- Verification of garment shape, branding-safe boundaries and fabric color with actual ALF samples.

The current initial registry supports only one subtype per category, **not all variants**. For example, `chef_jacket` does not include a real apron, and `security` is a shirt rather than a full security uniform. New subtypes require separate assets and registry entries, not generic substitutions.

## Asset folder structure

```
assets/approved/
  security/
    model.glb
    approval.json
  polo/
    model.glb
    approval.json
  ...
```

Start with the provided `approval.example.json` and set `approved: true` **only after the artwork, commercial rights, UV placement surfaces and GLB SHA-256 have been verified.** Never publish customer previews from the provisional models. The backend rejects an asset with an absent/incorrect digest, absent renderer, or missing approval checkboxes.

## Realism and manufacturing

The Blender pipeline supports real 3D geometry, studio lights, Cycles rendering and UV-bound logo colors with different shader settings for embroidery/DTF/screen printing. The embroidery wave bump is **only a surface preview**, not digitized embroidery stitches. Accurate stitch direction, thread selection and production validation need manufacturer artwork/digitizing and further renderer asset work.

## Render Free limitation

Render Free is **0.1 CPU, 512 MB memory**, sleeps after inactivity, and loses uploads/SQLite on restart/redeploy. It is usable for API readiness and authorization tests, **not a dependable 3–5 minute photorealistic Blender rendering service**. Plan for an appropriate render worker and persistent shared object storage/DB before a customer launch.
