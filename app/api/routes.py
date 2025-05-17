from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import requests

from app import crud, schemas, models
from app.database import get_db
from app.utils.mailer import send_pin_email
from app.core.config import settings

router = APIRouter(prefix="/api")

@router.post("/use", response_model=schemas.Locker)
def use_locker(locker_use: schemas.LockerUse, db: Session = Depends(get_db)):
    # Encontrar un locker disponible
    available_locker = crud.get_available_locker(db)
    if not available_locker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                           detail="No hay lockers disponibles")
    
    # Verificar si el usuario existe, crear si no
    user = crud.get_user_by_email(db, locker_use.email)
    if not user:
        user = crud.create_user(db, locker_use.email)
    
    # Generar y asignar PIN
    pin = crud.generate_pin()
    user = crud.assign_pin_to_user(db, user.id, pin)
    
    # Mostrar información para depuración
    print(f"Asignando locker {available_locker.id} al usuario {user.id} con email {user.email}")
    
    # Asignar locker al usuario (ahora cambia a estado "ocupado" directamente)
    locker = crud.assign_locker_to_user(db, available_locker.id, user.id)
    
    # Verificar que la asignación se hizo correctamente
    print(f"Resultado: locker_id={locker.id}, assigned_user_id={locker.assigned_user_id}, status={locker.status}")
    
    # Enviar PIN por correo electrónico
    send_pin_email(user.email, pin)
    
    # Registrar la acción
    crud.create_locker_history(db, locker.id, "locker_asignado")
    
    # Registrar automáticamente que se ha colocado un objeto (equivalente a notifyBackend)
    # Esto simula la respuesta que normalmente enviaría el ESP32
    locker = crud.update_locker_status(db, locker.id, "ocupado")
    crud.create_locker_history(db, locker.id, "objeto_colocado")
    print(f"Registrado automáticamente que hay un objeto en el locker {locker.id}")
    
    # Notificar al ESP32 para abrir el locker en modo "store"
    try:
        esp32_url = f"http://{settings.ESP32_IP}/actuate"
        print(f"Intentando comunicarse con ESP32 en: {esp32_url}")
        
        response = requests.post(
            esp32_url,
            json={"open": True, "mode": "store"},
            timeout=5
        )
        
        print(f"Respuesta del ESP32: {response.status_code} - {response.text}")
        
        if response.status_code != 200:
            # Registrar respuesta no exitosa
            crud.create_locker_alert(db, locker.id, f"ESP32 respondió con código {response.status_code}: {response.text}")
    except Exception as e:
        # Registrar error pero continuar con el proceso
        error_message = f"Error al comunicarse con ESP32: {str(e)}"
        print(error_message)
        crud.create_locker_alert(db, locker.id, error_message)
    
    return locker

@router.post("/unlock", response_model=schemas.Locker)
def unlock_locker(pin_verification: schemas.PinVerification, db: Session = Depends(get_db)):
    """
    Endpoint para desbloquear un locker usando un PIN.
    Este endpoint también simula el retiro del objeto y libera el locker.
    """
    print(f"Recibida solicitud de desbloqueo con PIN: {pin_verification.pin}")
    
    try:
        # Validar PIN
        if not crud.is_pin_valid(db, pin_verification.pin):
            # Registrar intento fallido
            print(f"PIN inválido: {pin_verification.pin}")
            user = crud.get_user_by_pin(db, pin_verification.pin)
            if user:
                assigned_locker = crud.get_locker_by_user_id(db, user.id)
                if assigned_locker:
                    crud.create_locker_history(db, assigned_locker.id, "intento_fallido")
                
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="PIN inválido o expirado")
        
        # Obtener usuario y locker
        user = crud.get_user_by_pin(db, pin_verification.pin)
        print(f"Usuario encontrado: {user.id if user else 'None'}")
        
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Usuario no encontrado")
        
        # Buscar el locker asignado a este usuario
        # Uso get_locker_by_user_id en lugar de get_locker_by_user según el mensaje de error
        locker = crud.get_locker_by_user_id(db, user.id)
        print(f"Locker encontrado: {locker.id if locker else 'None'}")
        
        if not locker:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="No hay locker asignado a este usuario")
        
        # Registrar desbloqueo exitoso
        crud.create_locker_history(db, locker.id, "locker_abierto")
        print(f"Desbloqueo exitoso registrado para locker {locker.id}")
        
        # Notificar al ESP32 para abrir el locker en modo "retrieve"
        try:
            # Verificar que settings.ESP32_IP está definido
            if not hasattr(settings, 'ESP32_IP'):
                print("ADVERTENCIA: settings.ESP32_IP no está definido, usando dirección por defecto")
                esp32_ip = "192.168.100.47"  # IP por defecto
            else:
                esp32_ip = settings.ESP32_IP
                
            esp32_url = f"http://{esp32_ip}/actuate"
            print(f"Intentando comunicarse con ESP32 en: {esp32_url} para retrieve")
            
            response = requests.post(
                esp32_url,
                json={"open": True, "mode": "retrieve"},
                timeout=5
            )
            
            print(f"Respuesta del ESP32: {response.status_code} - {response.text}")
            
            if response.status_code != 200:
                # Registrar respuesta no exitosa
                crud.create_locker_alert(db, locker.id, f"ESP32 respondió con código {response.status_code}: {response.text}")
            else:
                # Simular la notificación de objeto retirado que normalmente enviaría el ESP32
                print(f"Simulando retiro de objeto del locker {locker.id}")
                crud.create_locker_history(db, locker.id, "objeto_retirado")
                locker = crud.release_locker(db, locker.id)
                print(f"Locker liberado automáticamente. Nuevo estado: {locker.status}")
        except Exception as e:
            # Registrar error pero continuar con el proceso
            error_message = f"Error al comunicarse con ESP32: {str(e)}"
            print(error_message)
            crud.create_locker_alert(db, locker.id, error_message)
        
        # Devolver el locker actual
        return locker
        
    except HTTPException:
        # Re-lanzar excepciones HTTP para que FastAPI las maneje
        raise
    except Exception as e:
        # Capturar cualquier otra excepción y mostrar detalles
        error_message = f"Error inesperado en /unlock: {str(e)}"
        print(error_message)
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail="Error interno del servidor. Revisa los logs para más detalles.")

