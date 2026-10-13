import os,io,uuid,sys
from pathlib import Path
from PIL import Image,ImageDraw
os.environ['ALF_MOCKUP_DATA']='/tmp/alf-mockup-test-'+uuid.uuid4().hex
os.environ['ALF_ALLOW_PROVISIONAL_MODELS']='true'
os.environ['ALF_MOCKUP_SIGNING_KEY']='X'*64
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.service import app
from app.worker import process_job
from app.registry import GARMENTS

client=TestClient(app)

def logo_bytes():
    img=Image.new('RGBA',(620,420),(0,0,0,0));d=ImageDraw.Draw(img)
    d.ellipse((80,75,530,370),fill=(30,100,225,255));d.rectangle((210,180,390,230),fill=(252,252,252,255))
    b=io.BytesIO();img.save(b,format='PNG');return b.getvalue()

def create_session():
    r=client.post('/api/mockups/sessions');assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['session_token']}

def upload(headers):
    r=client.post('/api/mockups/uploads',headers=headers,files={'file':('alf-sample.png',logo_bytes(),'image/png')})
    assert r.status_code==200,r.text
    return r.json()['upload_id']

def test_full_seven_categories():
    for item in GARMENTS:
        headers=create_session();upload_id=upload(headers)
        payload={'quote_ref':'integration-test','category_id':item.category,'model_id':item.model,'logo_upload_id':upload_id,
                 'color':'navy','branding_method':'embroidery','placements':[{'name':item.placements[0],'scale':.13}]}
        r=client.post('/api/mockups/jobs',headers={**headers,'Idempotency-Key':'K'+uuid.uuid4().hex},json=payload)
        assert r.status_code==202,(item.category,r.text)
        job=r.json()['job_id'];assert process_job(job),f'{item.category} job failed'
        r=client.get('/api/mockups/jobs/'+job,headers=headers);assert r.json()['status']=='COMPLETED',r.text
        r=client.get('/api/mockups/jobs/'+job+'/result',headers=headers);assert r.status_code==200,r.text
        for key,url in r.json()['assets'].items():
            r=client.get(url);assert r.status_code==200,(key,r.text)
            assert len(r.content)>500,(key,len(r.content))
        no_auth=client.get('/api/mockups/jobs/'+job)
        assert no_auth.status_code==401

def test_validation_and_persistence():
    headers=create_session();up=upload(headers)
    payload={'quote_ref':'test','category_id':'ALF-05','model_id':'security','logo_upload_id':up,'color':'navy','branding_method':'embroidery','placements':[{'name':'left_chest'}]}
    key='a'+uuid.uuid4().hex
    r=client.post('/api/mockups/jobs',json=payload,headers={**headers,'Idempotency-Key':key});assert r.status_code==202
    again=client.post('/api/mockups/jobs',json=payload,headers={**headers,'Idempotency-Key':key});assert again.json()['job_id']==r.json()['job_id']
    altered={**payload,'color':'red'}
    assert client.post('/api/mockups/jobs',json=altered,headers={**headers,'Idempotency-Key':key}).status_code==409
    assert client.post('/api/mockups/jobs',json={**payload,'category_id':'ALF-999'},headers={**headers,'Idempotency-Key':'d'+uuid.uuid4().hex}).status_code==422
    assert client.post('/api/mockups/jobs',json={**payload,'placements':[{'name':'cap_front'}]},headers={**headers,'Idempotency-Key':'f'+uuid.uuid4().hex}).status_code==422
    assert client.post('/api/mockups/jobs/'+r.json()['job_id']+'/cancel',headers=headers).status_code==200
    assert client.get('/api/mockups/jobs/'+r.json()['job_id'],headers=headers).json()['status']=='CANCELLED'
    assert client.post('/api/mockups/uploads',headers=headers,files={'file':('bad.exe',b'not-image','application/octet-stream')}).status_code in [413,415]
