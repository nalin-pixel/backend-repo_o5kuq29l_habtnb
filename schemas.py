"""
Database Schemas for Expense Tracker

Each Pydantic model maps to a MongoDB collection (lowercased class name).
- Expense -> "expense"
- Category -> "category"
- Budget -> "budget"

These schemas are used for request validation and documentation.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Dict, Literal
from datetime import datetime

PaymentMethod = Literal["cash", "card", "bank", "wallet", "other"]

class Category(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Category name")
    icon: Optional[str] = Field(None, description="Icon identifier (e.g., emoji or lucide name)")
    color: Optional[str] = Field(None, description="Hex or tailwind color key")
    is_custom: bool = Field(True, description="Whether this category was created by the user")

class Expense(BaseModel):
    amount: float = Field(..., gt=0, description="Expense amount")
    category_id: Optional[str] = Field(None, description="Linked category id (ObjectId as string)")
    category_name: Optional[str] = Field(None, description="Denormalized category name for quick lookup")
    description: Optional[str] = Field(None, max_length=300)
    payment_method: PaymentMethod = Field("other")
    date: datetime = Field(default_factory=datetime.utcnow)
    attachment_url: Optional[str] = Field(None, description="URL to receipt image if uploaded elsewhere")

class Budget(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="Target month in YYYY-MM format")
    amount: float = Field(..., gt=0, description="Monthly budget amount")
    per_category: Optional[Dict[str, float]] = Field(
        default=None, description="Optional mapping category_id -> budget amount"
    )
