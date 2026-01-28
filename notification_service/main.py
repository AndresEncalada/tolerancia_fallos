import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# "up" = Funciona, "down" = Simula caída (500 Error)
service_status = "up"

class ChaosCommand(BaseModel):
    status: str

@app.get("/")
def health_check():
    return {"status": "Notification Service", "state": service_status}

@app.post("/api/chaos")
def set_chaos(cmd: ChaosCommand):
    global service_status
    service_status = cmd.status
    return {"status": "updated", "state": service_status}

class EmailRequest(BaseModel):
    email: str
    message: str

@app.post("/api/notification/send")
def send_email(request: EmailRequest):
    # --- CHAOS MONKEY: CORREO CAÍDO ---
    if service_status == "down":
        print("!!! FALLO DE NOTIFICACIÓN SIMULADO !!!")
        raise HTTPException(status_code=500, detail="Mail Server Down")

    print(f"--> Correo enviado a {request.email}")
    return {"status": "sent"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)