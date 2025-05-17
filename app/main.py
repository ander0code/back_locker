from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes

app = FastAPI(
    title="Sistema de Lockers API",
    description="API para gestionar un sistema de lockers inteligentes",
    version="1.0.0"
)

# Configurar CORS para permitir solicitudes desde cualquier origen
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite todos los orígenes
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos los métodos
    allow_headers=["*"],  # Permite todos los headers
)

# Incluir enrutador
app.include_router(routes.router)

@app.get("/")
def read_root():
    return {"mensaje": "Bienvenido a la API del Sistema de Lockers"}