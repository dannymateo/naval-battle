"""
FSM Naval Battle - Servidor de Defensa (5x5)
-------------------------------------------
Implementación del servidor con tablero 5x5 y soporte dual (CLI/Web).
"""

from fastapi import FastAPI, HTTPException, WebSocket
import uvicorn
from pydantic import BaseModel
import socket
import threading
from typing import Dict, Set, Optional
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import time
import os

class NavalServerFSM:
    # Estados del autómata
    INICIO = 'q0'
    FLOTA_INTACTA = 'q1'
    HUNDIDO = 'q2'
    
    def __init__(self):
        self.reset_state()
        self.host = '0.0.0.0'  # Cambiado a localhost
        self.port = 5000

    def reset_state(self):
        """
        Reinicia el estado del servidor
        """
        # Limpiar recursos anteriores si existen
        if hasattr(self, 'running'):
            self.running = False
        if hasattr(self, 'server_socket') and self.server_socket:
            self.server_socket.close()
        if hasattr(self, 'server_thread') and self.server_thread:
            self.server_thread.join()

        self.estado_actual = self.INICIO
        self.filas = 5
        self.columnas = 5
        
        # Inicializar tablero 5x5
        self.tablero = {
            f"{chr(65+i)}{j+1}": None 
            for i in range(5) 
            for j in range(5)
        }
        
        self.impactos = {
            f"{chr(65+i)}{j+1}": '~' 
            for i in range(5) 
            for j in range(5)
        }
        
        self.barcos = {
            'submarino': {'tamaño': 2, 'posiciones': []},
            'acorazado': {'tamaño': 3, 'posiciones': []},
            'destructor': {'tamaño': 1, 'posiciones': []}
        }
        
        self.ataques_recibidos = set()
        self.server_socket = None
        self.server_thread = None
        self.running = False

    def mostrar_tablero(self):
        """
        Muestra el estado actual del tablero
        """
        print("\nTablero de defensa (5x5):")
        print("  1 2 3 4 5")
        print(" ┌─────────┐")
        
        for fila in range(5):
            letra = chr(65 + fila)
            print(f"{letra}│", end="")
            for col in range(1, 6):
                pos = f"{letra}{col}"
                if self.impactos[pos] == 'X':
                    print("X ", end="")  # Impacto
                elif self.impactos[pos] == 'O':
                    print("O ", end="")  # Agua
                elif self.tablero[pos] is not None:
                    print(f"{self.tablero[pos]} ", end="")  # Barco
                else:
                    print("~ ", end="")  # Agua sin atacar
            print("│")
        
        print(" └─────────┘")
        print(" S: Submarino, A: Acorazado, D: Destructor")
        print(" ~: Agua, O: Fallo, X: Impacto")

    def validar_posicion_continua(self, posiciones, tamaño):
        if len(posiciones) != tamaño:
            return False
            
        # Convertir posiciones a coordenadas numéricas
        coords = [(ord(pos[0]) - ord('A'), int(pos[1])) for pos in posiciones]
        coords.sort()
        
        # Verificar si están en la misma fila o columna
        misma_fila = all(c[0] == coords[0][0] for c in coords)
        misma_columna = all(c[1] == coords[0][1] for c in coords)
        
        if not (misma_fila or misma_columna):
            return False
            
        # Verificar si son continuas
        if misma_fila:
            return all(coords[i+1][1] - coords[i][1] == 1 for i in range(len(coords)-1))
        else:
            return all(coords[i+1][0] - coords[i][0] == 1 for i in range(len(coords)-1))

    def colocar_flota(self, tipo_barco: str, posiciones: list) -> bool:
        if tipo_barco not in self.barcos:
            return False
            
        # Validar que las posiciones estén dentro del tablero
        if not all(pos in self.tablero for pos in posiciones):
            return False
            
        # Validar que las posiciones estén vacías
        if any(self.tablero[pos] is not None for pos in posiciones):
            return False
            
        # Validar tamaño y continuidad
        if not self.validar_posicion_continua(posiciones, self.barcos[tipo_barco]['tamaño']):
            return False
            
        # Colocar el barco
        for pos in posiciones:
            self.tablero[pos] = tipo_barco[0].upper()
        self.barcos[tipo_barco]['posiciones'] = posiciones
        
        # Cambiar estado si todos los barcos están colocados
        flota_lista = all(len(barco['posiciones']) > 0 for barco in self.barcos.values())
        if flota_lista:
            self.estado_actual = self.FLOTA_INTACTA
            # En lugar de crear un nuevo loop, devolvemos un indicador
            return True, True  # (éxito, flota_completa)
            
        return True, False  # (éxito, flota_incompleta)

    def procesar_ataque(self, coordenada: str) -> tuple:
        """
        Procesa un ataque y retorna el resultado según el estado del FSM
        """
        try:
            if coordenada not in self.tablero:
                return "404", "Coordenada_Invalida"
            
            if coordenada in self.ataques_recibidos:
                return "409", "Atacado_Previamente"
            
            self.ataques_recibidos.add(coordenada)
            
            if self.estado_actual == self.INICIO:
                return "400", "Flota_No_Colocada"
                
            elif self.estado_actual == self.FLOTA_INTACTA:
                if self.tablero[coordenada] is not None:
                    self.impactos[coordenada] = 'X'
                    
                    # Verificar si todos los barcos están hundidos
                    todos_hundidos = True
                    for barco in self.barcos.values():
                        if not all(pos in self.ataques_recibidos for pos in barco['posiciones']):
                            todos_hundidos = False
                            break
                    
                    if todos_hundidos:
                        self.estado_actual = self.HUNDIDO
                        return "200", "Hundido"
                    return "202", "Impactado"
                else:
                    self.impactos[coordenada] = 'O'
                    return "404", "Fallido"
                    
            elif self.estado_actual == self.HUNDIDO:
                return "404", "Flota_Ya_Hundida"
            
            return "500", "Error_Estado_Automata"
            
        except Exception as e:
            print(f"Error procesando ataque: {str(e)}")
            return "500", f"Error_Interno: {str(e)}"

    async def procesar_ataque_y_notificar(self, coordenada: str) -> tuple:
        """
        Procesa un ataque y notifica al cliente web a través del WebSocket
        """
        codigo, resultado = self.procesar_ataque(coordenada)
        
        # Notificar al cliente web a través del WebSocket
        await manager.send_impact_to_control(coordenada, resultado)
        
        return codigo, resultado

    def iniciar_servidor_socket(self):
        """
        Maneja las conexiones TCP para los clientes
        """
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            
            print(f"\n╔══════════════════════════════════════════╗")
            print(f"║ [ SERVIDOR DE DEFENSA - FSM ]             ║")
            print(f"╚══════════════════════════════════════════╝")
            print(f"Escuchando en {self.host}:{self.port}...")
            self.mostrar_tablero()
            
            self.running = True
            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    print(f"\nConexión establecida con {client_address}")
                    
                    # Manejar cada conexión en un hilo separado
                    client_thread = threading.Thread(
                        target=self.handle_client_connection,
                        args=(client_socket, client_address)
                    )
                    client_thread.start()
                    
                except Exception as e:
                    if self.running:
                        print(f"Error en la conexión: {e}")
        except Exception as e:
            print(f"Error al iniciar el servidor socket: {e}")
        finally:
            if self.server_socket:
                self.server_socket.close()

    def handle_client_connection(self, client_socket, client_address):
        """
        Maneja una conexión TCP individual
        """
        try:
            # Recibir ataque
            data = client_socket.recv(1024).decode().strip()
            if not data:  # Si no hay datos, cerrar conexión
                return
                
            print(f"Ataque recibido en: {data}")
            
            # Procesar el ataque y notificar vía WebSocket
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            codigo, respuesta = loop.run_until_complete(self.procesar_ataque_y_notificar(data))
            loop.close()
            
            # Enviar respuesta TCP
            client_socket.send(f"{codigo}:{respuesta}".encode())
            print(f"Respuesta enviada: {codigo}:{respuesta}")
            
            # Mostrar el tablero actualizado
            self.mostrar_tablero()
            
            # Si el barco está hundido, mostrar mensaje de fin
            if self.estado_actual == self.HUNDIDO:
                print("\n¡Toda la flota ha sido hundida!")
            
        except Exception as e:
            print(f"Error al procesar la solicitud: {e}")
            try:
                client_socket.send("500:Error_Interno".encode())
            except:
                pass
        finally:
            client_socket.close()

    def get_estado_completo(self):
        """
        Retorna el estado completo del juego para el frontend
        """
        return {
            "estado_actual": self.estado_actual,
            "tablero": self.tablero,
            "impactos": self.impactos,
            "barcos_colocados": {
                tipo: len(info['posiciones']) > 0 
                for tipo, info in self.barcos.items()
            }
        }

    def iniciar_servidor(self):
        """
        Inicia el servidor en un hilo separado
        """
        if not self.server_thread:
            try:
                self.server_thread = threading.Thread(target=self.iniciar_servidor_socket)
                self.server_thread.start()
                return "Servidor iniciado correctamente"
            except Exception as e:
                print(f"Error al iniciar el servidor: {e}")
                return f"Error al iniciar el servidor: {e}"
        return "El servidor ya está en ejecución"

    def detener_servidor(self):
        """
        Detiene el servidor y limpia el estado
        """
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        if self.server_thread:
            try:
                self.server_thread.join(timeout=2)
            except:
                pass
        self.reset_state()
        return "Servidor detenido correctamente"

