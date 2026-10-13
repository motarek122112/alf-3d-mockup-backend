# ALF 3D Garment Asset Manifest

**Status: NOT APPROVED / PROVISIONAL.** Seven GLB demonstration meshes are included for developer and API integration testing only. They are visibly simplified silhouettes, NOT photorealistic cloth, NOT manufacturer-specific ALF garments, and NOT ready to show to real customers.

| ID | Garment model | Current demonstrator | Required before launch |
|---|---|---|---|
| ALF-01 | polo | single basic polo silhouette | Real polo and T-shirt meshes, distinct styles, collars, sleeve lengths, PBR cloth, UV and embroidery zones |
| ALF-02 | chef_jacket | single chef jacket outline | Accurate chef jacket AND apron meshes; buttons, fabric, kitchen branding and approved logos |
| ALF-03 | chef_cap | basic cap outline | Verified chef caps/accessories, realistic hat volume and curvature-based branding |
| ALF-04 | workwear | basic workwear jacket outline | Cargo pants, workwear jackets and full workwear sets, seam and pocket geometry |
| ALF-05 | security | basic security shirt outline | Actual security shirt, trousers, and full uniform models, proper epaulettes and pocket details |
| ALF-06 | corporate | basic corporate shirt outline | Accurate corporate shirt meshes, collars, cuffs, pocket types and garment sizes |
| ALF-07 | event | basic promotional tee outline | Promo T-shirts, vests, event apparel models with corresponding approved placements |

Every approved asset also requires photography/material reference, manufacturer dimensional checks, UV and PBR material review, texture optimization, logo placement safety bounds, commercial license, and front/back/angle visual acceptance.

Demo use: set `ALF_ALLOW_PROVISIONAL_MODELS=true` ONLY in an isolated local development environment. Do not set it true on the public Shopify-facing server.

Default API returns a clear rejection for unsupported/unapproved garments, rather than making up a high-quality render.
