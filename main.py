import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Expense, Category, Budget

app = FastAPI(title="Expense Tracker API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------
# Helpers
# ------------------------------

def to_str_id(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    d = {**doc}
    if d.get("_id") is not None:
        d["id"] = str(d.pop("_id"))
    # Serialize nested ObjectIds if present (e.g., category_id)
    if d.get("category_id") and isinstance(d["category_id"], ObjectId):
        d["category_id"] = str(d["category_id"])
    return d


def parse_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


# ------------------------------
# Health & Schema
# ------------------------------

@app.get("/")
def read_root():
    return {"message": "Expense Tracker Backend Running"}


@app.get("/api/health")
def health():
    return {
        "backend": "ok",
        "database": "connected" if db is not None else "unavailable",
    }


@app.get("/schema")
def get_schema():
    # Minimal schema export for Flames data viewer compatibility
    return {
        "expense": Expense.model_json_schema(),
        "category": Category.model_json_schema(),
        "budget": Budget.model_json_schema(),
    }


# ------------------------------
# Category Endpoints
# ------------------------------

DEFAULT_CATEGORIES = [
    {"name": "Food", "icon": "Utensils", "color": "rose", "is_custom": False},
    {"name": "Transport", "icon": "Car", "color": "sky", "is_custom": False},
    {"name": "Bills", "icon": "Receipt", "color": "amber", "is_custom": False},
    {"name": "Shopping", "icon": "ShoppingCart", "color": "violet", "is_custom": False},
    {"name": "Health", "icon": "Heart", "color": "emerald", "is_custom": False},
    {"name": "Entertainment", "icon": "Music", "color": "indigo", "is_custom": False},
    {"name": "Travel", "icon": "Plane", "color": "cyan", "is_custom": False},
]


@app.get("/api/categories")
def list_categories():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    items = list(db["category"].find({}))
    if not items:
        # seed defaults
        db["category"].insert_many(DEFAULT_CATEGORIES)
        items = list(db["category"].find({}))
    return [to_str_id(it) for it in items]


@app.post("/api/categories")
def create_category(payload: Category):
    cid = create_document("category", payload)
    doc = db["category"].find_one({"_id": ObjectId(cid)})
    return to_str_id(doc)


@app.put("/api/categories/{category_id}")
def update_category(category_id: str, payload: Category):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    oid = parse_object_id(category_id)
    res = db["category"].update_one({"_id": oid}, {"$set": payload.model_dump() | {"updated_at": datetime.utcnow()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    doc = db["category"].find_one({"_id": oid})
    return to_str_id(doc)


@app.delete("/api/categories/{category_id}")
def delete_category(category_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    oid = parse_object_id(category_id)
    res = db["category"].delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"status": "deleted"}


# ------------------------------
# Expense Endpoints
# ------------------------------

class ExpenseCreate(Expense):
    pass


@app.get("/api/expenses")
def list_expenses(
    q: Optional[str] = None,
    category_id: Optional[str] = None,
    payment_method: Optional[str] = None,
    date_from: Optional[str] = Query(None, description="ISO date, e.g., 2024-01-01"),
    date_to: Optional[str] = Query(None, description="ISO date, e.g., 2024-01-31"),
    limit: int = Query(50, ge=1, le=500),
):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    filt: Dict[str, Any] = {}
    if q:
        filt["description"] = {"$regex": q, "$options": "i"}
    if category_id:
        try:
            filt["category_id"] = ObjectId(category_id)
        except Exception:
            filt["category_id"] = category_id
    if payment_method:
        filt["payment_method"] = payment_method
    if date_from or date_to:
        date_q: Dict[str, Any] = {}
        if date_from:
            date_q["$gte"] = datetime.fromisoformat(date_from)
        if date_to:
            # include full day
            dt = datetime.fromisoformat(date_to)
            date_q["$lte"] = dt + timedelta(days=1)
        filt["date"] = date_q

    items = db["expense"].find(filt).sort("date", -1).limit(limit)
    return [to_str_id(it) for it in items]


@app.post("/api/expenses")
def create_expense(payload: ExpenseCreate):
    data = payload.model_dump()
    # If category_id is string -> store as ObjectId when valid
    cat_id = data.get("category_id")
    if cat_id:
        try:
            data["category_id"] = ObjectId(cat_id)
        except Exception:
            pass
    eid = create_document("expense", data)
    doc = db["expense"].find_one({"_id": ObjectId(eid)})
    return to_str_id(doc)


@app.get("/api/expenses/{expense_id}")
def get_expense(expense_id: str):
    oid = parse_object_id(expense_id)
    doc = db["expense"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Expense not found")
    return to_str_id(doc)


@app.put("/api/expenses/{expense_id}")
def update_expense(expense_id: str, payload: Expense):
    oid = parse_object_id(expense_id)
    data = payload.model_dump()
    if data.get("category_id"):
        try:
            data["category_id"] = ObjectId(data["category_id"])  # may raise
        except Exception:
            pass
    res = db["expense"].update_one({"_id": oid}, {"$set": data | {"updated_at": datetime.utcnow()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
    doc = db["expense"].find_one({"_id": oid})
    return to_str_id(doc)


@app.delete("/api/expenses/{expense_id}")
def delete_expense(expense_id: str):
    oid = parse_object_id(expense_id)
    res = db["expense"].delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
    return {"status": "deleted"}


# ------------------------------
# Budget Endpoints
# ------------------------------

@app.get("/api/budgets/{month}")
def get_budget(month: str):
    # month format YYYY-MM
    doc = db["budget"].find_one({"month": month}) if db else None
    return to_str_id(doc) if doc else None


class BudgetUpsert(Budget):
    pass


@app.put("/api/budgets/{month}")
def upsert_budget(month: str, payload: BudgetUpsert):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    data = payload.model_dump()
    data["month"] = month
    db["budget"].update_one({"month": month}, {"$set": data, "$setOnInsert": {"created_at": datetime.utcnow()}}, upsert=True)
    doc = db["budget"].find_one({"month": month})
    return to_str_id(doc)


@app.get("/api/budgets/{month}/usage")
def budget_usage(month: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    # compute month range
    start = datetime.fromisoformat(month + "-01")
    # naive month end calculation
    if start.month == 12:
        end = datetime(start.year + 1, 1, 1)
    else:
        end = datetime(start.year, start.month + 1, 1)
    exp_sum = list(
        db["expense"].aggregate([
            {"$match": {"date": {"$gte": start, "$lt": end}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ])
    )
    total_spent = (exp_sum[0]["total"] if exp_sum else 0.0)
    budget = db["budget"].find_one({"month": month})
    amount = budget.get("amount", 0) if budget else 0
    pct = (total_spent / amount * 100) if amount else 0
    level = None
    if amount:
        if pct >= 100:
            level = "100"
        elif pct >= 80:
            level = "80"
        elif pct >= 50:
            level = "50"
    return {
        "month": month,
        "budget": amount,
        "spent": round(total_spent, 2),
        "percent": round(pct, 2),
        "alert": level,
    }


# ------------------------------
# Dashboard & Analytics
# ------------------------------

@app.get("/api/dashboard")
def dashboard(period: str = Query("month", pattern="^(day|week|month|year)$")):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    now = datetime.utcnow()
    if period == "day":
        start = datetime(now.year, now.month, now.day)
    elif period == "week":
        start = datetime(now.year, now.month, now.day) - timedelta(days=now.weekday())
    elif period == "month":
        start = datetime(now.year, now.month, 1)
    else:
        start = datetime(now.year, 1, 1)

    total = list(
        db["expense"].aggregate([
            {"$match": {"date": {"$gte": start}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ])
    )
    total_spent = total[0]["total"] if total else 0.0

    # recent transactions
    recent = [to_str_id(x) for x in db["expense"].find({}).sort("date", -1).limit(10)]

    # category breakdown
    cat_pipeline = [
        {"$match": {"date": {"$gte": start}}},
        {"$group": {"_id": "$category_id", "total": {"$sum": "$amount"}}},
        {"$sort": {"total": -1}},
    ]
    breakdown = list(db["expense"].aggregate(cat_pipeline))
    # Map category names
    cats = {c["_id"]: c for c in db["category"].find({})}
    breakdown_fmt = []
    for item in breakdown:
        cid = item.get("_id")
        name = None
        if isinstance(cid, ObjectId) and cid in cats:
            name = cats[cid].get("name")
        breakdown_fmt.append({
            "category_id": str(cid) if cid else None,
            "category_name": name,
            "total": round(item.get("total", 0.0), 2),
        })

    return {
        "period": period,
        "total_spent": round(total_spent, 2),
        "recent": recent,
        "breakdown": breakdown_fmt,
    }


@app.get("/api/analytics/monthly")
def analytics_monthly(year: int = datetime.utcnow().year):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    results = []
    for m in range(1, 13):
        start = datetime(year, m, 1)
        end = datetime(year + 1, 1, 1) if m == 12 else datetime(year, m + 1, 1)
        agg = list(db["expense"].aggregate([
            {"$match": {"date": {"$gte": start, "$lt": end}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]))
        total = agg[0]["total"] if agg else 0.0
        results.append({"month": f"{year}-{m:02d}", "total": round(total, 2)})
    return results


# ------------------------------
# Legacy test endpoint kept for diagnostics
# ------------------------------

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
