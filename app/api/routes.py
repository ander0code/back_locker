from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import List, Dict
import json

from app import crud, schemas, models
from app.database import get_db
from app.utils.mailer import send_pin_email
# from app.core.config import settings

# Clase para gestionar conexiones WebSocket
class ConnectionManager:
    def __init__(self):
        # Diccionario de listas de WebSockets por locker_id
        self.active_connections: Dict[int, List[WebSocket]] = {}
    
    async def connect(self, locker_id: int, websocket: WebSocket):
        await websocket.accept()
        if locker_id not in self.active_connections:
            self.active_connections[locker_id] = []
        self.active_connections[locker_id].append(websocket)
        print(f"Cliente WebSocket conectado al locker {locker_id}. Total conexiones: {len(self.active_connections[locker_id])}")
    
    def disconnect(self, locker_id: int, websocket: WebSocket):
        if locker_id in self.active_connections:
            self.active_connections[locker_id].remove(websocket)
            print(f"Cliente WebSocket desconectado del locker {locker_id}")
            if not self.active_connections[locker_id]:
                del self.active_connections[locker_id]
    
    async def broadcast(self, locker_id: int, message: str):
        if locker_id in self.active_connections:
            for connection in self.active_connections[locker_id]:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    print(f"Error al enviar mensaje a cliente WebSocket: {str(e)}")

# Instancia global del gestor de conexiones
manager = ConnectionManager()

router = APIRouter()

@router.post("/use", response_model=schemas.Locker)
async def use_locker(locker_use: schemas.LockerUse, db: Session = Depends(get_db)):
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
    
    # Enviar evento por WebSocket
    event_data = {
        "event": "locker_assigned",
        "locker_id": locker.id,
        "status": locker.status,
        "user_id": user.id,
        "email": user.email
    }
    await manager.broadcast(locker.id, json.dumps(event_data))
    
    # Notificar al ESP32 para abrir el locker en modo "store"
    try:
        # En lugar de HTTP, ahora enviamos por WebSocket
        ws_command = {
            "cmd": "actuate",
            "open": True,
            "mode": "store"
        }
        await manager.broadcast(locker.id, json.dumps(ws_command))
        print(f"Comando enviado al locker {locker.id} por WebSocket: {ws_command}")
          # WebSocket ya está funcionando, no necesitamos HTTP como fallback
        # Antiguamente se usaba HTTP como fallback, pero ahora es innecesario
        print("Usando comunicación WebSocket para controlar el locker")
        
        # Registramos para diagnóstico
        crud.create_locker_history(db, locker.id, "comando_websocket_enviado")
    except Exception as e:
        # Registrar error pero continuar con el proceso
        error_message = f"Error al comunicarse con ESP32: {str(e)}"
        print(error_message)
        crud.create_locker_alert(db, locker.id, error_message)
    
    return locker

@router.post("/unlock", response_model=schemas.Locker)
async def unlock_locker(pin_verification: schemas.PinVerification, db: Session = Depends(get_db)):
    print(f"Recibida solicitud de desbloqueo con PIN: {pin_verification.pin}")
    try:
        # Validar PIN
        if not crud.is_pin_valid(db, pin_verification.pin):
            print(f"PIN inválido: {pin_verification.pin}")
            user = crud.get_user_by_pin(db, pin_verification.pin)
            if user:
                assigned_locker = crud.get_locker_by_user_id(db, user.id)
                if assigned_locker:
                    crud.create_locker_history(db, assigned_locker.id, "intento_fallido")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="PIN inválido o expirado")

        user = crud.get_user_by_pin(db, pin_verification.pin)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Usuario no encontrado")

        locker = crud.get_locker_by_user_id(db, user.id)
        if not locker:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="No hay locker asignado a este usuario")

        crud.create_locker_history(db, locker.id, "locker_abierto")

        # Enviar evento WebSocket al frontend
        unlock_event = {
            "event": "locker_opened", 
            "locker_id": locker.id,
            "user_id": user.id
        }
        await manager.broadcast(locker.id, json.dumps(unlock_event))

        # Enviar comando al ESP32
        ws_command = {
            "cmd": "actuate",
            "open": True,
            "mode": "retrieve"
        }
        await manager.broadcast(locker.id, json.dumps(ws_command))
        crud.create_locker_history(db, locker.id, "comando_websocket_enviado")
        print(f"Comando enviado al locker {locker.id} para modo 'retrieve'")

        # 🔴 NUEVO: liberar locker inmediatamente
        locker = crud.release_locker(db, locker.id)
        crud.create_locker_history(db, locker.id, "locker_liberado_tras_unlock")
        print(f"Locker {locker.id} liberado automáticamente en /unlock")

        return locker

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error inesperado en /unlock: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


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

@router.websocket("/ws/locker/{locker_id}")
async def websocket_locker(websocket: WebSocket, locker_id: int):
    """
    WebSocket en tiempo real con el ESP32 y el frontend.
    Escucha eventos como 'object_retrieved' para liberar el locker desde ESP32.
    """
    await manager.connect(locker_id, websocket)
    try:
        welcome_msg = {
            "event": "connected",
            "message": f"Conectado al locker {locker_id}",
            "status": "ok"
        }
        await websocket.send_text(json.dumps(welcome_msg))
        print(f"Nueva conexión WebSocket aceptada para locker {locker_id}")

        while True:
            data = await websocket.receive_text()
            print(f"Mensaje recibido del locker {locker_id}: {data}")

            try:
                parsed = json.loads(data)

                # ✅ Detectar evento especial de retiro de objeto
                if parsed.get("event") == "object_retrieved":
                    print(f"[{locker_id}] Objeto retirado detectado por ESP32")
                    
                    db = next(get_db())
                    crud.create_locker_history(db, locker_id, "objeto_retirado")
                    locker = crud.release_locker(db, locker_id)
                    
                    print(f"[{locker_id}] Locker liberado automáticamente")

                    # Notificar a todos los clientes frontend
                    release_event = {
                        "event": "locker_released",
                        "locker_id": locker_id
                    }
                    await manager.broadcast(locker_id, json.dumps(release_event))
                    continue  # evitar que este mensaje se reenvíe a todos otra vez

            except Exception as e:
                print(f"[{locker_id}] Error procesando mensaje JSON: {e}")

            # Reenviar el mensaje recibido a todos los clientes conectados
            await manager.broadcast(locker_id, data)

    except WebSocketDisconnect:
        manager.disconnect(locker_id, websocket)
        print(f"Cliente WebSocket desconectado del locker {locker_id}")

    except Exception as e:
        print(f"Error en websocket del locker {locker_id}: {str(e)}")
        try:
            manager.disconnect(locker_id, websocket)
        except Exception as disconnect_error:
            print(f"Error al desconectar websocket: {disconnect_error}")