@router.get("/status/{locker_id}", response_model=schemas.Locker)
def get_locker_status(locker_id: int, db: Session = Depends(get_db)):
    locker = crud.get_locker(db, locker_id)
    if not locker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                           detail="Locker no encontrado")
    return locker

@router.post("/movement", response_model=schemas.Locker)
def register_movement(movement: schemas.LockerMovement, db: Session = Depends(get_db)):
    """
    Registra un movimiento en el locker (colocación o retiro de objeto)
    - has_object=True: se colocó un objeto, cambia estado a "ocupado" si no lo está
    - has_object=False: se retiró un objeto, libera el locker
    """
    print(f"Recibida notificación de movimiento: locker_id={movement.locker_id}, has_object={movement.has_object}")
    
    try:
        locker = crud.get_locker(db, movement.locker_id)
        if not locker:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Locker no encontrado")
          # Registrar el estado actual para diagnóstico
        print(f"Estado actual del locker: id={locker.id}, status={locker.status}, assigned_user_id={locker.assigned_user_id}")
        
        # Obtener información del usuario si está asignado
        user_email = "ninguno"
        if locker.assigned_user_id:
            user = db.query(models.LockerUser).get(locker.assigned_user_id)
            if user:
                user_email = user.email
        
        if movement.has_object:
            # Se colocó un objeto
            print(f"Objeto colocado en locker {locker.id}, usuario: {user_email}")
            crud.create_locker_history(db, locker.id, "objeto_colocado")
            
            # Asegurarnos de que el locker esté marcado como ocupado
            if locker.status != "ocupado":
                locker = crud.update_locker_status(db, locker.id, "ocupado")
                print(f"Estado actualizado a 'ocupado': locker_id={locker.id}")
        else:
            # Se retiró un objeto, liberar completamente el locker
            print(f"Liberando locker {locker.id}, desasociando de usuario {user_email} (id: {locker.assigned_user_id})")
            crud.create_locker_history(db, locker.id, "objeto_retirado")
            locker = crud.release_locker(db, locker.id)
            print(f"Locker liberado. Nuevo estado: {locker.status}, usuario asignado: {locker.assigned_user_id}")
        
        return locker
    except Exception as e:
        print(f"ERROR en /movement: {str(e)}")
        # Re-lanzar la excepción para que FastAPI la maneje adecuadamente
        raise

@router.get("/history/{locker_id}", response_model=List[schemas.LockerHistory])
def get_locker_history(locker_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    locker = crud.get_locker(db, locker_id)
    if not locker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                           detail="Locker no encontrado")
    
    history = crud.get_locker_history(db, locker_id, skip, limit)
    return history

@router.get("/alerts/{locker_id}", response_model=List[schemas.LockerAlert])
def get_locker_alerts(locker_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    locker = crud.get_locker(db, locker_id)
    if not locker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                           detail="Locker no encontrado")
    
    alerts = crud.get_locker_alerts(db, locker_id, skip, limit)
    return alerts