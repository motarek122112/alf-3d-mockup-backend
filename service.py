import io,os,re,time,json,hmac,hashlib,secrets,sqlite3,uuid,mimetypes
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import quote
from PIL import Image,ImageOps,UnidentifiedImageError
from fastapi import FastAPI,HTTPException,UploadFile,File,Header,Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,Field,field_validator
from itsdangerous import URLSafeTimedSerializer,BadSignature,SignatureExpired
from .registry import BY_CATEGORY,ALLOWED_COLORS,public_registry

ROOT=Path(os.getenv('ALF_MOCKUP_DATA','/tmp/alf-mockup-data')).resolve()
DB=ROOT/'jobs.sqlite3'
APPROVED_MODE=os.getenv('ALF_ALLOW_PROVISIONAL_MODELS','false').lower()=='true'
SECRET=os.getenv('ALF_MOCKUP_SIGNING_KEY','')
if len(SECRET)<32:
    if os.getenv('ALF_MOCKUP_ENV','development')=='production':raise RuntimeError('ALF_MOCKUP_SIGNING_KEY must be set to 32+ characters in production')
    SECRET='INSECURE-DEVELOPMENT-ONLY-'+ '9'*50
SIGN=URLSafeTimedSerializer(SECRET,salt='alf-mockup-session')
FILE_SIGN=URLSafeTimedSerializer(SECRET,salt='alf-mockup-assets')
ORIGINS=[x.strip() for x in os.getenv('ALF_ALLOWED_ORIGINS','https://alf-uniforms-kw.myshopify.com,https://www.alfuniforms.com').split(',') if x.strip()]
MAX_LOGO_BYTES=int(os.getenv('ALF_LOGO_MAX_BYTES',10*1024*1024))
MAX_IMAGE_PIXELS=16_000_000
ROOT.mkdir(parents=True,exist_ok=True)
app=FastAPI(title='ALF Mockup Generator API',version='0.2.0-provisional',docs_url='/docs' if os.getenv('ALF_MOCKUP_ENV')!='production' else None)
app.add_middleware(CORSMiddleware,allow_origins=ORIGINS,allow_credentials=False,allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type','Idempotency-Key'])

def connect():
    conn=sqlite3.connect(DB,timeout=15,isolation_level=None)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=15000')
    return conn

def db_init():
    with connect() as con:
        con.executescript('''CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY, session_id TEXT NOT NULL, basename TEXT NOT NULL, sha256 TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,config TEXT NOT NULL,idempotency TEXT NOT NULL, status TEXT NOT NULL,stage TEXT NOT NULL,progress REAL,started REAL,created REAL NOT NULL,updated REAL NOT NULL,error TEXT, result TEXT, UNIQUE(session_id,idempotency));
        CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(status,created);''')
db_init()

class Placement(BaseModel):
    name: str
    scale: float = Field(default=.14, ge=.06, le=.35)

class JobRequest(BaseModel):
    quote_ref: str=Field(min_length=1,max_length=128)
    category_id: str
    model_id: str
    logo_upload_id: str
    color: str
    branding_method: str
    placements: list[Placement]=Field(min_length=1,max_length=3)
    customer_approved: bool = True
    @field_validator('branding_method')
    @classmethod
    def branding_ok(cls,v):
        if v not in ('embroidery','dtf','screen_print'):raise ValueError('Unsupported branding method')
        return v

async def auth_session(authorization:str|None):
    if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'Session token required')
    try: session_id=SIGN.loads(authorization[7:],max_age=86400)
    except (SignatureExpired,BadSignature):raise HTTPException(401,'Session expired or invalid')
    if not re.fullmatch(r'[0-9a-f]{32}',str(session_id)):raise HTTPException(401,'Invalid session')
    with connect() as db:
        if not db.execute('SELECT id FROM sessions WHERE id=?',(session_id,)).fetchone():raise HTTPException(401,'Unknown session')
    return session_id

def scoped_path(parent,name):
    path=(ROOT/parent/name).resolve();directory=(ROOT/parent).resolve()
    if directory not in path.parents:raise HTTPException(400,'Invalid path')
    return path

@app.get('/health')
def health():
    return {'api':'ok','rendering':'provisional' if APPROVED_MODE else 'awaiting_approved_3d_assets','worker':'run separately', 'production_ready':False}

@app.get('/api/mockups/catalog')
def catalog():return public_registry(APPROVED_MODE)

@app.post('/api/mockups/sessions')
async def new_session(request:Request):
    # Production should add IP/merchant quotas at edge gateway before opening public sessions.
    id=uuid.uuid4().hex
    with connect() as db:db.execute('INSERT INTO sessions VALUES (?,?)',(id,time.time()))
    return {'session_token':SIGN.dumps(id),'expires_in':86400,'quote_session_id':id}

