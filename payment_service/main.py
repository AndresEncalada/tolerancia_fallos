import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
import asyncio
import os

app = FastAPI()

# --- ESTADO GLOBAL ---
# "none" = Normal, "latency" = Lento (20s)
latency_mode = "none"

class ChaosCommand(BaseModel):
    mode: str

@app.get("/")
def health_check():
    return {"status": "Payment Service is running", "mode": latency_mode}

# Endpoint para activar el caos desde el Dashboard
@app.post("/api/chaos")
def set_chaos(cmd: ChaosCommand):
    global latency_mode
    latency_mode = cmd.mode
    return {"status": "updated", "mode": latency_mode}

@app.post("/api/payment/process")
async def process_payment(amount: float): # Async para poder usar sleep sin bloquear todo
    print(f"Procesando pago de ${amount}...")
    
    # --- CHAOS MONKEY: LATENCIA ---
    if latency_mode == "latency":
        await asyncio.sleep(20) # Se duerme 20 segundos
    
    # --- HAPPY PATH ---
    print("Pago completado.")
    return {"status": "paid", "transaction_id": "tx_12345"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)