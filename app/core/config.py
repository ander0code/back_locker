from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Conexión a base de datos por componentes
    DB_HOST: str = "167.234.226.113"
    DB_PORT: str = "5432" 
    DB_NAME: str = "locker"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "root@123"
      # Email
    EMAIL_HOST_USER: str = "ttitokevin5@gmail.com"
    EMAIL_HOST_PASSWORD: str = "jkpy sfmr qupo uuer"
      # ESP32
    ESP32_IP: str = "192.168.100.6"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

# Crear una única instancia de Settings
settings = Settings()