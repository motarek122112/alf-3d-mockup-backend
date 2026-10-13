"""Standalone job worker. Provisional CPU 3D preview mode only.

Production must replace provisional garment geometry with manufacturer-approved GLBs
and Blender Cycles / equivalent high-quality physical render pipeline.
"""
import sys,time,json,math,os,io,traceback
from pathlib import Path
import numpy as np, cv2, trimesh
from PIL import Image,ImageDraw,ImageFilter,ImageFont
from .service import ROOT,connect,APPROVED_MODE
from .registry import BY_CATEGORY,ALLOWED_COLORS
from .modeling import create_scene,PROFILES,ZONES,material_color
from .approved_assets import lookup_approved_asset
from .approved_render import render_approved_asset


def update(job,stage,progress=None,status='RUNNING',error=None,result=None):
    with connect() as db:
        db.execute('UPDATE jobs SET status=?,stage=?,progress=?,error=?,result=?,updated=?,started=COALESCE(started,?) WHERE id=?',
                   (status,stage,progress,error,json.dumps(result) if result else None,time.time(),time.time(),job))

def project(x,y,z,angle,zoom=1):
    # rotate about vertical Z for consistent front/back/three-quarter images
    cs=math.cos(angle);sn=math.sin(angle)
    xr=x*cs-y*sn;yr=x*sn+y*cs
    perspective=1.0 + yr*.16
    return (int(700+xr*420*zoom/perspective),int(1010-z*610*zoom/perspective))

