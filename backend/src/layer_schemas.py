from decimal import Decimal
from pydantic import BaseModel,Field,ConfigDict
class CleanInput(BaseModel):model_config=ConfigDict(str_strip_whitespace=True)
class LayerIn(CleanInput):
    liters:Decimal=Field(gt=0,le=100000000,max_digits=14,decimal_places=3)
    sample_id:int|None=Field(default=None,gt=0)
class StratificationIn(CleanInput):
    layers:list[LayerIn]=Field(min_length=1,max_length=20)
