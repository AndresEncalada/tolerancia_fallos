import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import requests
import os

app = FastAPI()

RESERVATION_SERVICE_URL = os.getenv("RESERVATION_URL", "http://localhost:8004")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_URL", "http://localhost:8002")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_URL", "http://localhost:8003")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_URL", "http://localhost:8001")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/health")
def gateway_health():
    return {"status": "Gateway Online"}

@app.post("/buy-ticket")
def buy_ticket(request: dict):
    try:
        response = requests.post(f"{RESERVATION_SERVICE_URL}/api/reservations", json=request)
        return response.json()
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Service Unavailable: Core system is down")

@app.get("/debug/db")
def proxy_debug_db():
    try:
        response = requests.get(f"{RESERVATION_SERVICE_URL}/api/debug/db")
        return response.json()
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="No se pudo conectar al Core")

# --- CONTROL DE CAOS (Puentes) ---

@app.post("/control/inventory-chaos")
def control_inventory(request: dict):
    # request: {"mode": "crash"}
    try:
        # Nota: El gateway llama directo al inventario (puerto 8001) para configurar esto
        # Asegúrate de que en docker-compose el gateway pueda ver al inventario (lo hace, están en la misma red)
        resp = requests.post(f"{INVENTORY_SERVICE_URL}/api/chaos", json=request)
        return resp.json()
    except Exception as e:
        return {"error": f"No se pudo contactar al Inventario: {str(e)}"}

@app.post("/control/inventory-reset")
def reset_inventory_proxy():
    try:
        # Llamamos al endpoint de reset que ya creamos en el inventario
        resp = requests.post(f"{INVENTORY_SERVICE_URL}/api/inventory/reset")
        return resp.json()
    except Exception as e:
        return {"error": f"No se pudo contactar al Inventario: {str(e)}"}

@app.post("/control/db-chaos")
def control_db(request: dict):
    # request: {"enable": true}
    try:
        resp = requests.post(f"{RESERVATION_SERVICE_URL}/api/chaos/db", json=request)
        return resp.json()
    except Exception as e:
        return {"error": f"No se pudo contactar al Core: {str(e)}"}

@app.post("/control/payment-chaos")
def control_payment(request: dict):
    try:
        resp = requests.post(f"{PAYMENT_SERVICE_URL}/api/chaos", json=request)
        return resp.json()
    except Exception as e: return {"error": str(e)}

@app.post("/control/notification-chaos")
def control_notification(request: dict):
    try:
        resp = requests.post(f"{NOTIFICATION_SERVICE_URL}/api/chaos", json=request)
        return resp.json()
    except Exception as e: return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)