def render_view(model,color,logo,method,placements,angle,name,outdir):
    # Renderer is a deterministic preview from the same 3D geometry.
    # It does not simulate full physically based cloth and is clearly watermarked.
    W=1400;H=1400
    y,x=np.mgrid[0:H,0:W]
    l=np.clip((x-700)**2/1.8e6+(y-520)**2/1.6e6,0,1)
    arr=np.empty((H,W,3),dtype=np.uint8)
    for k,c in enumerate([238,242,248]):arr[:,:,k]=(c-36*l).astype('uint8')
    image=Image.fromarray(arr,'RGB').convert('RGBA')
    shadow=Image.new('RGBA',image.size);sd=ImageDraw.Draw(shadow)
    sd.ellipse((390,1105,1010,1220),fill=(24,38,56,70))
    shadow=shadow.filter(ImageFilter.GaussianBlur(42));image=Image.alpha_composite(image,shadow)
    frame=np.asarray(image.convert('RGB')).copy()
    mesh=trimesh.Trimesh()
    from .modeling import extrude_profile
    mesh=extrude_profile(PROFILES[model]);verts=mesh.vertices
    faces=mesh.faces
    base=np.asarray(material_color(color),float)
    # Actual triangle geometry is projected, lit by per-face normals and depth sorted.
    tris=[]
    for i,face in enumerate(faces):
        points=verts[face];xform=np.array([project(*v,angle) for v in points],np.int32)
        dz=points[:,1].mean()*math.cos(angle)+points[:,0].mean()*math.sin(angle)
        norm=np.cross(points[1]-points[0],points[2]-points[0]);nm=np.linalg.norm(norm)
        if nm>.0001: norm/=nm
        light=max(.22,.63+float(np.dot(norm,[-.3,-.58,.8]))*.29)
        tris.append((dz, xform, np.clip(base*light+23,0,255).astype(int).tolist()))
    # painter from back to near; y negative nearer front camera
    for dep,vertices,shade in sorted(tris,key=lambda r:r[0],reverse=True):cv2.fillConvexPoly(frame,vertices,shade,lineType=cv2.LINE_AA)
    image=Image.fromarray(frame,'RGB').convert('RGBA')
    # Actual logo texture projected onto a 3D facing plane (same coordinates as exported GLB)
    # front, angled, back have consistent coordinates. Embroidery preview: slight thread texture.
    for place in placements:
        p=place['name']; is_back=(p=='back')
        if (name=='front' and is_back) or (name=='back' and not is_back):continue
        if p not in ZONES:continue
        cx,cz=ZONES[p];h=min(.28,max(.06,place['scale'])); h=min(.14,h) if model=='chef_cap' else h
        logo_rgba=logo.copy().convert('RGBA');ar=logo_rgba.width/logo_rgba.height;w=h*min(ar,3)
        ypos=.097 if is_back else -.097
        quad=[(cx-w/2,ypos,cz+h/2),(cx+w/2,ypos,cz+h/2),(cx+w/2,ypos,cz-h/2),(cx-w/2,ypos,cz-h/2)]
        dst=np.float32([project(*v,angle) for v in quad]);src=np.float32([[0,0],[logo.width,0],[logo.width,logo.height],[0,logo.height]])
        if abs(np.linalg.det(cv2.getPerspectiveTransform(src,dst)))<1e-10: continue
        rgba=np.asarray(logo_rgba); M=cv2.getPerspectiveTransform(src,dst)
        warped=cv2.warpPerspective(rgba,M,(W,H),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        overlay=Image.fromarray(warped,'RGBA')
        if method=='embroidery':
            overlay=Image.alpha_composite(Image.new('RGBA',(W,H),(12,20,36,0)),overlay)
        image=Image.alpha_composite(image,overlay)
    d=ImageDraw.Draw(image)
    try:ft=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',25)
    except:ft=ImageFont.load_default()
    d.rounded_rectangle((34,28,490,91),radius=15,fill=(9,27,53,215));d.text((52,44),'ALF / DESIGN PREVIEW',font=ft,fill=(237,249,255,255))
    d.rounded_rectangle((50,1305,1350,1370),radius=14,fill=(9,27,53,220))
    d.text((79,1325),'PROVISIONAL 3D ASSET — NOT FINAL MANUFACTURING PROOF',font=ft,fill=(242,248,252,255))
    image.convert('RGB').save(outdir/f'{name}.png',quality=95)


def process_job(job_id):
    with connect() as db:
        row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not row or row['status'] not in ('QUEUED','RUNNING'):return False
    try:
        params=json.loads(row['config']);garment=BY_CATEGORY[params['category_id']]
        verified_asset=lookup_approved_asset(params['model_id'])
        if not APPROVED_MODE and not verified_asset:raise RuntimeError('Manufacturer-approved model is not available')
        logo_path=ROOT/'uploads'/row['session_id']/(params['logo_upload_id']+'.png')
        if not logo_path.is_file():raise ValueError('Uploaded logo is missing')
        update(job_id,'PREPROCESSING_LOGO')
        with Image.open(logo_path) as im:
            logo=im.convert('RGBA').copy()
            if logo.width>1800 or logo.height>1800:logo.thumbnail((1800,1800),Image.Resampling.LANCZOS)
        update(job_id,'PREPARING_GARMENT')
        model=params['model_id'];color=ALLOWED_COLORS[params['color'].lower()];method=params['branding_method'];placements=params['placements']
        output=ROOT/'results'/job_id;output.mkdir(parents=True,exist_ok=True)
        if verified_asset:
            params['color_hex']=color
            data=render_approved_asset(job_id,params,logo_path,output,lambda step:update(job_id,step))
            update(job_id,'COMPLETED',progress=100,status='COMPLETED',result=data)
            return True
        update(job_id,'APPLYING_BRANDING')
        scene=create_scene(model,color,logo,method,[p['name'] for p in placements],placements[0]['scale'])
        scene.export(output/'model.glb',file_type='glb')
        for idx,(name,angle) in enumerate([('front',0),('back',math.pi),('angle',math.pi/5)]):
            update(job_id,'RENDERING_'+name.upper())
            render_view(model,color,logo,method,placements,angle,name,output)
        update(job_id,'FINALIZING')
        expected=['model.glb','front.png','back.png','angle.png']
        for file in expected:
            p=output/file
            if not p.is_file() or p.stat().st_size<500:raise IOError(f'Render missing: {file}')
        update(job_id,'COMPLETED',progress=100,status='COMPLETED',result={'files':expected,'provisional':True,'renderer':'DEVELOPMENT_ONLY'})
        return True
    except Exception as exc:
        update(job_id,'FAILED',status='FAILED',error=str(exc)[:300])
        print('Job failed',job_id,str(exc),traceback.format_exc(),flush=True)
        return False


def work_once():
    # transactional claim; never mark a job complete from the storefront UI.
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute("SELECT id FROM jobs WHERE status='QUEUED' ORDER BY created LIMIT 1").fetchone()
        if row:
            db.execute("UPDATE jobs SET status='RUNNING',stage='PREPARING_GARMENT',updated=?,started=? WHERE id=? AND status='QUEUED'",(time.time(),time.time(),row['id']))
        db.execute('COMMIT')
    return process_job(row['id']) if row else None

if __name__=='__main__':
    once='--once' in sys.argv
    while True:
        result=work_once()
        if once:break
        time.sleep(.8 if result is not None else 2.0)