# Crear instancia de FastAPI primero
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.control_connection: Optional[WebSocket] = None
        self.pending_connection: Optional[WebSocket] = None

    async def connect_control(self, websocket: WebSocket):
        await websocket.accept()
        if servidor.estado_actual == servidor.FLOTA_INTACTA:
            self.control_connection = websocket
            await self.send_initial_state(websocket)
        else:
            self.pending_connection = websocket
            await websocket.send_json({
                "tipo": "error",
                "mensaje": "La flota no está lista. Por favor, complete la configuración de todos los barcos para iniciar el juego."
            })

    async def notify_fleet_ready(self):
        if self.pending_connection:
            self.control_connection = self.pending_connection
            self.pending_connection = None
            await self.send_initial_state(self.control_connection)

    async def send_initial_state(self, websocket: WebSocket):
        await websocket.send_json({
            "tipo": "estado_inicial",
            "estado": servidor.get_estado_completo()
        })

    async def disconnect_control(self):
        self.control_connection = None

    async def send_impact_to_control(self, coordenada: str, resultado: str):
        if self.control_connection:
            await self.control_connection.send_json({
                "tipo": "impacto",
                "coordenada": coordenada,
                "resultado": resultado
            })

manager = ConnectionManager()

@app.websocket("/ws/control")
async def websocket_control_endpoint(websocket: WebSocket):
    await manager.connect_control(websocket)
    try:
        await websocket.send_json({
            "tipo": "estado_inicial",
            "estado": servidor.get_estado_completo()
        })
        while True:
            await websocket.receive_text()  # Mantener conexión viva
    except:
        await manager.disconnect_control()

