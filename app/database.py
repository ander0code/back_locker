from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
import urllib.parse

# Escapar la contraseña para evitar problemas con caracteres especiales
password = urllib.parse.quote_plus(settings.DB_PASSWORD)
SQLALCHEMY_DATABASE_URL = f"postgresql://{settings.DB_USER}:{password}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"

# Crear motor de base de datos con opciones específicas
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,  # Verificar la conexión antes de usarla
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()