from decimal import Decimal
from datetime import datetime,timezone
from fastapi import HTTPException
from sqlalchemy import select,func
from .models import Tank,FuelSample
from .layer_models import TankLayer,TransferLayerDraw
from .transfer_service import obj,get,audit
from .density_model import within_spec

def now():return datetime.now(timezone.utc).isoformat()
def layer_state(sample,grade):
    # 缺样/待判定/计算失败均为待查；异常与复检未过为异常；合格须同时满足KDE结论与等级规格
    if not sample:return 'pending'
    density=sample.retest_density if sample.retest_density is not None else sample.density_15
    if sample.status in('qualified','retested')and within_spec(grade,density,sample.viscosity,sample.sulfur):return 'qualified'
    if sample.status in('received','queued','failed'):return 'pending'
    return 'anomaly'
def active_layers(s,tank_id):
    layers=s.scalars(select(TankLayer).where(TankLayer.tank_id==tank_id,TankLayer.active==True).order_by(TankLayer.seq).execution_options(populate_existing=True)).all()
    if layers:return 'active',layers
    stale=s.scalar(select(TankLayer.id).where(TankLayer.tank_id==tank_id,TankLayer.supersede_reason=='receipt').limit(1))
    return('stale',[])if stale else('none',[])
def layer_view(s,x,grade):
    sample=s.get(FuelSample,x.sample_id)if x.sample_id else None
    density=(sample.retest_density if sample.retest_density is not None else sample.density_15)if sample else None
    return{**obj(x),'sample_code':sample.code if sample else '','sample_status':sample.status if sample else '','layer_state':layer_state(sample,grade),'density_15':float(density)if density is not None else None}
def stratification(s,tank_id):
    t=get(s,Tank,tank_id);state,layers=active_layers(s,tank_id)
    drawable=Decimal('0');blocked=False;views=[]
    for ly in layers:
        v=layer_view(s,ly,t.grade)
        if v['layer_state']=='qualified'and not blocked:drawable+=ly.liters
        else:blocked=True
        views.append(v)
    return{'tank_id':t.id,'tank_code':t.code,'grade':t.grade,'state':state,'tank_liters':float(t.liters),'drawable_liters':float(drawable),'layers':views}
def all_stratifications(s):return[stratification(s,t.id)for t in s.scalars(select(Tank).order_by(Tank.id))]
def register(s,tank_id,data,u):
    t=get(s,Tank,tank_id,True)
    total=sum((l.liters for l in data.layers),Decimal('0'))
    if total!=t.liters:raise HTTPException(409,f'分层油量合计{total}L与罐内当前存量{t.liters}L不一致，须按罐底到罐顶覆盖全部存油')
    seen=set()
    for l in data.layers:
        if not l.sample_id:continue
        if l.sample_id in seen:raise HTTPException(409,'同一油样不能重复登记到多个层')
        seen.add(l.sample_id);x=get(s,FuelSample,l.sample_id)
        if x.tank_id!=t.id:raise HTTPException(409,'分层油样必须取自本储罐')
        if x.reference:raise HTTPException(409,'等级参考样不能作为分层油样')
    old=s.scalars(select(TankLayer).where(TankLayer.tank_id==t.id,TankLayer.active==True).with_for_update()).all()
    for o in old:o.active=False;o.supersede_reason='resurvey'
    survey=(s.scalar(select(func.max(TankLayer.survey)).where(TankLayer.tank_id==t.id))or 0)+1
    for i,l in enumerate(data.layers,1):s.add(TankLayer(tank_id=t.id,survey=survey,seq=i,liters=l.liters,initial_liters=l.liters,sample_id=l.sample_id,active=True,supersede_reason='',registered_by=u['email'],registered_at=now()))
    audit(s,u,'stratification_registered',f'{t.code}:第{survey}次分层共{len(data.layers)}层');s.flush();return stratification(s,t.id)
def deduct_for_release(s,t,tr,u):
    # 调用处已锁Transfer与Tank；分层扣量与签放在同一事务生效，重试被状态检查拦截不重复扣量
    state,layers=active_layers(s,t.id)
    if state=='stale':raise HTTPException(409,'补油入罐后原分层已作废，须重新分层取样登记再放行')
    if not layers:return
    drawable=Decimal('0');qualified=[]
    for ly in layers:
        if layer_state(s.get(FuelSample,ly.sample_id)if ly.sample_id else None,t.grade)!='qualified':break
        qualified.append(ly);drawable+=ly.liters
    if tr.liters>drawable:raise HTTPException(409,f'罐底连续合格层可抽{drawable}L，调拨量触及缺样或异常层，整单退回未扣量')
    remaining=tr.liters
    for ly in qualified:
        if remaining<=0:break
        take=ly.liters if ly.liters<=remaining else remaining;before=ly.liters
        ly.liters-=take;remaining-=take
        sample=s.get(FuelSample,ly.sample_id)if ly.sample_id else None
        density=(sample.retest_density if sample.retest_density is not None else sample.density_15)if sample else None
        s.add(TransferLayerDraw(transfer_id=tr.id,layer_id=ly.id,layer_seq=ly.seq,liters=take,snapshot={'tank_code':t.code,'grade':t.grade,'survey':ly.survey,'layer_seq':ly.seq,'drawn_liters':float(take),'layer_liters_before':float(before),'layer_liters_after':float(ly.liters),'layer_initial_liters':float(ly.initial_liters),'sample_code':sample.code if sample else '','sample_status':sample.status if sample else '','density_15':float(density)if density is not None else None,'viscosity':float(sample.viscosity)if sample else None,'sulfur':float(sample.sulfur)if sample else None,'at':now()}))
    audit(s,u,'layer_deducted',f'{tr.code}:罐底起按层抽{tr.liters}L')
def invalidate_for_receipt(s,tank_id):
    layers=s.scalars(select(TankLayer).where(TankLayer.tank_id==tank_id,TankLayer.active==True).with_for_update()).all()
    for ly in layers:ly.active=False;ly.supersede_reason='receipt'
    return len(layers)
def draws_for(s,transfer_id):
    return[{**d.snapshot,'layer_seq':d.layer_seq,'liters':float(d.liters)}for d in s.scalars(select(TransferLayerDraw).where(TransferLayerDraw.transfer_id==transfer_id).order_by(TransferLayerDraw.layer_seq))]
