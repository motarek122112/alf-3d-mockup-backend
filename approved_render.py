"""Blender rendering of *approved* garment GLB assets only.

Not compatible with intentionally simplified provisional assets. A production GLB
must expose ALF_DECAL_<placement> UV mapped mesh(es) with the approved orientation.
"""
from pathlib import Path
import json, os, subprocess, sys
from .approved_assets import lookup_approved_asset, BLENDER_BIN

SCRIPT = Path(__file__).parent / 'blender_render_scene.py'


def render_approved_asset(job_id, params, logo_path, out_dir, on_stage):
    approved = lookup_approved_asset(params['model_id'])
    if approved is None:
        raise RuntimeError('No approved, verified garment asset or Blender executable')
    requested = {p['name'] for p in params['placements']}
    if not requested.issubset(set(approved.allowed_decals)):
        raise ValueError('One or more branding surfaces are not approved on this garment')
    output = Path(out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    job_data = {
        'job_id': job_id,
        'glb_path': str(approved.model_path),
        'logo_path': str(Path(logo_path).resolve()),
        'output_dir': str(output),
        'model_id': params['model_id'],
        'placements': params['placements'],
        'branding_method': params['branding_method'],
        'garment_hex': params['color_hex'],
        'samples': min(160,max(48,int(os.getenv('ALF_CYCLES_SAMPLES', '80')))),
        'resolution': min(2600,max(1000,int(os.getenv('ALF_RENDER_RESOLUTION', '1600')))),
    }
    config = output / 'render_job.json'
    config.write_text(json.dumps(job_data, ensure_ascii=True), encoding='utf-8')
    on_stage('PREPARING_GARMENT')
    # No shell=True: never allow a user to alter the Blender command or run scripts.
    try:
        process = subprocess.Popen([
            BLENDER_BIN, '-b', '--factory-startup', '-t',
            str(max(1, min(4, int(os.getenv('ALF_BLENDER_THREADS','2'))))),
            '--python', str(SCRIPT), '--', str(config),
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=str(output), env=os.environ.copy())
    except OSError as exc:
        raise RuntimeError('Unable to start Blender worker') from exc
    import time
    started=time.monotonic(); recent=[]
    # Stream stage changes; don't invent progress or countdown percentages.
    try:
        for line in process.stdout:
            recent.append(line.rstrip()[:500]);recent=recent[-15:]
            if line.startswith('ALF_STAGE:'):
                stage=line.split(':',1)[1].strip()
                if stage in {'APPLYING_BRANDING','RENDERING_FRONT','RENDERING_BACK',
                             'RENDERING_ANGLE','OPTIMIZING_MODEL','FINALIZING'}:
                    on_stage(stage)
            if time.monotonic()-started>900:
                process.kill()
                raise TimeoutError('Rendering exceeded worker safety limit (15 minutes)')
        if process.wait(timeout=10)!=0:
            raise RuntimeError('Blender rendering failed: '+ '\\n'.join(recent[-5:])[-950:])
    finally:
        if process.poll() is None:
            process.kill(); process.wait()
    for fname in ['front.png','back.png','angle.png','model.glb']:
        p = output/fname
        if not p.is_file() or p.stat().st_size < 1024:
            raise IOError(f'Blender did not produce valid {fname}')
    config.unlink(missing_ok=True)
    return {'files':['front.png','back.png','angle.png','model.glb'],
            'provisional':False,'renderer':'blender-cycles','source_asset_sha256':approved.approval_data['model_sha256']}