@app.post('/api/mockups/uploads')
async def upload_logo(file:UploadFile=File(...),authorization:str|None=Header(default=None)):
    sid=await auth_session(authorization)
    data=await file.read(MAX_LOGO_BYTES+1)
    if len(data)>MAX_LOGO_BYTES:raise HTTPException(413,'Logo exceeds upload limit')
    if len(data)<70:raise HTTPException(415,'Image is invalid')
    allowed={'PNG':'image/png','JPEG':'image/jpeg','WEBP':'image/webp'}
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in allowed:raise HTTPException(415,'Only PNG/JPEG/WebP logos accepted')
            if im.width*im.height>MAX_IMAGE_PIXELS:raise HTTPException(413,'Image pixel count exceeds safe limit')
            im=ImageOps.exif_transpose(im)
            # Preserve transparency; no external AI transformations performed without approval.
            rgba=im.convert('RGBA')
            if rgba.width<300 or rgba.height<300:warning='Low-resolution artwork: fine embroidery details may not reproduce faithfully.'
            else:warning=None
            upload_id=uuid.uuid4().hex
            directory=ROOT/'uploads'/sid;directory.mkdir(parents=True,exist_ok=True)
            target=directory/f'{upload_id}.png';rgba.save(target,optimize=True)
            digest=hashlib.sha256(data).hexdigest()
    except (UnidentifiedImageError,ValueError,OSError,Image.DecompressionBombError):raise HTTPException(415,'Unable to read safe image')
    with connect() as db:db.execute('INSERT INTO uploads VALUES (?,?,?,?,?)',(upload_id,sid,Path(file.filename or 'logo').name[:128],digest,time.time()))
    return {'upload_id':upload_id,'sha256':digest,'width':rgba.width,'height':rgba.height,'warning':warning}

@app.post('/api/mockups/jobs',status_code=202)
async def create_job(req:JobRequest, authorization:str|None=Header(default=None),idempotency_key:str|None=Header(default=None)):
    sid=await auth_session(authorization)
    if not idempotency_key or not re.fullmatch(r'[A-Za-z0-9_\-]{16,100}',idempotency_key):raise HTTPException(400,'Valid Idempotency-Key required')
    garment=BY_CATEGORY.get(req.category_id)
    if garment is None:raise HTTPException(422,'Unsupported uniform category')
    if req.model_id!=garment.model:raise HTTPException(422,'Model subtype is not approved for this category')
    if not garment.approved and not APPROVED_MODE:raise HTTPException(422,'A manufacturer-approved 3D asset is required before customer generation can be enabled')
    if req.color.lower() not in ALLOWED_COLORS:raise HTTPException(422,'Choose an available uniform color')
    if req.branding_method not in garment.methods:raise HTTPException(422,'Branding method not supported')
    if not req.customer_approved:raise HTTPException(422,'Customer approval required')
    names=[p.name for p in req.placements]
    if len(set(names))!=len(names) or any(p not in garment.placements for p in names):raise HTTPException(422,'Invalid logo placement for selected garment')
    with connect() as db:
        if not db.execute('SELECT id FROM uploads WHERE id=? AND session_id=?',(req.logo_upload_id,sid)).fetchone():raise HTTPException(422,'Logo upload not found in your session')
        existing=db.execute('SELECT id,config FROM jobs WHERE session_id=? AND idempotency=?',(sid,idempotency_key)).fetchone()
        req_json=req.model_dump_json()
        if existing:
            if existing['config']!=req_json:raise HTTPException(409,'Idempotency key was reused with different data')
            return {'job_id':existing['id'],'status_url':f'/api/mockups/jobs/{existing["id"]}','status':'existing'}
        pending=db.execute("SELECT COUNT(*) FROM jobs WHERE session_id=? AND created>? AND status NOT IN ('FAILED','CANCELLED')",(sid,time.time()-3600)).fetchone()[0]
        if pending>=3:raise HTTPException(429,'Maximum of three mockups per hour reached for this session')
        job=uuid.uuid4().hex;now=time.time()
        db.execute('INSERT INTO jobs(id,session_id,config,idempotency,status,stage,progress,created,updated) VALUES(?,?,?,?,?,?,?,?,?)',(job,sid,req_json,idempotency_key,'QUEUED','QUEUED',None,now,now))
    return {'job_id':job,'status':'QUEUED','status_url':f'/api/mockups/jobs/{job}','eta_seconds':None}

def job_view(row):
    result=json.loads(row['result']) if row['result'] else None
    return {'job_id':row['id'],'status':row['status'],'stage':row['stage'],'progress':row['progress'],'eta_seconds':None,'started':row['started'],'created':row['created'],'updated':row['updated'],'error':row['error'],'result':result}

@app.get('/api/mockups/jobs/{job_id}')
async def get_job(job_id:str,authorization:str|None=Header(default=None)):
    sid=await auth_session(authorization)
    with connect() as db:row=db.execute('SELECT * FROM jobs WHERE id=? AND session_id=?',(job_id,sid)).fetchone()
    if not row:raise HTTPException(404,'Job not found')
    return job_view(row)

