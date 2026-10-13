# ALF 3D renderer update v0.3 — setup and safety

## What this code now actually does

- Keeps the **existing `POST /api/mockups/sessions` / uploads / jobs / status / results API**, so the previously integrated Shopify quote page does not need a frontend rewrite for this backend update.
- Registers all seven *categories* but keeps them non-generatable until they have **manufacturer-reviewed, commercially licensed garment GLBs**.
- Enforces SHA-256 approval, supported model and material configuration, logo placement zone and scale validation.
- Adds a **Blender Cycles** renderer for approved garment GLBs, with a controlled studio, color adjustment on explicitly marked fabric materials, UV decals with embroidery/DTF/screen-print visual treatments, and front / back / 3-quarter images plus an interactive GLB export.
- Keeps the existing provisional CPU renderer for **isolated local development testing only**. In production, `ALF_ALLOW_PROVISIONAL_MODELS=true` is intentionally ignored.
- Preserves customer logo and job access restrictions of the existing app.

## What's NOT done / do not enable in production yet

- No actual ALF manufacturer-verified garment assets have been supplied. Assets inside `assets/provisional` are deliberately not approved.
- Blender Cycles is **not installed in this development container**, so the new Blender subprocess has only been syntax/preflight-checked, **not an end-to-end rendered garment test**.
- On Render Free, the 0.1 CPU / 512 MB RAM server is for API tests only; it spins down and has ephemeral storage. It cannot meet an assured 3–5 minute commercial photorealistic render target.
- Persistent worker queues, transactional Postgres, durable S3/R2 logo storage, quota enforcement at the edge, multiple client jobs, GDPR/storage policy, manual 3D scene/art approval, and live Shopify mobile regression tests are outstanding.
- Shader bump simulates a texture but is **not digitized embroidery**. Manufacturer stitch geometry or stitch-map references are needed for production-grade embroidery fidelity.
- The 7 registry entries are not all garment subtypes: apron, cargo trousers, and full security uniform are **not** supplied as individually accurate assets. Those must be created and registered before supporting the requested subtypes.

## GitHub upload — IMPORTANT

Extract the ZIP. The **repository root** must contain `app/` as an actual subfolder:

```
app/__init__.py
app/service.py
app/registry.py
app/modeling.py
app/worker.py
app/approved_assets.py
app/approved_render.py
app/blender_render_scene.py
assets/provisional/...
assets/approved/... (only after physical approval)
tests/...
requirements.txt
Procfile
```

Do **not** flatten the `app` directory into GitHub's root. Do **not** upload a ZIP as a single file and expect Render to unzip it automatically.

Render API web service commands after fixing directory layout:

Build: `pip install -r requirements.txt`
Start: `uvicorn app.service:app --host 0.0.0.0 --port $PORT`

Leave these safe values:

`ALF_MOCKUP_ENV=production`  
`ALF_ALLOW_PROVISIONAL_MODELS=false`  
`ALF_MOCKUP_DATA=/tmp/alf-mockup-data` (Free: **not persistent**)  
`ALF_MOCKUP_SIGNING_KEY=<your private random 32+ character secret>`

Do not put the secret in GitHub. `/health` shows asset and Blender readiness, and `/api/mockups/catalog` exposes each item's approval state.

## To start the *real* rendering stage

1. Get GLB models made from approved ALF reference garments, including material and UV logo zones named `ALF_DECAL_<placement>`; acquire commercial usage rights.
2. Verify front orientation -Y, up +Z, recolorable garment materials `ALF_COLOR_FABRIC*`, stable UVs and correct curved logo decal surfaces.
3. Put each model in `assets/approved/<model_id>/model.glb` and create its individual `approval.json` based on `assets/approval.example.json`. Every approval requires a valid file SHA-256, explicit physical/material/license confirmation, and vetted decal sizes. `python tools/asset_preflight.py` must report approved models.
4. Supply an appropriate rendering machine with Blender installed and set `ALF_BLENDER_BIN`, `ALF_APPROVED_ASSET_DIR`, `ALF_RENDER_RESOLUTION`, `ALF_CYCLES_SAMPLES`. Use `python -m app.worker` there, with a durable shared job store and uploads/results accessible from both API and worker.
5. Run at least one full product render and examine collar, seams, buttons, folds, logo curve, stitching and color against ALF references. Reject inaccurate garment assets. For 7 categories, evaluate all approved subtypes, not just category names.
6. Replace the current local SQLite/temp file arrangement with durable Postgres + private S3/R2/compatible object storage and robust job queue before production; *do not deploy independent workers sharing only `/tmp`*.
7. When those conditions pass and live quote integration is tested, configure `Mockup renderer API URL (HTTPS)` in Shopify Theme Editor.

## Tested in this package

`OPENBLAS_NUM_THREADS=1 pytest -q tests/test_backend.py tests/test_approved_assets.py`

Expected: 5 tests pass in local development. The render scene script compiles, but physical Blender rendering remains unverified.
