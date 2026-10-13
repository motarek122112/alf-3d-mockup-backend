import io,json,hashlib,os,sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import approved_assets
from app.registry import GARMENTS


def test_unapproved_all_blocked():
    for item in GARMENTS:
        assert approved_assets.lookup_approved_asset(item.model) is None


def test_hash_and_permission_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(approved_assets,'ASSET_BASE',tmp_path)
    folder=tmp_path/'security';folder.mkdir()
    (folder/'model.glb').write_bytes(b'sample-nonproduction-glb'*150)
    record={'approved':True,'model_id':'security','model_format':'glb',
       'model_sha256':hashlib.sha256((folder/'model.glb').read_bytes()).hexdigest(),
       'physical_reference_reviewed':True,'commercial_use_rights_verified':True,
       'material_reviewed':True,'verified_decal_surfaces':['left_chest','back'],
       'placement_scale_limits': {'left_chest':[0.08,0.2],'back':[0.1,0.28]}}
    (folder/'approval.json').write_text(json.dumps(record))
    # Verification can be performed without Blender to test the approval parser.
    got=approved_assets.lookup_approved_asset('security',require_renderer=False)
    assert got and got.model_id=='security'
    record['model_sha256']='0'*64
    (folder/'approval.json').write_text(json.dumps(record))
    assert approved_assets.lookup_approved_asset('security',require_renderer=False) is None
    record['model_sha256']=hashlib.sha256((folder/'model.glb').read_bytes()).hexdigest()
    record['physical_reference_reviewed']=False
    (folder/'approval.json').write_text(json.dumps(record))
    assert approved_assets.lookup_approved_asset('security',require_renderer=False) is None


def test_worker_prevents_nonapproved_production(monkeypatch):
    # Model registry holds 7 categories but none are manufacturer-approved.
    import importlib
    from app.service import catalog
    rows=catalog()['categories']
    assert len(rows)==7
    if not os.getenv('ALF_ALLOW_PROVISIONAL_MODELS','false').lower()=='true':
        assert all(not entry['available_for_generation'] for entry in rows)
