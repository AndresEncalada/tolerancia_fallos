import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import json

app = FastAPI()

# --- CONFIGURACIÓN ---
DATA_FOLDER = "data"
DB_FILE = os.path.join(DATA_FOLDER, "inventory.json")

DEFAULT_INVENTORY = {
    "ticket_rock_concert": 100,
    "ticket_vip": 100,
    "ticket_general": 500
}

# Variable Global de Caos
current_failure_mode = os.getenv("FAILURE_MODE", "none")

def load_inventory():
    if not os.path.exists(DATA_FOLDER):
        os.makedirs(DATA_FOLDER)
    if not os.path.exists(DB_FILE):
        save_inventory(DEFAULT_INVENTORY)
        return DEFAULT_INVENTORY.copy()
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except:
        return DEFAULT_INVENTORY.copy()

def save_inventory(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

inventory_db = load_inventory()

# --- MODELOS ---
class AddStockRequest(BaseModel):
    item_id: str
    quantity: int

class ChaosCommand(BaseModel):
    mode: str  # "crash" o "none"

# --- ENDPOINTS ---

@app.get("/")
def health_check():
    return {"status": "Inventory Service is running", "stock": inventory_db, "chaos_mode": current_failure_mode}

# [NUEVO] Endpoint Control de Caos
@app.post("/api/chaos")
def set_chaos_mode(cmd: ChaosCommand):
    global current_failure_mode
    current_failure_mode = cmd.mode
    print(f"!!! CAOS INVENTARIO ACTUALIZADO: {current_failure_mode} !!!")
    return {"status": "chaos_updated", "current_mode": current_failure_mode}

@app.post("/api/inventory/reserve")
def reserve_stock(item_id: str):
    # 1. CHAOS CHECK
    if current_failure_mode == "crash":
        raise HTTPException(status_code=500, detail="CRITICAL_FAILURE: Inventory System Crash")

    # 2. LOGICA
    if item_id not in inventory_db:
        raise HTTPException(status_code=404, detail="Item no existe")
    
    if inventory_db[item_id] <= 0:
        raise HTTPException(status_code=400, detail="Sold Out")

    inventory_db[item_id] -= 1
    save_inventory(inventory_db)
    
    return {
        "status": "reserved", 
        "item_id": item_id, 
        "remaining_stock": inventory_db[item_id]
    }

@app.post("/api/inventory/reset")
def reset_inventory():
    global inventory_db
    inventory_db = DEFAULT_INVENTORY.copy()
    save_inventory(inventory_db)
    return {"status": "Inventory Reset", "stock": inventory_db}

@app.post("/api/inventory/add")
def add_stock(request: AddStockRequest):
    if request.item_id not in inventory_db:
        inventory_db[request.item_id] = 0
    inventory_db[request.item_id] += request.quantity
    save_inventory(inventory_db)
    return {"status": "Stock Updated", "new_quantity": inventory_db[request.item_id]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)