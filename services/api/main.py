import os, sqlite3, secrets, hashlib, hmac
from pathlib import Path
from fastapi.responses import FileResponse
from datetime import date, datetime, timedelta
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
DB=os.getenv('DATABASE_PATH','atlas.db')
app=FastAPI(title='ATLAS RMS API',version='0.2.0')
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','http://localhost:3000').split(','),allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
@contextmanager
def db():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
 try: yield c;c.commit()
 finally:c.close()
def hashpw(p,s):return hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(s),310000).hex()
def init():
 with db() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS tenants(id INTEGER PRIMARY KEY,name TEXT NOT NULL);CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL REFERENCES tenants(id),email TEXT UNIQUE NOT NULL,salt TEXT NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL);CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),expires TEXT NOT NULL);CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL REFERENCES tenants(id),number TEXT NOT NULL,category TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,UNIQUE(tenant_id,number));CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL REFERENCES tenants(id),room_id INTEGER NOT NULL REFERENCES rooms(id),guest_name TEXT NOT NULL,checkin TEXT NOT NULL,checkout TEXT NOT NULL,nightly_rate REAL NOT NULL CHECK(nightly_rate>=0),status TEXT NOT NULL CHECK(status IN ('confirmed','cancelled')),created_at TEXT NOT NULL);CREATE INDEX IF NOT EXISTS idx_booking_dates ON bookings(tenant_id,checkin,checkout,status);''')
init()
class Login(BaseModel):email:str;password:str
class TenantCreate(BaseModel):name:str;email:str;password:str=Field(min_length=12)
class RoomCreate(BaseModel):number:str;category:str='Standard'
class BookingCreate(BaseModel):room_id:int;guest_name:str;checkin:date;checkout:date;nightly_rate:float=Field(ge=0)
def actor(authorization:str=Header(default='')):
 token=authorization.removeprefix('Bearer ').strip()
 with db() as c:
  r=c.execute('SELECT u.id,u.tenant_id,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?',(hashlib.sha256(token.encode()).hexdigest(),datetime.utcnow().isoformat())).fetchone()
 if not r:raise HTTPException(401,'Invalid or expired session')
 return dict(r)
@app.get('/health')
def health():return {'status':'ok'}
@app.post('/setup')
def setup(data:TenantCreate,x_setup_key:str=Header(default='')):
 if not os.getenv('SETUP_KEY') or not hmac.compare_digest(x_setup_key,os.environ['SETUP_KEY']):raise HTTPException(403,'Setup key required')
 salt=secrets.token_hex(16)
 with db() as c:
  try:
   cur=c.execute('INSERT INTO tenants(name) VALUES (?)',(data.name,));tid=cur.lastrowid
   c.execute('INSERT INTO users(tenant_id,email,salt,password_hash,role) VALUES (?,?,?,?,?)',(tid,data.email.lower(),salt,hashpw(data.password,salt),'admin'))
  except sqlite3.IntegrityError:raise HTTPException(409,'Email already exists')
 return {'tenant_id':tid,'created':True}
@app.post('/login')
def login(data:Login):
 with db() as c:
  u=c.execute('SELECT * FROM users WHERE email=?',(data.email.lower(),)).fetchone()
  if not u or not hmac.compare_digest(hashpw(data.password,u['salt']),u['password_hash']):raise HTTPException(401,'Invalid credentials')
  token=secrets.token_urlsafe(40)
  c.execute('INSERT INTO sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],(datetime.utcnow()+timedelta(hours=8)).isoformat()))
 return {'access_token':token,'token_type':'bearer','tenant_id':u['tenant_id']}
@app.get('/rooms')
def rooms(a=Depends(actor)):
 with db() as c:return [dict(x) for x in c.execute('SELECT id,number,category FROM rooms WHERE tenant_id=? AND active=1 ORDER BY number',(a['tenant_id'],))]
@app.post('/rooms')
def add_room(v:RoomCreate,a=Depends(actor)):
 if a['role']!='admin':raise HTTPException(403)
 with db() as c:
  try:r=c.execute('INSERT INTO rooms(tenant_id,number,category) VALUES (?,?,?)',(a['tenant_id'],v.number,v.category))
  except sqlite3.IntegrityError:raise HTTPException(409,'Room already exists')
  return {'id':r.lastrowid}
@app.get('/bookings')
def bookings(a=Depends(actor)):
 with db() as c:return [dict(x) for x in c.execute('SELECT * FROM bookings WHERE tenant_id=? ORDER BY checkin',(a['tenant_id'],))]
@app.post('/bookings')
def book(v:BookingCreate,a=Depends(actor)):
 if v.checkout<=v.checkin:raise HTTPException(422,'Checkout must be after checkin')
 with db() as c:
  c.execute('BEGIN IMMEDIATE')
  room=c.execute('SELECT id FROM rooms WHERE id=? AND tenant_id=? AND active=1',(v.room_id,a['tenant_id'])).fetchone()
  if not room:raise HTTPException(404,'Room not found')
  overlap=c.execute("SELECT 1 FROM bookings WHERE tenant_id=? AND room_id=? AND status='confirmed' AND checkin<? AND checkout>?",(a['tenant_id'],v.room_id,v.checkout.isoformat(),v.checkin.isoformat())).fetchone()
  if overlap:raise HTTPException(409,'Room unavailable for dates')
  r=c.execute("INSERT INTO bookings(tenant_id,room_id,guest_name,checkin,checkout,nightly_rate,status,created_at) VALUES (?,?,?,?,?,?,'confirmed',?)",(a['tenant_id'],v.room_id,v.guest_name,v.checkin.isoformat(),v.checkout.isoformat(),v.nightly_rate,datetime.utcnow().isoformat()))
  return {'id':r.lastrowid}
@app.post('/bookings/{booking_id}/cancel')
def cancel(booking_id:int,a=Depends(actor)):
 with db() as c:
  r=c.execute("UPDATE bookings SET status='cancelled' WHERE id=? AND tenant_id=? AND status='confirmed'",(booking_id,a['tenant_id']))
  if not r.rowcount:raise HTTPException(404,'Active booking not found')
 return {'cancelled':True}
@app.get('/metrics')
def metrics(day:date=date.today(),a=Depends(actor)):
 d=day.isoformat()
 with db() as c:
  capacity=c.execute('SELECT COUNT(*) FROM rooms WHERE tenant_id=? AND active=1',(a['tenant_id'],)).fetchone()[0]
  x=c.execute("SELECT COUNT(*),COALESCE(SUM(nightly_rate),0) FROM bookings WHERE tenant_id=? AND status='confirmed' AND checkin<=? AND checkout>?",(a['tenant_id'],d,d)).fetchone()
 sold,revenue=x[0],round(x[1],2)
 return {'date':d,'rooms_available':capacity,'rooms_sold':sold,'room_revenue':revenue,'occupancy_pct':round(sold/capacity*100,2) if capacity else None,'adr':round(revenue/sold,2) if sold else None,'revpar':round(revenue/capacity,2) if capacity else None,'trevpar':None,'note':'TRevPAR requires ancillary revenue data'}
@app.get('/forecast')
def forecast(days:int=7,a=Depends(actor)):
 if days<1 or days>90:raise HTTPException(422,'days must be 1..90')
 return [metrics(date.today()+timedelta(days=i),a) for i in range(days)]

# Supplementary commercial revenue modules, tenant scoped.
def init_commercial():
 with db() as c:
  c.executescript("""CREATE TABLE IF NOT EXISTS ancillary(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL REFERENCES tenants(id),day TEXT NOT NULL,category TEXT NOT NULL,amount REAL NOT NULL CHECK(amount>=0));
CREATE TABLE IF NOT EXISTS market_daily(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL REFERENCES tenants(id),day TEXT NOT NULL,market_occupancy REAL NOT NULL CHECK(market_occupancy>0 AND market_occupancy<=100),market_adr REAL NOT NULL CHECK(market_adr>0),UNIQUE(tenant_id,day));
CREATE TABLE IF NOT EXISTS rate_plans(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL REFERENCES tenants(id),name TEXT NOT NULL,segment TEXT NOT NULL,base_rate REAL NOT NULL CHECK(base_rate>=0),active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL,actor_id INTEGER NOT NULL,action TEXT NOT NULL,entity TEXT NOT NULL,entity_id INTEGER,created_at TEXT NOT NULL);""")
init_commercial()
class AncillaryCreate(BaseModel):
 day:date
 category:str=Field(min_length=1,max_length=80)
 amount:float=Field(ge=0)
class MarketCreate(BaseModel):
 day:date
 market_occupancy:float=Field(gt=0,le=100)
 market_adr:float=Field(gt=0)
class RatePlanCreate(BaseModel):
 name:str=Field(min_length=1,max_length=100)
 segment:str=Field(min_length=1,max_length=80)
 base_rate:float=Field(ge=0)
def audit(c,a,action,entity,entity_id):
 c.execute('INSERT INTO audit_log(tenant_id,actor_id,action,entity,entity_id,created_at) VALUES (?,?,?,?,?,?)',(a['tenant_id'],a['id'],action,entity,entity_id,datetime.utcnow().isoformat()))
@app.get('/me')
def me(a=Depends(actor)):
 with db() as c:
  u=c.execute('SELECT email FROM users WHERE id=?',(a['id'],)).fetchone()
  t=c.execute('SELECT name FROM tenants WHERE id=?',(a['tenant_id'],)).fetchone()
 return {'email':u['email'],'role':a['role'],'hotel':t['name'],'tenant_id':a['tenant_id']}
@app.get('/ancillary')
def ancillary(a=Depends(actor)):
 with db() as c:return [dict(x) for x in c.execute('SELECT id,day,category,amount FROM ancillary WHERE tenant_id=? ORDER BY day DESC',(a['tenant_id'],))]
@app.post('/ancillary')
def add_ancillary(v:AncillaryCreate,a=Depends(actor)):
 with db() as c:
  r=c.execute('INSERT INTO ancillary(tenant_id,day,category,amount) VALUES (?,?,?,?)',(a['tenant_id'],v.day.isoformat(),v.category,v.amount));audit(c,a,'create','ancillary',r.lastrowid)
 return {'id':r.lastrowid}
@app.get('/rate-plans')
def rate_plans(a=Depends(actor)):
 with db() as c:return [dict(x) for x in c.execute('SELECT id,name,segment,base_rate,active FROM rate_plans WHERE tenant_id=? ORDER BY name',(a['tenant_id'],))]
@app.post('/rate-plans')
def add_rate_plan(v:RatePlanCreate,a=Depends(actor)):
 if a['role']!='admin':raise HTTPException(403)
 with db() as c:
  r=c.execute('INSERT INTO rate_plans(tenant_id,name,segment,base_rate) VALUES (?,?,?,?)',(a['tenant_id'],v.name,v.segment,v.base_rate));audit(c,a,'create','rate_plan',r.lastrowid)
 return {'id':r.lastrowid}
@app.put('/market')
def put_market(v:MarketCreate,a=Depends(actor)):
 if a['role']!='admin':raise HTTPException(403)
 with db() as c:
  c.execute('INSERT INTO market_daily(tenant_id,day,market_occupancy,market_adr) VALUES (?,?,?,?) ON CONFLICT(tenant_id,day) DO UPDATE SET market_occupancy=excluded.market_occupancy,market_adr=excluded.market_adr',(a['tenant_id'],v.day.isoformat(),v.market_occupancy,v.market_adr));audit(c,a,'upsert','market',None)
 return {'saved':True}
@app.get('/revenue-intelligence')
def revenue_intelligence(day:date=date.today(),a=Depends(actor)):
 m=metrics(day,a);d=day.isoformat()
 with db() as c:
  extra=c.execute('SELECT COALESCE(SUM(amount),0) FROM ancillary WHERE tenant_id=? AND day=?',(a['tenant_id'],d)).fetchone()[0]
  market=c.execute('SELECT market_occupancy,market_adr FROM market_daily WHERE tenant_id=? AND day=?',(a['tenant_id'],d)).fetchone()
 m['ancillary_revenue']=round(extra,2)
 m['total_revenue']=round(m['room_revenue']+extra,2)
 m['trevpar']=round(m['total_revenue']/m['rooms_available'],2) if m['rooms_available'] else None
 if market:
  mo,ma=market['market_occupancy'],market['market_adr'];mr=mo/100*ma
  m['mpi']=round(m['occupancy_pct']/mo*100,2) if m['occupancy_pct'] is not None else None
  m['ari']=round(m['adr']/ma*100,2) if m['adr'] is not None else None
  m['rgi']=round(m['revpar']/mr*100,2) if m['revpar'] is not None else None
 else:m.update(mpi=None,ari=None,rgi=None)
 return m
@app.get('/audit')
def audit_list(a=Depends(actor)):
 if a['role']!='admin':raise HTTPException(403)
 with db() as c:return [dict(x) for x in c.execute('SELECT action,entity,entity_id,created_at FROM audit_log WHERE tenant_id=? ORDER BY id DESC LIMIT 100',(a['tenant_id'],))]
@app.post('/logout')
def logout(authorization:str=Header(default=''),a=Depends(actor)):
 token=authorization.removeprefix('Bearer ').strip()
 with db() as c:c.execute('DELETE FROM sessions WHERE token_hash=? AND user_id=?',(hashlib.sha256(token.encode()).hexdigest(),a['id']))
 return {'logged_out':True}
WEB=Path(__file__).resolve().parents[2]/'apps'/'web'/'index.html'
@app.get('/',include_in_schema=False)
def home():return FileResponse(WEB)