@app.post('/api/mockups/jobs/{job_id}/cancel')
async def cancel_job(job_id:str,authorization:str|None=Header(default=None)):
    sid=await auth_session(authorization)
    with connect() as db:
        row=db.execute('SELECT status FROM jobs WHERE id=? AND session_id=?',(job_id,sid)).fetchone()
        if not row:raise HTTPException(404,'Job not found')
        if row['status'] not in ('QUEUED',):raise HTTPException(409,'Only queued jobs can be cancelled safely')
        db.execute("UPDATE jobs SET status='CANCELLED',stage='CANCELLED',updated=? WHERE id=?",(time.time(),job_id))
    return {'job_id':job_id,'status':'CANCELLED'}

@app.get('/api/mockups/jobs/{job_id}/result')
async def result(job_id:str,request:Request,authorization:str|None=Header(default=None)):
    sid=await auth_session(authorization)
    with connect() as db:row=db.execute('SELECT * FROM jobs WHERE id=? AND session_id=?',(job_id,sid)).fetchone()
    if not row:raise HTTPException(404,'Job not found')
    if row['status']!='COMPLETED':raise HTTPException(409,'Job has not completed')
    names=['front.png','back.png','angle.png','model.glb']
    folder=ROOT/'results'/job_id
    if not all((folder/name).is_file() for name in names):raise HTTPException(503,'Result files are not yet available')
    prefix=str(request.base_url).rstrip('/')
    media={name.split('.')[0]: f'{prefix}/api/mockups/assets/{job_id}/{name}?access={quote(FILE_SIGN.dumps([job_id,sid,name]),safe="")}' for name in names}
    return {'job_id':job_id,'assets':media,'expires_in':900,'provisional':not BY_CATEGORY[json.loads(row['config'])['category_id']].approved,'disclaimer':'Design preview only. Final production details are confirmed by ALF Uniforms.'}

@app.get('/api/mockups/assets/{job_id}/{name}')
def get_asset(job_id:str,name:str,access:str,download:bool=False):
    if not re.fullmatch(r'[a-f0-9]{32}',job_id) or name not in ('front.png','back.png','angle.png','model.glb'):raise HTTPException(404,'Asset not found')
    try:parts=FILE_SIGN.loads(access,max_age=900)
    except (BadSignature,SignatureExpired):raise HTTPException(403,'Asset link expired')
    if parts[0]!=job_id or parts[2]!=name:raise HTTPException(403,'Invalid access')
    with connect() as db:found=db.execute('SELECT id FROM jobs WHERE id=? AND session_id=? AND status=?',(job_id,parts[1],'COMPLETED')).fetchone()
    if not found:raise HTTPException(403,'Access denied')
    path=scoped_path('results',job_id)/name
    if not path.is_file():raise HTTPException(404,'Missing result')
    return FileResponse(path,media_type='model/gltf-binary' if name.endswith('glb') else 'image/png',filename=name if download else None,content_disposition_type='attachment' if download else 'inline',headers={'Cache-Control':'private, max-age=300','X-Content-Type-Options':'nosniff'})

# Explicit preview-share authorization: only the customer holding the scoped
# session can grant a limited-time link for ALF staff to view the result.
SHARE_SIGN=URLSafeTimedSerializer(SECRET,salt='alf-mockup-explicit-shares')
SHARE_TTL=7*24*3600
class ShareRequest(BaseModel):
    consent: bool

@app.post('/api/mockups/jobs/{job_id}/share')
async def create_share(job_id:str,req:ShareRequest,request:Request,authorization:str|None=Header(default=None)):
    sid=await auth_session(authorization)
    if not req.consent:raise HTTPException(422,'Explicit consent required to share the preview')
    with connect() as db:row=db.execute("SELECT id FROM jobs WHERE id=? AND session_id=? AND status='COMPLETED'",(job_id,sid)).fetchone()
    if not row:raise HTTPException(404,'Completed mockup not found')
    token=SHARE_SIGN.dumps([job_id,sid])
    base=str(request.base_url).rstrip('/')
    return {'share_url':f'{base}/api/mockups/shared/{job_id}/assets/front.png?share={quote(token,safe="")}', 'expires_in':SHARE_TTL,'note':'Anyone with the generated preview link can view its front image until expiry. Logo source files remain private.'}

@app.get('/api/mockups/shared/{job_id}/assets/{name}')
def public_shared(job_id:str,name:str,share:str):
    if name not in ('front.png','back.png','angle.png'):raise HTTPException(404,'Only approved preview images can be shared')
    try:parts=SHARE_SIGN.loads(share,max_age=SHARE_TTL)
    except (BadSignature,SignatureExpired):raise HTTPException(403,'Link expired or invalid')
    if parts[0]!=job_id:raise HTTPException(403,'Invalid link')
    with connect() as db:found=db.execute("SELECT id FROM jobs WHERE id=? AND session_id=? AND status='COMPLETED'",(job_id,parts[1])).fetchone()
    if not found:raise HTTPException(403,'Forbidden')
    path=scoped_path('results',job_id)/name
    if not path.is_file():raise HTTPException(404,'Preview not found')
    return FileResponse(path,media_type='image/png',headers={'Cache-Control':'private, max-age=180','X-Content-Type-Options':'nosniff'})
