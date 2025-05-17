import uvicorn

if __name__ == "__main__":
    # Ejecutar la aplicación escuchando en todas las interfaces (0.0.0.0)
    # Esto permite conexiones desde la red local, no solo desde localhost
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)