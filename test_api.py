import os,sys,tempfile,importlib
from fastapi.testclient import TestClient
f=tempfile.NamedTemporaryFile(suffix='.db',delete=False);f.close();os.environ['DATABASE_PATH']=f.name;os.environ['SETUP_KEY']='test-key-for-local-only';sys.path.insert(0,os.path.dirname(__file__))
m=importlib.import_module('services.api.main');c=TestClient(m.app)
def check(r,code=200):assert r.status_code==code,(r.status_code,r.text);return r.json()
check(c.post('/setup',headers={'x-setup-key':'test-key-for-local-only'},json={'name':'Hotel A','email':'a@example.com','password':'long-test-password'}))
check(c.post('/setup',headers={'x-setup-key':'test-key-for-local-only'},json={'name':'Hotel B','email':'b@example.com','password':'long-test-password'}))
def auth(email):return {'Authorization':'Bearer '+check(c.post('/login',json={'email':email,'password':'long-test-password'}))['access_token']}
a=auth('a@example.com');b=auth('b@example.com')
room=check(c.post('/rooms',headers=a,json={'number':'101','category':'Deluxe'}))['id']
check(c.post('/bookings',headers=a,json={'room_id':room,'guest_name':'Guest','checkin':'2027-01-01','checkout':'2027-01-03','nightly_rate':150}))
check(c.post('/bookings',headers=a,json={'room_id':room,'guest_name':'Duplicate','checkin':'2027-01-02','checkout':'2027-01-04','nightly_rate':150}),409)
assert check(c.get('/rooms',headers=b))==[]
assert check(c.get('/bookings',headers=b))==[]
check(c.post('/ancillary',headers=a,json={'day':'2027-01-01','category':'F&B','amount':50}))
check(c.put('/market',headers=a,json={'day':'2027-01-01','market_occupancy':70,'market_adr':120}))
check(c.post('/rate-plans',headers=a,json={'name':'BAR','segment':'Direct','base_rate':175}))
x=check(c.get('/revenue-intelligence?day=2027-01-01',headers=a));assert x['room_revenue']==150 and x['trevpar']==200 and x['rgi'] is not None,x
assert check(c.get('/revenue-intelligence?day=2027-01-01',headers=b))['room_revenue']==0
assert check(c.get('/')).get('detail') is None if False else c.get('/').status_code==200
check(c.post('/logout',headers=a));check(c.get('/me',headers=a),401)
print('PASS: login, tenant isolation, inventory, overlap, KPI, ancillary, benchmarking, rates, logout, frontend')
os.unlink(f.name)
