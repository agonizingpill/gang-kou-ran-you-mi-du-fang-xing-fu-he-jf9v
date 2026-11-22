"""Tank stratification layers and per-release layer draw evidence."""
from decimal import Decimal
from sqlalchemy import String,Numeric,ForeignKey,JSON,Integer,Boolean,CheckConstraint,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .database import Base
class TankLayer(Base):
    __tablename__='tank_layers'
    __table_args__=(CheckConstraint('seq > 0'),CheckConstraint('liters >= 0'),CheckConstraint('initial_liters > 0'),CheckConstraint("supersede_reason IN ('','resurvey','receipt')"),UniqueConstraint('tank_id','survey','seq'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    tank_id:Mapped[int]=mapped_column(ForeignKey('tanks.id'))
    survey:Mapped[int]=mapped_column(Integer)
    seq:Mapped[int]=mapped_column(Integer)
    liters:Mapped[Decimal]=mapped_column(Numeric(14,3))
    initial_liters:Mapped[Decimal]=mapped_column(Numeric(14,3))
    sample_id:Mapped[int|None]=mapped_column(ForeignKey('fuel_samples.id'),nullable=True)
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    supersede_reason:Mapped[str]=mapped_column(String(20),default='')
    registered_by:Mapped[str]=mapped_column(String(120))
    registered_at:Mapped[str]=mapped_column(String(40))
class TransferLayerDraw(Base):
    __tablename__='transfer_layer_draws'
    __table_args__=(CheckConstraint('liters > 0'),UniqueConstraint('transfer_id','layer_id'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    transfer_id:Mapped[int]=mapped_column(ForeignKey('transfers.id'))
    layer_id:Mapped[int]=mapped_column(ForeignKey('tank_layers.id'))
    layer_seq:Mapped[int]=mapped_column(Integer)
    liters:Mapped[Decimal]=mapped_column(Numeric(14,3))
    snapshot:Mapped[dict]=mapped_column(JSON)
