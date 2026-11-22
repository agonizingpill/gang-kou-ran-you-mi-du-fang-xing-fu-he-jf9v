"""V4 储罐分层与按层放行 — 端到端验证（SQLite 内存级运行真实后端代码）。"""
import os,sys,json
os.environ['DATABASE_URL']='sqlite:////tmp/layer-test.db'
os.environ['SEED_DEMO']='false'
os.environ['REDIS_URL']='redis://localhost:6379/0'
sys.path.insert(0,'/workspace/backend')
if os.path.exists('/tmp/layer-test.db'):os.remove('/tmp/layer-test.db')
from datetime import datetime,timedelta,timezone
from scripts.seed_demo import seed
seed()
from fastapi.testclient import TestClient
from src.main import app
from src.database import Session
from src.models import Tank,FuelSample
from src.layer_models import TankLayer,TransferLayerDraw
from sqlalchemy import select
c=TestClient(app)
FAIL=[]
def check(name,cond,detail=''):
    print(('PASS' if cond else 'FAIL'),name,('| '+str(detail)) if detail else '')
    if not cond:FAIL.append(name)
def login(email):
    r=c.post('/auth/login',json={'email':email,'password':'Harbor2026!'})
    assert r.status_code==200,r.text
    return{'Authorization':'Bearer '+r.json()['token']}
admin=login('admin@chenggang.local');chemist=login('chemist@chenggang.local');viewer=login('viewer@chenggang.local')
def strat(code):
    r=c.get('/tank-stratifications',headers=admin);assert r.status_code==200
    return next(x for x in r.json() if x['tank_code']==code)
def tank(code):
    r=c.get('/tanks',headers=admin);return next(x for x in r.json() if x['code']==code)
def sample(code):
    r=c.get('/samples',headers=admin);return next(x for x in r.json() if x['code']==code)
WN=0
def window_dates():
    global WN;WN+=1
    a=datetime.now(timezone.utc)+timedelta(days=1,hours=3*WN);b=a+timedelta(hours=2)
    return a.isoformat(),b.isoformat()
LINE=BER=None
def prep(tid):
    global LINE,BER
    if LINE is None:
        LINE=next(x['id'] for x in c.get('/fuel-lines',headers=admin).json() if x['code']=='FL-V01')
        BER=next(x['id'] for x in c.get('/berths',headers=admin).json() if x['code']=='BT-01')
    p=c.post('/line-permits',json={'transfer_id':tid,'line_id':LINE,'flush_liters':200,'clean_grade':'VLSFO'},headers=chemist);assert p.status_code==200,p.text
    pid=p.json()['id'];r=c.post(f'/line-permits/{pid}/approve',headers=admin);assert r.status_code==200,r.text
    a,b=window_dates()
    w=c.post('/vessel-windows',json={'transfer_id':tid,'berth_id':BER,'starts_at':a,'ends_at':b,'draft':6},headers=chemist);assert w.status_code==200,w.text
    r=c.post(f"/vessel-windows/{w.json()['id']}/confirm",headers=admin);assert r.status_code==200,r.text
    return pid
def complete(pid,note='输油完工管线冲洗合格已交接'):
    r=c.post(f'/line-permits/{pid}/complete',json={'completion_note':note},headers=admin);assert r.status_code==200,r.text

print('== A. 分层登记与可抽量（缺样/异常层上方合格油留罐）==')
st=strat('TK-08')
check('A1 TK-08分层在册',st['state']=='active')
check('A2 可抽量=罐底连续合格层12000',st['drawable_liters']==12000.0,st['drawable_liters'])
check('A3 层状态[合格,异常,合格]',[l['layer_state'] for l in st['layers']]==['qualified','anomaly','qualified'])
check('A4 顶层合格但被异常层阻断不计入可抽',st['layers'][2]['layer_state']=='qualified' and st['drawable_liters']==12000.0)
check('A5 TK-06未登记分层',strat('TK-06')['state']=='none')

