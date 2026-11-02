"""
The checkout backend. It checks the order AGAIN, on its own, and never trusts the browser.
The browser's Zod rules and these rules are two separate checks of the same contract.
A shared list of test cases (shared/checkout-cases.json) proves they agree.
"""
import re
from itertools import count
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

MAX_TABLE = 20
ALLOWED_TIPS = (0, 10, 20)

app = FastAPI(title="Kitchen checkout")

# Lets a page served from another address (the Vite dev server) call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


def _is_int(value: Any) -> bool:
    # True and False are ints in Python, so they must be rejected on purpose.
    return isinstance(value, int) and not isinstance(value, bool)


class Checkout(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=60)
    phone: str = Field(pattern=r"^[6-9][0-9]{9}$")  # [0-9], not \d: \d also matches non-ASCII digits
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    orderType: Literal["dine-in", "delivery"]
    # These three depend on orderType, which is declared above, so it is already checked here.
    table: Any = Field(default=None, validate_default=True)
    street: Any = Field(default=None, validate_default=True)
    pincode: Any = Field(default=None, validate_default=True)
    notes: str | None = Field(default=None, max_length=200)
    tip: Any
    acceptTerms: Literal[True]

    @field_validator("table", mode="before")
    @classmethod
    def check_table(cls, v: Any, info: ValidationInfo):
        kind = info.data.get("orderType")
        if kind != "dine-in":
            return None  # not needed for delivery (ignored if sent)
        if not _is_int(v) or not 1 <= v <= MAX_TABLE:
            raise ValueError(f"Choose a table from 1 to {MAX_TABLE}.")
        return v

    @field_validator("street", mode="before")
    @classmethod
    def check_street(cls, v: Any, info: ValidationInfo):
        if info.data.get("orderType") != "delivery":
            return None
        if not isinstance(v, str) or len(v.strip()) < 5:
            raise ValueError("Enter the street address (at least 5 characters).")
        return v.strip()

    @field_validator("pincode", mode="before")
    @classmethod
    def check_pincode(cls, v: Any, info: ValidationInfo):
        if info.data.get("orderType") != "delivery":
            return None
        if not isinstance(v, str) or not re.fullmatch(r"[0-9]{6}", v.strip()):
            raise ValueError("Enter a 6-digit pincode.")
        return v.strip()

    @field_validator("tip", mode="before")
    @classmethod
    def check_tip(cls, v: Any):
        if not _is_int(v) or v not in ALLOWED_TIPS:
            raise ValueError("Choose a tip of 0, 10 or 20.")
        return v


_order_ids = count(1001)


@app.exception_handler(RequestValidationError)
async def validation_problem(_: Request, exc: RequestValidationError):
    """One simple shape: { detail, errors: { field: message } }."""
    errors: dict[str, str] = {}
    for err in exc.errors():
        loc = [p for p in err["loc"] if p != "body"]
        field = str(loc[0]) if loc else "form"
        message = err["msg"].removeprefix("Value error, ")
        errors.setdefault(field, message)
    return JSONResponse(status_code=422, content={"detail": "Please fix the highlighted fields.", "errors": errors})


@app.post("/api/checkout", status_code=201)
def checkout(order: Checkout):
    placed = {
        "orderId": next(_order_ids),
        "name": order.name,
        "orderType": order.orderType,
        "tip": order.tip,
        "notes": order.notes,
    }
    if order.orderType == "dine-in":
        placed["table"] = order.table
    else:
        placed["street"] = order.street
        placed["pincode"] = order.pincode
    return placed


@app.get("/api/health")
def health():
    return {"status": "ok"}
