from typing import Literal
from pydantic import BaseModel, Field

class IntentResult(BaseModel):
    intent: Literal["lookup", "what_if", "affordability", "move_money", "roadmap", "out_of_scope"]
    confidence: float = Field(ge=0, le=1, description="Độ chắc chắn 0..1")
    needs_clarification: bool = False
    clarification_question: str | None = None
    amount_vnd: int | None = Field(default=None, ge=0, description="Số tiền VND, số nguyên không âm")

class PaymentPlan(BaseModel):
    method: Literal["lump_sum", "installment", "bnpl"]
    installments: int = Field(default=1, ge=1, le=36)

class ScenarioSpec(BaseModel):
    amount_vnd: int = Field(ge=0, description="Số tiền khoản chi, VND, số nguyên >= 0")
    jar: Literal["an_uong", "di_lai", "giai_tri", "tiet_kiem"] = Field(description="Hũ bị trừ")
    payment: PaymentPlan
    start_date: str = Field(description="Ngày bắt đầu ISO 8601 YYYY-MM-DD")
    constraints: list[str] = Field(default_factory=list, description="Ràng buộc người dùng nêu")
