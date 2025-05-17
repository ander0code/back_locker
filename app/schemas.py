from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

# Schemas for LockerUser
class LockerUserBase(BaseModel):
    email: EmailStr

class LockerUserCreate(LockerUserBase):
    pass

class LockerUser(LockerUserBase):
    id: int
    pin: Optional[str] = None
    pin_created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}  # Updated for Pydantic v2

# Schemas for Locker
class LockerBase(BaseModel):
    status: str = "disponible"

class LockerCreate(LockerBase):
    pass

class Locker(LockerBase):
    id: int
    updated_at: datetime
    assigned_user_id: Optional[int] = None

    model_config = {"from_attributes": True}  # Updated for Pydantic v2

# Schemas for LockerHistory
class LockerHistoryBase(BaseModel):
    locker_id: int
    action: str

class LockerHistoryCreate(LockerHistoryBase):
    pass

class LockerHistory(LockerHistoryBase):
    id: int
    timestamp: datetime

    model_config = {"from_attributes": True}  # Updated from orm_mode in pydantic v2

# Schemas for LockerAlert
class LockerAlertBase(BaseModel):
    locker_id: int
    description: str

class LockerAlertCreate(LockerAlertBase):
    pass

class LockerAlert(LockerAlertBase):
    id: int
    timestamp: datetime

    model_config = {"from_attributes": True}  # Updated from orm_mode in pydantic v2

# API Request/Response schemas
class LockerUse(BaseModel):
    email: EmailStr

class PinVerification(BaseModel):
    pin: str

class LockerMovement(BaseModel):
    locker_id: int
    has_object: bool

class LockerStatus(BaseModel):
    id: int
    status: str
    updated_at: datetime