# Crear instancia del servidor FSM después de los endpoints
servidor = NavalServerFSM()

# Iniciar el servidor TCP automáticamente al arrancar
servidor.iniciar_servidor()

class PosicionBarco(BaseModel):
    tipo: str
    posiciones: list[str]

@app.post("/colocar-flota")
async def colocar_flota(datos: PosicionBarco):
    resultado = servidor.colocar_flota(datos.tipo, datos.posiciones)
    if not resultado[0]:
        raise HTTPException(status_code=400, detail="Posición inválida")
        
    if resultado[1]:  # Si la flota está completa
        await manager.notify_fleet_ready()
        
    return {
        "mensaje": f"Barco {datos.tipo} colocado en {datos.posiciones}",
        "flota_completa": resultado[1]
    }

@app.get("/estado")
async def obtener_estado():
    return servidor.get_estado_completo()

@app.post("/reiniciar")
async def reiniciar_servicio():
    try:
        # Reiniciar el estado del servidor sin depender del systemctl
        servidor.detener_servidor()
        time.sleep(1)  # Pequeña pausa para asegurar limpieza de recursos
        mensaje = servidor.iniciar_servidor()
        
        return {"mensaje": "Servidor reiniciado exitosamente", "detalles": mensaje}
    except Exception as e:
        print(f"Error al reiniciar servidor: {str(e)}")  # Log para diagnóstico
        raise HTTPException(
            status_code=500,
            detail=f"Error al reiniciar el servidor: {str(e)}"
        )

def cli():
    """
    Interfaz de línea de comandos para el servidor
    """
    while True:
        print("\n=== Servidor Naval FSM ===")
        print("1. Colocar barco")
        print("2. Mostrar tablero")
        print("3. Salir")
        
        opcion = input("\nSeleccione una opción: ")
        
        if opcion == "1":
            print("\nTipos de barcos disponibles:")
            print("- submarino (2 casillas)")
            print("- acorazado (3 casillas)")
            print("- destructor (1 casilla)")
            
            tipo = input("Ingrese el tipo de barco: ").lower()
            if tipo not in servidor.barcos:
                print("Tipo de barco inválido")
                continue
                
            posiciones = input(f"Ingrese las posiciones (ej: A1,A2 para {tipo}): ").split(',')
            if servidor.colocar_flota(tipo, posiciones):
                print(f"Barco {tipo} colocado exitosamente")
            else:
                print("Error al colocar el barco")
                
        elif opcion == "2":
            servidor.mostrar_tablero()
            
        elif opcion == "3":
            break
            
        else:
            print("Opción inválida")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        cli()
    else:
        # FastAPI corre en puerto 8000
        uvicorn.run(app, host="191.91.240.39", port=8000) 