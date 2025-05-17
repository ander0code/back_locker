import smtplib
from email.mime.text import MIMEText
from app.core.config import settings

def send_pin_email(to_email: str, pin: str):
    msg = MIMEText(f"Tu PIN para abrir el locker es: {pin}")
    msg["Subject"] = "Código PIN para Locker"
    msg["From"] = settings.EMAIL_HOST_USER
    msg["To"] = to_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
        server.send_message(msg)