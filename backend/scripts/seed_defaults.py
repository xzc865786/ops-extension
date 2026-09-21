"""Idempotent seed for cost centers, expense category labels (via meta), payment accounts."""
from __future__ import annotations

import sys
from pathlib import Path

# allow running as `python -m scripts.seed_defaults` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.common.enums import COST_CENTER_SEEDS
from app.db.models.expense import CostCenter, PaymentAccount
from app.db.session import SessionLocal


def seed() -> None:
    db = SessionLocal()
    try:
        for code, name in COST_CENTER_SEEDS:
            existing = db.scalar(select(CostCenter).where(CostCenter.code == code))
            if existing:
                existing.name = name
                existing.enabled = True
            else:
                db.add(CostCenter(code=code, name=name, enabled=True))

        samples = [
            ("公司公户-示例", "COMPANY_BANK", "****1234", "公司"),
            ("支付宝-对公示例", "ALIPAY", "corp@example.com", "公司"),
            ("个人垫付收款-示例", "PERSONAL_BANK", "****5678", "员工"),
        ]
        for name, atype, masked, owner in samples:
            exists = db.scalar(select(PaymentAccount).where(PaymentAccount.name == name))
            if not exists:
                db.add(
                    PaymentAccount(
                        name=name,
                        account_type=atype,
                        account_no_masked=masked,
                        owner_label=owner,
                        enabled=True,
                    )
                )
        db.commit()
        print("seed_defaults: ok")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
