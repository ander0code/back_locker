from fastapi import FastAPI
from app.api import routes

app = FastAPI(
    title="Sistema de Lockers API",
    description="API para gestionar un sistema de lockers inteligentes",
    version="1.0.0"
)

# Incluir enrutador
app.include_router(routes.router)

@app.get("/")
def read_root():
    return {"mensaje": "Bienvenido a la API del Sistema de Lockers"}