print('== B. 登记校验 ==')
tk6=tank('TK-06');tkm=tank('TK-M01');fs_mgo=sample('FS-MGO-01');fs_a=sample('FS-LAYER-08-A')
r=c.post(f"/tanks/{tkm['id']}/stratification",json={'layers':[{'liters':1,'sample_id':None}]},headers=chemist)
check('B1 合计≠罐存量被拒',r.status_code==409 and '不一致' in r.json()['detail'],r.json().get('detail'))
r=c.post(f"/tanks/{tkm['id']}/stratification",json={'layers':[{'liters':35000,'sample_id':fs_a['id']}]},headers=chemist)
check('B2 他罐油样被拒',r.status_code==409 and '本储罐' in r.json()['detail'])
with Session() as s:ref_id=s.scalar(select(FuelSample.id).where(FuelSample.reference==True,FuelSample.tank_id==tkm['id']).limit(1))
r=c.post(f"/tanks/{tkm['id']}/stratification",json={'layers':[{'liters':35000,'sample_id':ref_id}]},headers=chemist)
check('B3 参考样被拒',r.status_code==409 and '参考样' in r.json()['detail'])
r=c.post(f"/tanks/{tkm['id']}/stratification",json={'layers':[{'liters':20000,'sample_id':fs_mgo['id']},{'liters':15000,'sample_id':fs_mgo['id']}]},headers=chemist)
check('B4 同样品多层被拒',r.status_code==409 and '重复' in r.json()['detail'])
r=c.post(f"/tanks/{tkm['id']}/stratification",json={'layers':[{'liters':35000,'sample_id':fs_mgo['id']}]},headers=viewer)
check('B5 观察员无权登记',r.status_code==403)
r=c.post(f"/tanks/{tkm['id']}/stratification",json={'layers':[{'liters':35000,'sample_id':fs_mgo['id']}]},headers=chemist)
check('B6 化验员登记成功',r.status_code==200 and r.json()['state']=='active')
check('B7 待判定层可抽为0',r.json()['drawable_liters']==0.0 and r.json()['layers'][0]['layer_state']=='pending')
r=c.get('/tank-stratifications',headers=viewer);check('B8 观察员只读可查',r.status_code==200)

print('== C. 放行按层扣量+留痕+重试幂等 ==')
r=c.post('/transfers',json={'code':'TR-L1','sample_id':fs_a['id'],'liters':8000,'vessel':'澄海31 / CG-L1'},headers=chemist);assert r.status_code==200,r.text
t1=r.json()['id'];pid=prep(t1)
r=c.post(f'/transfers/{t1}/release',headers=admin)
check('C1 放行成功',r.status_code==200 and r.json()['status']=='released',r.json().get('detail'))
d=r.json()['layer_draws']
check('C2 抽层依据1层8000L',len(d)==1 and d[0]['liters']==8000.0 and d[0]['sample_code']=='FS-LAYER-08-A',d)
check('C3 抽层快照前后量',d[0]['layer_liters_before']==12000.0 and d[0]['layer_liters_after']==4000.0)
check('C4 罐量原子扣减',tank('TK-08')['liters']==12000.0)
st=strat('TK-08');check('C5 层余量与可抽重算',st['layers'][0]['liters']==4000.0 and st['drawable_liters']==4000.0)
r=c.post(f'/transfers/{t1}/release',headers=admin)
check('C6 重试被拒不重复扣量',r.status_code==409 and tank('TK-08')['liters']==12000.0 and strat('TK-08')['layers'][0]['liters']==4000.0)
with Session() as s:check('C7 抽层记录仍1条',len(s.scalars(select(TransferLayerDraw).where(TransferLayerDraw.transfer_id==t1)).all())==1)
complete(pid)

