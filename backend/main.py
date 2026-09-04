import os
import json
import math
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_PATH = "data/failed_payments.csv"
AUDIT_LOG_PATH = "logs/audit_log.json"

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

import base64

def razorpay_create_order(amount_in_inr: int, currency: str = "INR") -> Dict[str, Any]:
    # Basic auth for Razorpay
    key_secret = f"{RAZORPAY_KEY_ID}:{RAZORPAY_KEY_SECRET}"
    auth_header = "Basic " + base64.b64encode(key_secret.encode()).decode()
    url = "https://api.razorpay.com/v1/orders"
    payload = {
        "amount": amount_in_inr * 100,  # Razorpay expects amount in paise
        "currency": currency,
        "receipt": f"rec_{datetime.utcnow().timestamp()}",
    }
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()

def load_audit_log() -> List[Dict[str, Any]]:
    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    with open(AUDIT_LOG_PATH, "r") as f:
        return json.load(f)

def save_audit_log(log: List[Dict[str, Any]]):
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    with open(AUDIT_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)

def compute_recovery_score_and_action(row: pd.Series) -> Dict[str, Any]:
    amount = float(row["amount"])
    attempt_count = int(row.get("attempt_count", 0))
    failure_reason = str(row.get("failure_reason", "")).lower()

    # Simple interpretable scoring
    score = 0.0
    reason_parts = []

    # Attempt count
    if attempt_count == 0:
        score += 0.3
        reason_parts.append("no previous attempts")
    elif attempt_count == 1:
        score += 0.2
        reason_parts.append("only one prior attempt")
    else:
        score += 0.05
        reason_parts.append("multiple prior attempts")

    # Failure reason
    if "timeout" in failure_reason or "upi" in failure_reason:
        score += 0.25
        reason_parts.append("likely transient (UPI/timeout)")
    elif "insufficient" in failure_reason:
        score += 0.15
        reason_parts.append("insufficient funds (moderate recovery chance)")
    elif "declined" in failure_reason or "fraud" in failure_reason:
        score += 0.05
        reason_parts.append("hard decline / possible fraud")
    else:
        score += 0.1
        reason_parts.append("generic failure")

    # Amount band
    if amount >= 5000:
        score += 0.15
        reason_parts.append("high value")
    elif amount >= 1000:
        score += 0.1
        reason_parts.append("medium value")
    else:
        score += 0.05
        reason_parts.append("low value")

    score = min(1.0, max(0.0, score))

    # Policy-based action
    max_retries = 2
    max_contacts = 3

    if attempt_count >= max_retries:
        action = "manual_review"
        reason_parts.append("retry limit reached -> manual review")
    elif amount >= 10000 and attempt_count >= 1:
        action = "manual_review"
        reason_parts.append("high value + prior attempts -> manual review")
    else:
        if score >= 0.6:
            action = "retry"
        elif score >= 0.35:
            action = "email"
        else:
            action = "whatsapp"

    return {
        "recovery_score": round(score, 3),
        "recommended_action": action,
        "reason": "; ".join(reason_parts),
    }

