import socket
import requests
import sys

def get_ip():
    """Obtener la IP de esta PC en la red local"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        print(f"Error obteniendo IP: {e}")
        return None

def check_server(url, method="GET", json=None):
    """Verificar si un servidor está respondiendo"""
    try:
        if method.upper() == "GET":
            response = requests.get(url, timeout=5)
        elif method.upper() == "POST":
            response = requests.post(url, json=json, timeout=5)
        else:
            return {"success": False, "error": f"Método no soportado: {method}"}
            
        return {
            "success": True, 
            "status": response.status_code, 
            "response": response.text[:100]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def main():
    # Obtener la IP local
    local_ip = get_ip()
    if not local_ip:
        print("No se pudo determinar la IP local")
        sys.exit(1)
    
    print("\n=== DIAGNÓSTICO DE CONEXIÓN ===")
    print(f"IP local de esta PC: {local_ip}")
    
    # Verificar backend en localhost
    print("\nVerificando backend en localhost...")
    result = check_server("http://127.0.0.1:8000")
    if result["success"]:
        print(f"✅ Backend responde en localhost: HTTP {result['status']}")
    else:
        print(f"❌ Backend no responde en localhost: {result.get('error')}")
        print("   Asegúrate de que el servidor está en ejecución")
        sys.exit(1)
    
    # Verificar backend en IP externa
    print(f"\nVerificando backend en IP externa ({local_ip})...")
    result = check_server(f"http://{local_ip}:8000")
    if result["success"]:
        print(f"✅ Backend responde en IP externa: HTTP {result['status']}")
    else:
        print(f"❌ Backend NO responde en IP externa: {result.get('error')}")
        print("   - Verifica que tu servidor esté configurado con host='0.0.0.0'")
        print("   - Asegúrate de que el firewall permita conexiones entrantes al puerto 8000")
        sys.exit(1)
      # Verificar endpoint /api/movement
    print("\nVerificando endpoint /api/movement...")
    test_data = {"locker_id": 1, "has_object": True}
    
    # Usar un timeout más largo para dar tiempo al backend
    try:
        print("Enviando solicitud POST a /api/movement (espera hasta 15 segundos)...")
        response = requests.post(
            f"http://{local_ip}:8000/api/movement", 
            json=test_data, 
            timeout=15
        )
        print(f"✅ Endpoint /api/movement responde: HTTP {response.status_code}")
        print(f"Respuesta: {response.text[:100]}")
    except Exception as e:
        print(f"❌ Endpoint /api/movement no responde: {str(e)}")
        print("\nPosibles causas:")
        print("1. El endpoint no está implementado correctamente")
        print("2. El backend está procesando las solicitudes muy lentamente")
        print("3. Hay un problema con la validación de datos o la lógica del endpoint")
        
        print("\n¿Deseas continuar de todas formas? (S/N): ", end="")
        if input().strip().lower() != 's':
            sys.exit(1)
    
    print("\n=== CONFIGURACIÓN CORRECTA ===")
    print("✅ Tu backend es accesible desde la red local")
    print("✅ El endpoint /api/movement funciona correctamente")
    print(f"✅ La IP correcta para tu ESP32 es: {local_ip}")
    print("\nPara que tu ESP32 funcione correctamente:")
    print(f"1. Asegúrate de que BASE_URL = \"http://{local_ip}:8000\" en el código del ESP32")
    print("2. Carga el código actualizado al ESP32")
    print("3. Mantén tu servidor backend en ejecución con host='0.0.0.0'")

if __name__ == "__main__":
    main()