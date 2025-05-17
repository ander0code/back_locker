from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class LockerUser(Base):
    __tablename__ = "locker_users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    pin = Column(String)  # PIN temporal, hash opcional
    pin_created_at = Column(DateTime)
    
    # Relación con locker a través de assigned_user_id
    assigned_locker = relationship("Locker", back_populates="assigned_user", uselist=False)

class Locker(Base):
    __tablename__ = "lockers"
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="disponible")  # disponible, esperando_objeto, ocupado
    updated_at = Column(DateTime, default=datetime.utcnow)
    assigned_user_id = Column(Integer, ForeignKey("locker_users.id"), nullable=True)
    
    # Relación con usuario
    assigned_user = relationship("LockerUser", foreign_keys=[assigned_user_id], back_populates="assigned_locker")
    
    # Historiales y alertas
    history = relationship("LockerHistory", back_populates="locker")
    alerts = relationship("LockerAlert", back_populates="locker")

class LockerHistory(Base):
    __tablename__ = "locker_history"
    id = Column(Integer, primary_key=True)
    locker_id = Column(Integer, ForeignKey("lockers.id"))
    action = Column(String)  # abierto, cerrado, intento fallido, etc.
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones
    locker = relationship("Locker", back_populates="history")

class LockerAlert(Base):
    __tablename__ = "locker_alerts"
    id = Column(Integer, primary_key=True)
    locker_id = Column(Integer, ForeignKey("lockers.id"))
    description = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones
    locker = relationship("Locker", back_populates="alerts")