def simulate_outcome(action: str, amount: float) -> Dict[str, Any]:
    # Simple simulation for demo purposes
    base_probs = {
        "retry": 0.55,
        "email": 0.35,
        "whatsapp": 0.45,
        "manual_review": 0.7,
    }
    p = base_probs.get(action, 0.4)
    # Slight amount effect
    if amount >= 5000:
        p *= 0.9
    p = min(0.95, max(0.1, p))
    success = random.random() < p
    return {
        "success": success,
        "recovered_amount": amount if success else 0.0,
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/load-data")
async def load_data(file: UploadFile = File(...)):
    contents = await file.read()
    df = pd.read_csv(io.BytesIO(contents))
    required_cols = ["payment_id", "amount", "failure_reason"]
    for col in required_cols:
        if col not in df.columns:
            raise HTTPException(status_code=400, detail=f"Missing column: {col}")
    df.to_csv(DATA_PATH, index=False)
    return {"status": "ok", "rows": len(df)}

@app.get("/api/payments")
def get_payments():
    if not os.path.exists(DATA_PATH):
        # Load default synthetic data if none uploaded
        df = generate_synthetic_data()
        os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
        df.to_csv(DATA_PATH, index=False)
    df = pd.read_csv(DATA_PATH)
    rows = []
    for _, row in df.iterrows():
        scoring = compute_recovery_score_and_action(row)
        rows.append({
            "payment_id": row["payment_id"],
            "customer_email": row.get("customer_email", ""),
            "amount": float(row["amount"]),
            "currency": row.get("currency", "INR"),
            "failure_reason": row["failure_reason"],
            "attempt_count": int(row.get("attempt_count", 0)),
            "last_attempt_at": row.get("last_attempt_at", ""),
            "subscription_id": row.get("subscription_id", ""),
            **scoring,
        })
    return {"payments": rows}

@app.post("/api/approve-action")
def approve_action(payload: Dict[str, Any]):
    payment_id = payload["payment_id"]
    action = payload["action"]
    amount = float(payload["amount"])
    currency = payload.get("currency", "INR")

    # Policy check (re-implement key rules for safety)
    df = pd.read_csv(DATA_PATH)
    row = df[df["payment_id"] == payment_id]
    if row.empty:
        raise HTTPException(status_code=404, detail="Payment not found")
    row = row.iloc[0]
    attempt_count = int(row.get("attempt_count", 0))

    max_retries = 2
    if action == "retry" and attempt_count >= max_retries:
        raise HTTPException(status_code=400, detail="Retry not allowed: max retries reached")

    order_id = None
    if action == "retry":
        try:
            order_resp = razorpay_create_order(int(amount), currency)
            order_id = order_resp.get("id")
        except Exception:
            # In case Razorpay keys not set, still allow demo
            order_id = f"fake_order_{payment_id}"

    outcome = simulate_outcome(action, amount)

    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "payment_id": payment_id,
        "action": action,
        "amount": amount,
        "currency": currency,
        "order_id": order_id,
        "outcome_success": outcome["success"],
        "recovered_amount": outcome["recovered_amount"],
    }

    audit_log = load_audit_log()
    audit_log.append(log_entry)
    save_audit_log(audit_log)

    return log_entry

@app.get("/api/audit-log")
def get_audit_log():
    return {"audit_log": load_audit_log()}

@app.get("/api/metrics")
def get_metrics():
    audit_log = load_audit_log()
    if not audit_log:
        return {
            "total_failed": 0,
            "total_recovered_count": 0,
            "total_recovered_amount": 0.0,
            "recovery_rate": 0.0,
            "baseline_recovery_rate": 0.0,
        }

    total_failed = len(audit_log)
    recovered_rows = [e for e in audit_log if e.get("outcome_success", False)]
    total_recovered_count = len(recovered_rows)
    total_recovered_amount = sum(e.get("recovered_amount", 0.0) for e in recovered_rows)

    recovery_rate = total_recovered_count / total_failed if total_failed else 0.0

    # Baseline: assume naive "always retry once" with 40% success
    baseline_recovery_rate = 0.4

    return {
        "total_failed": total_failed,
        "total_recovered_count": total_recovered_count,
        "total_recovered_amount": total_recovered_amount,
        "recovery_rate": round(recovery_rate, 3),
        "baseline_recovery_rate": baseline_recovery_rate,
    }

def generate_synthetic_data(n: int = 100) -> pd.DataFrame:
    random.seed(42)
    rows = []
    reasons = [
        "upi_timeout",
        "insufficient_funds",
        "card_declined",
        "network_error",
        "fraud_suspected",
    ]
    now = datetime.utcnow()
    for i in range(n):
        amount = random.choice([199, 299, 499, 999, 1499, 2999, 4999, 7999])
        attempt_count = random.choices([0, 1, 2, 3], weights=[0.2, 0.4, 0.3, 0.1])[0]
        reason = random.choice(reasons)
        last_attempt = now - timedelta(days=random.randint(0, 7), hours=random.randint(0, 23))
        rows.append({
            "payment_id": f"pay_{i+1:04d}",
            "customer_email": f"user{i+1}@example.com",
            "amount": amount,
            "currency": "INR",
            "failure_reason": reason,
            "attempt_count": attempt_count,
            "last_attempt_at": last_attempt.isoformat(),
            "subscription_id": f"sub_{(i%20)+1:03d}",
        })
    return pd.DataFrame(rows)

# Fix: import io for file handling
import io