print('== D. 跨待查/异常层整单退回 ==')
r=c.post('/transfers',json={'code':'TR-L2','sample_id':fs_a['id'],'liters':5000,'vessel':'澄海32 / CG-L2'},headers=chemist);t2=r.json()['id'];pid2=prep(t2)
r=c.post(f'/transfers/{t2}/release',headers=admin)
check('D1 超可抽量整单退回',r.status_code==409 and '整单退回' in r.json()['detail'],r.json().get('detail'))
check('D2 退回后罐量层量未动',tank('TK-08')['liters']==12000.0 and strat('TK-08')['layers'][0]['liters']==4000.0)
check('D3 退回单仍待放行',next(x for x in c.get('/transfers',headers=admin).json() if x['id']==t2)['status']=='requested')
with Session() as s:check('D4 无部分扣层记录',len(s.scalars(select(TransferLayerDraw).where(TransferLayerDraw.transfer_id==t2)).all())==0)

print('== E. 已扣层量重算可抽（并发语义的串行验证）==')
r=c.post('/transfers',json={'code':'TR-L3','sample_id':fs_a['id'],'liters':3000,'vessel':'澄海33 / CG-L3'},headers=chemist);t3=r.json()['id'];pid3=prep(t3)
r=c.post(f'/transfers/{t3}/release',headers=admin);check('E1 第二单放行成功',r.status_code==200,r.json().get('detail'))
complete(pid3)
r=c.post('/transfers',json={'code':'TR-L4','sample_id':fs_a['id'],'liters':3000,'vessel':'澄海34 / CG-L4'},headers=chemist);t4=r.json()['id'];pid4=prep(t4)
r=c.post(f'/transfers/{t4}/release',headers=admin)
check('E2 按已扣层量重算后超额被拒',r.status_code==409 and '可抽1000' in r.json()['detail'],r.json().get('detail'))
check('E3 罐量9000层余1000',tank('TK-08')['liters']==9000.0 and strat('TK-08')['layers'][0]['liters']==1000.0)

print('== F. 补油作废旧分层，须重新分层取样 ==')
r=c.post('/tank-receipts',json={'code':'RC-L1','tank_id':tank('TK-08')['id'],'grade':'VLSFO','liters':2000,'density_15':985,'viscosity':130,'sulfur':.35},headers=chemist);rc=r.json()['id']
r=c.post(f'/tank-receipts/{rc}/inspect',headers=chemist);assert r.status_code==200,r.text
r=c.post(f'/tank-receipts/{rc}/receive',headers=admin)
check('F1 补油入罐成功',r.status_code==200 and r.json()['state']=='received',r.json().get('detail'))
check('F2 入罐快照记录作废层数',r.json()['receipt_snapshot']['stratification_invalidated_layers']==3)
check('F3 分层状态stale',strat('TK-08')['state']=='stale')
r=c.post(f'/transfers/{t4}/release',headers=admin)
check('F4 补油后未重分层放行被拦',r.status_code==409 and '重新分层' in r.json()['detail'],r.json().get('detail'))
check('F5 罐量11000未动',tank('TK-08')['liters']==11000.0)
fs_b=sample('FS-LAYER-08-B')
r=c.post(f"/tanks/{tank('TK-08')['id']}/stratification",json={'layers':[{'liters':6000,'sample_id':fs_a['id']},{'liters':3000,'sample_id':fs_b['id']},{'liters':2000,'sample_id':None}]},headers=chemist)
check('F6 补油后重新分层成功',r.status_code==200 and r.json()['state']=='active',r.json() if r.status_code!=200 else '')
check('F7 异常层阻断可抽6000',r.json()['drawable_liters']==6000.0)
r=c.post(f'/transfers/{t4}/release',headers=admin)
check('F8 重分层后滞留单可放行',r.status_code==200,r.json().get('detail'))
complete(pid4)

print('== G. 复检翻层，可抽量动态跟随 ==')
r=c.put(f"/samples/{fs_b['id']}/retest",json={'density':980,'note':'重新取样排气核温后密度合格'},headers=chemist)
check('G1 异常样复检合格',r.status_code==200 and r.json()['status']=='retested',r.json().get('detail'))
st=strat('TK-08')
check('G2 中层翻合格可抽=3000+3000',st['layers'][1]['layer_state']=='qualified' and st['drawable_liters']==6000.0,st['drawable_liters'])
check('G3 顶层缺样仍阻断',st['layers'][2]['layer_state']=='pending')

