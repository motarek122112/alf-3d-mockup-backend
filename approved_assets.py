"""Approval-gated manufacturer garment assets (no demo garments in production).

Every artist-produced garment asset needs an individual signed-off manifest and exact
file digest. The manifest is only an operational gate; the owner must verify the
physical garment and licensing before setting approved=true.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib, json, os, shutil
from .registry import BY_MODEL

ASSET_BASE = Path(os.environ.get('ALF_APPROVED_ASSET_DIR', 'assets/approved')).resolve()
BLENDER_BIN = os.getenv('ALF_BLENDER_BIN', 'blender')
MAX_ASSET_SIZE = 200 * 1024 * 1024

@dataclass(frozen=True)
class ApprovedAsset:
    model_id: str
    model_path: Path
    allowed_decals: tuple[str, ...]
    approval_data: dict


def blender_available():
    return bool(shutil.which(BLENDER_BIN) or Path(BLENDER_BIN).is_file())


def lookup_approved_asset(model_id: str, require_renderer: bool = True) -> ApprovedAsset | None:
    if model_id not in BY_MODEL:
        return None
    folder = (ASSET_BASE / model_id).resolve()
    # Never follow a symlinked model folder outside the approved catalog.
    if ASSET_BASE not in folder.parents:
        return None
    meta = folder / 'approval.json'
    glb = folder / 'model.glb'
    if not meta.is_file() or not glb.is_file() or glb.is_symlink():
        return None
    if require_renderer and not blender_available():
        return None
    try:
        record = json.loads(meta.read_text('utf-8'))
        if record.get('approved') is not True or record.get('model_id') != model_id:
            return None
        if not record.get('physical_reference_reviewed') or not record.get('commercial_use_rights_verified'):
            return None
        expected = record.get('model_sha256', '')
        if len(expected) != 64 or not all(c in '0123456789abcdef' for c in expected.lower()):
            return None
        if not (1024 < glb.stat().st_size <= MAX_ASSET_SIZE):
            return None
        with glb.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if expected.lower() != actual:
            return None
        placement_names = tuple(record.get('verified_decal_surfaces', []))
        if not placement_names or not set(placement_names).issubset(set(BY_MODEL[model_id].placements)):
            return None
        scale_limits=record.get('placement_scale_limits')
        if not isinstance(scale_limits, dict) or set(scale_limits)!=set(placement_names):
            return None
        for name in placement_names:
            pair=scale_limits[name]
            if not isinstance(pair,list) or len(pair)!=2 or not all(isinstance(n,(int,float)) for n in pair):
                return None
            if not (0.06 <= pair[0] <= 0.14 <= pair[1] <= 0.35):
                return None
        if record.get('model_format') != 'glb' or record.get('material_reviewed') is not True:
            return None
        return ApprovedAsset(model_id=model_id, model_path=glb,
                             allowed_decals=placement_names, approval_data=record)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def production_state():
    return {m: bool(lookup_approved_asset(m)) for m in BY_MODEL}
