import platform
import socket
import subprocess
import sys

def ping_test(host):
    """Realiza un ping básico para verificar conectividad"""
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '4', host]
    
    print(f"Ejecutando: {' '.join(command)}")
    try:
        # Usar encoding con manejo de errores para evitar problemas con caracteres no UTF-8
        output = subprocess.check_output(command).decode('utf-8', errors='replace')
        print(output)
        return "0% packet loss" in output or "0% pérdida de paquetes" in output or "0 perdidos" in output or "perdidos = 0" in output
    except subprocess.CalledProcessError as e:
        print(f"Error al ejecutar ping: {e}")
        return False

def scan_port(host, port):
    """Verifica si un puerto específico está abierto"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex((host, port))
    sock.close()
    
    if result == 0:
        print(f"Puerto {port} en {host} está ABIERTO")
        return True
    else:
        print(f"Puerto {port} en {host} está CERRADO (código: {result})")
        return False

def get_local_ip():
    """Obtiene la dirección IP local de la computadora"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No importa si esta dirección es alcanzable
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def get_network_info():
    """Obtiene información sobre la red local"""
    local_ip = get_local_ip()
    print(f"Dirección IP local: {local_ip}")
    
    # Dividir la IP para obtener la subred
    ip_parts = local_ip.split('.')
    if len(ip_parts) == 4:
        subnet = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}"
        print(f"Subred: {subnet}.x")
        return subnet
    return None

def main():
    print("=== DIAGNÓSTICO DE RED PARA ESP32 ===\n")
    
    # Obtener información de red local
    subnet = get_network_info()
    
    # Dirección IP del ESP32
    esp32_ip = "192.168.100.47"
    if len(sys.argv) > 1:
        esp32_ip = sys.argv[1]
    
    print(f"\n=== PRUEBAS DE CONECTIVIDAD CON {esp32_ip} ===\n")
    
    # Verificar si el ESP32 está en la misma subred
    esp32_ip_parts = esp32_ip.split('.')
    if len(esp32_ip_parts) == 4:
        esp32_subnet = f"{esp32_ip_parts[0]}.{esp32_ip_parts[1]}.{esp32_ip_parts[2]}"
        if subnet and esp32_subnet != subnet:
            print(f"ADVERTENCIA: El ESP32 ({esp32_subnet}.x) parece estar en una subred diferente a tu computadora ({subnet}.x)")
            print("Esto puede causar problemas de conectividad.")
    
    # Realizar prueba de ping
    print("\n1. Prueba de PING:")
    ping_success = ping_test(esp32_ip)
    
    # Realizar prueba de puerto
    print("\n2. Prueba de PUERTO 80:")
    port_success = scan_port(esp32_ip, 80)
    
    # Resumir resultados
    print("\n=== RESUMEN DE RESULTADOS ===")
    print(f"Prueba de PING: {'EXITOSA' if ping_success else 'FALLIDA'}")
    print(f"Prueba de PUERTO 80: {'EXITOSA' if port_success else 'FALLIDA'}")
    
    # Recomendaciones
    print("\n=== RECOMENDACIONES ===")
    if not ping_success:
        print("- El ESP32 no responde a ping. Verifica:")
        print("  * Que el ESP32 esté encendido y conectado a la red WiFi")
        print("  * Que la dirección IP sea correcta")
        print("  * Que no haya un firewall bloqueando el tráfico ICMP")
    
    if not port_success:
        print("- El puerto 80 no está abierto. Verifica:")
        print("  * Que el sketch con el servidor web esté cargado en el ESP32")
        print("  * Que el servidor web esté configurado en el puerto 80")
        print("  * Que el ESP32 esté funcionando correctamente")
        print("  * Que no haya un firewall bloqueando el puerto 80")
    
    if not ping_success and not port_success:
        print("\nPrueba estas soluciones:")
        print("1. Reinicia el ESP32")
        print("2. Desactiva temporalmente el firewall de Windows")
        print("3. Carga el sketch 'simple_locker_controller.ino' en el ESP32")
        print("4. Verifica en el monitor serial del Arduino IDE que el ESP32 muestra correctamente su IP")
        print("5. Asegúrate de que tu computadora y el ESP32 estén en la misma red WiFi")

if __name__ == "__main__":
    main()