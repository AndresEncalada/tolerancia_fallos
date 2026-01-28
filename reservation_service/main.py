import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import sqlite3
import os
import uuid
import pybreaker
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

app = FastAPI()

# --- CONFIGURACIÓN ---
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8001")
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://localhost:8002")
NOTIFICATION_URL = os.getenv("NOTIFICATION_URL", "http://localhost:8003")

# --- BASE DE DATOS ---
DB_FOLDER = "data"
DB_FILE = os.path.join(DB_FOLDER, "reservas.db")

# --- VARIABLES GLOBALES DE CAOS ---
# Controlan si la BD debe fallar simuladamente
db_flaky_mode = os.getenv("DB_FLAKY", "false")

def init_db():
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                item_id TEXT,
                amount REAL,
                status TEXT
            )
        ''')
        print(f"Base de datos lista en: {DB_FILE}")

init_db()

# --- MODELOS DE DATOS ---
class ReservationRequest(BaseModel):
    user_id: str
    item_id: str
    amount: float

# [CORRECCIÓN] Definimos esto ANTES de usarlo en el endpoint
class ChaosCommand(BaseModel):
    enable: bool

# --- RESILIENCIA: CIRCUIT BREAKER (Inventario) ---
inventory_breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=10)

@inventory_breaker
def call_inventory_safe(item_id: str):
    resp = requests.post(f"{INVENTORY_URL}/api/inventory/reserve", params={"item_id": item_id})
    if resp.status_code == 400:
        return {"error": "sold_out"}
    resp.raise_for_status() 
    return resp.json()

# --- RESILIENCIA: RETRIES (Base de Datos) ---
@retry(stop=stop_after_attempt(3), wait=wait_fixed(1), retry=retry_if_exception_type(sqlite3.OperationalError))
def save_reservation_safe(order_id, user_id, item_id, amount):
    # USAMOS LA VARIABLE GLOBAL PARA EL CAOS
    if db_flaky_mode == "true":
        import random
        # 50% de probabilidad de fallo si el modo caos está activo
        if random.choice([True, False]):
            print("!!! SIMULANDO FALLO DE CONEXIÓN BD !!!")
            raise sqlite3.OperationalError("Simulated DB Connection Lost")

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT INTO reservations (id, user_id, item_id, amount, status) VALUES (?, ?, ?, ?, ?)",
            (order_id, user_id, item_id, amount, "CONFIRMED")
        )
    print("Reserva guardada en BD.")

# --- ENDPOINTS ---

@app.get("/")
def health_check():
    return {"status": "Reservation Core Active"}

# [NUEVO] Endpoint para activar/desactivar caos en BD
@app.post("/api/chaos/db")
def set_db_chaos(cmd: ChaosCommand):
    global db_flaky_mode
    db_flaky_mode = "true" if cmd.enable else "false"
    print(f"!!! CAOS BD ACTUALIZADO: {db_flaky_mode} !!!")
    return {"status": "db_chaos_updated", "flaky_mode": db_flaky_mode}

@app.post("/api/reservations")
def create_reservation(reservation: ReservationRequest):
    print(f"--> Procesando reserva: {reservation.user_id}")
    order_id = str(uuid.uuid4())

    # 1. INVENTARIO
    try:
        inv_data = call_inventory_safe(reservation.item_id)
        if "error" in inv_data and inv_data["error"] == "sold_out":
             raise HTTPException(status_code=400, detail="Lo sentimos, entradas agotadas.")
    except pybreaker.CircuitBreakerError:
        print("!!! CIRCUIT BREAKER ABIERTO !!!")
        return {"status": "pending", "message": "Sistemas saturados, procesaremos tu orden manualmente", "order_id": order_id}
    except Exception as e:
         raise HTTPException(status_code=503, detail=f"Error técnico en inventario: {str(e)}")

    # 2. PAGOS (SOLUCIÓN: TIMEOUT)
    # Si tarda más de 5s, cortamos y damos error.
    try:
        pay_resp = requests.post(
            f"{PAYMENT_URL}/api/payment/process", 
            params={"amount": reservation.amount},
            timeout=5 
        )
        pay_resp.raise_for_status()
    
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="El sistema de pagos no responde a tiempo. Intente más tarde.")
        
    except Exception as e:
        raise HTTPException(status_code=502, detail="Fallo en pasarela de pago")

    # 3. BASE DE DATOS
    try:
        save_reservation_safe(order_id, reservation.user_id, reservation.item_id, reservation.amount)
    except Exception as e:
        print(f"Error final BD: {e}")
        raise HTTPException(status_code=500, detail="No se pudo guardar la reserva tras varios intentos")

    # 4. NOTIFICACIÓN (Fail-Safe con Reporte)
    email_result = "sent"
    try:
        # Guardamos la respuesta en una variable 'resp'
        resp = requests.post(f"{NOTIFICATION_URL}/api/notification/send", json={"email": "user@test.com", "message": "OK"}, timeout=2)
        resp.raise_for_status() 

    except Exception as e:
        print(f"⚠️ ADVERTENCIA: No se pudo enviar el correo ({str(e)})")
        email_result = "failed" 

    return {
        "status": "success", 
        "order_id": order_id, 
        "email_status": email_result
    }

@app.get("/api/debug/db")
def read_database():
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.cursor().execute("SELECT * FROM reservations").fetchall()
            return {"total_records": len(rows), "data": [dict(row) for row in rows]}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)