print('== H. 跨多层抽取与逐层依据 ==')
r=c.post('/transfers',json={'code':'TR-L5','sample_id':fs_a['id'],'liters':5500,'vessel':'澄海35 / CG-L5'},headers=chemist);t5=r.json()['id'];pid5=prep(t5)
r=c.post(f'/transfers/{t5}/release',headers=admin)
check('H1 跨层放行成功',r.status_code==200,r.json().get('detail'))
d=r.json()['layer_draws']
check('H2 两层抽取3000+2500',len(d)==2 and d[0]['liters']==3000.0 and d[1]['liters']==2500.0,d)
check('H3 各层留样依据',[x['sample_code'] for x in d]==['FS-LAYER-08-A','FS-LAYER-08-B'])
st=strat('TK-08');check('H4 层余0/500/2000可抽500',[l['liters'] for l in st['layers']]==[0.0,500.0,2000.0] and st['drawable_liters']==500.0)
complete(pid5)
r=c.post('/transfers',json={'code':'TR-L6','sample_id':fs_a['id'],'liters':1000,'vessel':'澄海36 / CG-L6'},headers=chemist);t6=r.json()['id'];prep(t6)
r=c.post(f'/transfers/{t6}/release',headers=admin)
check('H5 缺样层上方合格油留罐(1000>500退回)',r.status_code==409 and '整单退回' in r.json()['detail'])

print('== I. 对账快照留存抽层依据 ==')
r=c.post('/loading-reconciliations',json={'transfer_id':t5,'meter_before':0,'meter_after':5500,'vessel_received_liters':5500},headers=chemist)
check('I1 对账登记matched',r.status_code==200 and r.json()['state']=='matched',r.json().get('detail'))
check('I2 对账快照含抽层依据',len(r.json()['transfer_snapshot']['layer_draws'])==2)

print('== J. 未分层罐保持原流程 ==')
with Session.begin() as s:
    x=s.scalar(select(FuelSample).where(FuelSample.code=='FS-20261117-01'))
    from src.density_model import compare
    x.log_density,x.threshold,passed,ev=compare(s,x);x.status='qualified' if passed else 'anomaly';x.evidence=json.dumps(ev,ensure_ascii=False)
fs1=sample('FS-20261117-01');check('J0 KDE比对合格(worker同逻辑)',fs1['status']=='qualified')
r=c.post('/transfers',json={'code':'TR-L7','sample_id':fs1['id'],'liters':1000,'vessel':'澄海37 / CG-L7'},headers=chemist);t7=r.json()['id'];pid7=prep(t7)
r=c.post(f'/transfers/{t7}/release',headers=admin)
check('J1 未分层罐放行成功',r.status_code==200 and r.json()['layer_draws']==[],r.json().get('detail'))
complete(pid7)
r=c.get('/tank-receipts',headers=admin);rc0=next(x for x in r.json() if x['code']=='RC-DEMO-17')
r=c.post(f"/tank-receipts/{rc0['id']}/inspect",headers=chemist);r=c.post(f"/tank-receipts/{rc0['id']}/receive",headers=admin)
check('J2 未分层罐补油不作废分层',r.status_code==200 and r.json()['receipt_snapshot']['stratification_invalidated_layers']==0)
check('J3 TK-06仍none',strat('TK-06')['state']=='none')

print('== K. seed幂等 ==')
with Session() as s:n1=len(s.scalars(select(TankLayer)).all())
seed();seed()
with Session() as s:
    n2=len(s.scalars(select(TankLayer)).all());nd=len(s.scalars(select(TransferLayerDraw)).all())
check('K1 重跑seed不重复建层',n1==n2,(n1,n2))
check('K2 抽层证据未被seed改动',nd==5,nd)

print()
print('FAILED:',FAIL if FAIL else '无 — 全部通过')
sys.exit(1 if FAIL else 0)
