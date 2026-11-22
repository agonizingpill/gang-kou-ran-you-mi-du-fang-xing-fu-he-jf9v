from fastapi import APIRouter,Depends
from .database import Session
from .security import current,allow
from .layer_schemas import StratificationIn
from . import layer_service as svc
router=APIRouter()
@router.get('/tank-stratifications')
def stratifications(u=Depends(current)):
    with Session() as s:return svc.all_stratifications(s)
@router.post('/tanks/{tank_id}/stratification')
def register(tank_id:int,p:StratificationIn,u=Depends(current)):
    allow(u,'admin','chemist')
    with Session.begin() as s:return svc.register(s,tank_id,p,u)
