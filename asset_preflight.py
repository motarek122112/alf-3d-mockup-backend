"""List which garment assets have completed their human QA and hash verification."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.registry import GARMENTS
from app.approved_assets import lookup_approved_asset,blender_available,ASSET_BASE

rows=[]
for item in GARMENTS:
    asset=lookup_approved_asset(item.model)
    rows.append({'category_id':item.category,'model':item.model,'label':item.label,
                 'approved_and_renderable':bool(asset),
                 'missing_or_blocked':[] if asset else ['Approved model GLB, license/material audit, exact SHA-256 and/or Blender engine required']})
print(json.dumps({'renderer_available':blender_available(),'approved_dir':str(ASSET_BASE),
                  'approved_count':sum(r['approved_and_renderable'] for r in rows),
                  'total':len(rows),'assets':rows},indent=2))
