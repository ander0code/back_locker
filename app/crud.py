from sqlalchemy.orm import Session
import random
import string
from datetime import datetime, timedelta
from app import models
# from app.utils.mailer import send_pin_email

def get_available_locker(db: Session):
    return db.query(models.Locker).filter(models.Locker.status == "disponible").first()

def get_locker(db: Session, locker_id: int):
    return db.query(models.Locker).filter(models.Locker.id == locker_id).first()

def get_locker_by_user_id(db: Session, user_id: int):
    return db.query(models.Locker).filter(models.Locker.assigned_user_id == user_id).first()

def get_user_by_email(db: Session, email: str):
    return db.query(models.LockerUser).filter(models.LockerUser.email == email).first()

def get_user_by_pin(db: Session, pin: str):
    return db.query(models.LockerUser).filter(models.LockerUser.pin == pin).first()

def create_user(db: Session, email: str):
    db_user = models.LockerUser(email=email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def generate_pin():
    # Generate a 6-digit PIN
    return ''.join(random.choice(string.digits) for _ in range(6))

def assign_pin_to_user(db: Session, user_id: int, pin: str):
    db_user = db.query(models.LockerUser).filter(models.LockerUser.id == user_id).first()
    db_user.pin = pin
    db_user.pin_created_at = datetime.utcnow()
    db.commit()
    db.refresh(db_user)
    return db_user

def assign_locker_to_user(db: Session, locker_id: int, user_id: int):
    """Asigna un locker a un usuario y establece la relación correctamente"""
    # Obtener el locker y el usuario
    db_locker = db.query(models.Locker).filter(models.Locker.id == locker_id).first()
    if not db_locker:
        return None
        
    db_user = db.query(models.LockerUser).filter(models.LockerUser.id == user_id).first()
    if not db_user:
        return None
    
    # Establecer la relación de manera explícita
    db_locker.assigned_user_id = user_id  
    db_locker.status = "ocupado"  
    db_locker.updated_at = datetime.utcnow()
    
    # Imprimir información para depuración
    print(f"Asignando locker {locker_id} al usuario {user_id} ({db_user.email})")
    
    # Hacer commit y refrescar
    db.commit()
    db.flush()  # Asegura que se escriben los cambios
    
    # Verificar explícitamente el estado actual en la base de datos
    updated_locker = db.query(models.Locker).filter(models.Locker.id == locker_id).first()
    print(f"Verificación: locker_id={updated_locker.id}, assigned_user_id={updated_locker.assigned_user_id}, status={updated_locker.status}")
    
    return updated_locker

def update_locker_status(db: Session, locker_id: int, status: str):
    db_locker = db.query(models.Locker).filter(models.Locker.id == locker_id).first()
    db_locker.status = status
    db_locker.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_locker)
    return db_locker

def create_locker_history(db: Session, locker_id: int, action: str):
    db_history = models.LockerHistory(locker_id=locker_id, action=action)
    db.add(db_history)
    db.commit()
    db.refresh(db_history)
    return db_history

def create_locker_alert(db: Session, locker_id: int, description: str):
    db_alert = models.LockerAlert(locker_id=locker_id, description=description)
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert

def get_locker_history(db: Session, locker_id: int, skip: int = 0, limit: int = 100):
    return db.query(models.LockerHistory).filter(
        models.LockerHistory.locker_id == locker_id
    ).offset(skip).limit(limit).all()

def get_locker_alerts(db: Session, locker_id: int, skip: int = 0, limit: int = 100):
    return db.query(models.LockerAlert).filter(
        models.LockerAlert.locker_id == locker_id
    ).offset(skip).limit(limit).all()

def release_locker(db: Session, locker_id: int):
    """Libera un locker, lo marca como disponible y lo desasocia del usuario"""
    # Obtener el locker
    db_locker = db.query(models.Locker).filter(models.Locker.id == locker_id).first()
    if not db_locker:
        return None
    
    # Si hay un usuario asignado, desasociarlo
    if db_locker.assigned_user_id:
        # Buscar el usuario asignado
        db_user = db.query(models.LockerUser).filter(models.LockerUser.id == db_locker.assigned_user_id).first()
        if db_user:
            # Limpiar el PIN 
            db_user.pin = None
            db_user.pin_created_at = None
            db.commit()
    
    # Actualizar el locker
    db_locker.status = "disponible"
    db_locker.assigned_user_id = None
    db_locker.updated_at = datetime.utcnow()
    
    # Guardar cambios
    db.commit()
    db.refresh(db_locker)
    
    return db_locker

def is_pin_valid(db: Session, pin: str) -> bool:
    """Verifica si un PIN es válido y no ha expirado"""
    user = get_user_by_pin(db, pin)
    if not user or not user.pin_created_at:
        return False
    
    # Tiempo de expiración: 15 minutos desde la creación
    # Convertir todo a naive (sin timezone) para comparación segura
    pin_created_at = user.pin_created_at
    if pin_created_at.tzinfo:
        pin_created_at = pin_created_at.replace(tzinfo=None)
    
    expiration_time = pin_created_at + timedelta(hours=2, minutes=30)   
    current_time = datetime.utcnow()
    
    # Comparar fechas sin timezone para evitar el error
    return current_time <= expiration_time