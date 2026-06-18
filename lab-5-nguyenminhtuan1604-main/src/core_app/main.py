from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, field_validator
from datetime import datetime, timezone
from typing import Optional
import os
import httpx
import uuid

app = FastAPI(
    title="Smart Campus — Core Business Policy API",
    version=os.getenv("SERVICE_VERSION", "v0.1.0-team-core"),
    description="Lab 05 — Core Business Policy Engine with Docker Compose"
)

# ── Exception handlers ─────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(status_code=422, media_type="application/problem+json",
        content={
            "type": "https://campus.local/errors/validation",
            "title": "Validation Error", "status": 422,
            "detail": str(exc.errors()[0]["msg"]),
            "instance": str(request.url.path), "errors": []
        })

# ── Config ─────────────────────────────────────────────────────
AUTH_TOKEN     = os.getenv("AUTH_TOKEN", "lab-compose-token")
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai-service:9000")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "v0.1.0-team-core")

# Timeout settings (giây)
AI_TIMEOUT        = float(os.getenv("AI_TIMEOUT", "5.0"))
PARTNER_TIMEOUT   = float(os.getenv("PARTNER_TIMEOUT", "5.0"))

security = HTTPBearer(auto_error=False)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials or credentials.credentials != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail={
            "type": "https://campus.local/errors/unauthorized",
            "title": "Unauthorized", "status": 401,
            "detail": "Invalid or missing token",
            "instance": "/", "errors": []
        })
    return credentials.credentials

# ── In-memory data ─────────────────────────────────────────────
POLICIES = {
    "POL-2026-001": {
        "policyId": "POL-2026-001", "gateId": "GATE-01",
        "allowedRoles": ["STUDENT", "STAFF"],
        "timeRestriction": {
            "restrictionType": "TIME_WINDOW",
            "startTime": "07:00", "endTime": "22:00",
            "daysOfWeek": ["MON", "TUE", "WED", "THU", "FRI"]
        },
        "active": True, "updatedAt": "2026-05-01T00:00:00Z"
    },
    "POL-2026-002": {
        "policyId": "POL-2026-002", "gateId": "GATE-05",
        "allowedRoles": ["STAFF", "ADMIN"],
        "timeRestriction": None,
        "active": True, "updatedAt": "2026-05-01T00:00:00Z"
    },
}

ACCESS_LOGS = []

# ── Schemas ────────────────────────────────────────────────────
class AccessCheckRequest(BaseModel):
    cardId: str
    gateId: str
    direction: str
    timestamp: str

    @field_validator("cardId")
    @classmethod
    def validate_card_id(cls, v):
        import re
        if not re.match(r"^RFID-[A-Z0-9\-]{1,28}$", v):
            raise ValueError("cardId must match pattern ^RFID-[A-Z0-9-]{1,28}$")
        return v

class AccessLogRequest(BaseModel):
    cardId: str
    gateId: str
    direction: str
    decision: str
    reason: Optional[str] = None
    timestamp: str

# ── Helper: gọi service ngoài có timeout + xử lý lỗi ──────────
async def call_external(url: str, payload: dict, timeout: float = 5.0) -> dict:
    """Gọi service ngoài với timeout rõ ràng, không treo vô hạn."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            return {
                "error": "service_timeout",
                "message": f"Service tại {url} không phản hồi sau {timeout}s",
                "status": 503
            }
        except httpx.HTTPStatusError as e:
            return {
                "error": "service_error",
                "message": f"Service trả lỗi {e.response.status_code}",
                "status": e.response.status_code
            }
        except httpx.RequestError:
            return {
                "error": "service_unavailable",
                "message": f"Không kết nối được service tại {url}",
                "status": 503
            }

# ── Endpoints ──────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "core-business",
        "version": SERVICE_VERSION,
        "ai_service": AI_SERVICE_URL,
        "time": datetime.now(timezone.utc).isoformat()
    }

@app.post("/policy/access-check", dependencies=[Depends(verify_token)])
def access_check(req: AccessCheckRequest):
    policy = next(
        (p for p in POLICIES.values() if p["gateId"] == req.gateId and p["active"]),
        None
    )
    if not policy:
        return {
            "cardId": req.cardId, "gateId": req.gateId,
            "decision": "DENY",
            "reason": "No active policy for this gate",
            "policyId": None,
            "checkedAt": datetime.now(timezone.utc).isoformat()
        }
    return {
        "cardId": req.cardId, "gateId": req.gateId,
        "decision": "ALLOW", "reason": None,
        "policyId": policy["policyId"],
        "checkedAt": datetime.now(timezone.utc).isoformat()
    }

@app.get("/policy/rules", dependencies=[Depends(verify_token)])
def get_policy_rules(limit: int = 20, gateId: Optional[str] = None):
    rules = list(POLICIES.values())
    if gateId:
        rules = [r for r in rules if r["gateId"] == gateId]
    return {"items": rules[:limit], "nextCursor": None, "hasMore": False}

@app.get("/policy/rules/{policyId}", dependencies=[Depends(verify_token)])
def get_policy_rule(policyId: str):
    policy = POLICIES.get(policyId)
    if not policy:
        raise HTTPException(status_code=404, detail={
            "type": "https://campus.local/errors/not-found",
            "title": "Not Found", "status": 404,
            "detail": f"Policy {policyId} not found",
            "instance": f"/policy/rules/{policyId}", "errors": []
        })
    return policy

@app.post("/access-log", status_code=201, dependencies=[Depends(verify_token)])
def create_access_log(req: AccessLogRequest):
    log_id = str(uuid.uuid4())
    accepted_at = datetime.now(timezone.utc).isoformat()
    ACCESS_LOGS.append({"logId": log_id, **req.model_dump(), "acceptedAt": accepted_at})
    return {"logId": log_id, "acceptedAt": accepted_at}

@app.post("/ai/predict", dependencies=[Depends(verify_token)])
async def proxy_ai_predict(req: AccessCheckRequest):
    """
    Proxy gọi AI Vision service.
    Có timeout 5s và xử lý lỗi đầy đủ — không treo vô hạn.
    """
    result = await call_external(
        url=f"{AI_SERVICE_URL}/predict",
        payload={"cardId": req.cardId},
        timeout=AI_TIMEOUT
    )

    # Nếu AI service lỗi, vẫn trả response hợp lệ thay vì crash
    if "error" in result:
        return JSONResponse(
            status_code=503,
            media_type="application/problem+json",
            content={
                "type": "https://campus.local/errors/dependency-unavailable",
                "title": "AI Service Unavailable",
                "status": 503,
                "detail": result.get("message", "AI service không khả dụng"),
                "instance": "/ai/predict",
                "errors": []
            }
        )
    return result