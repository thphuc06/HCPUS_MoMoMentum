"""Persona demo: bộ sinh dữ liệu seed tất định và ánh xạ tài khoản -> persona.

Đây là DỮ LIỆU đầu vào nạp vào Aurora (không có API giao dịch thật), không phải mã nghiệp vụ.
Xem generator.py và README.md.
"""

from personas.generator import (
    Materialized,
    MaterializedTx,
    PersonaData,
    PersonaError,
    available_personas,
    generate,
    load_accounts,
    materialize,
    parse_groups_claim,
    persona_from_groups,
)
from personas.out_of_wallet import (
    OutOfWallet,
    OutOfWalletSource,
    OutOfWalletTx,
    generate_out_of_wallet,
    statement_balances,
    statement_csv,
)

__all__ = [
    "Materialized",
    "MaterializedTx",
    "OutOfWallet",
    "OutOfWalletSource",
    "OutOfWalletTx",
    "PersonaData",
    "PersonaError",
    "available_personas",
    "generate",
    "generate_out_of_wallet",
    "load_accounts",
    "materialize",
    "parse_groups_claim",
    "persona_from_groups",
    "statement_balances",
    "statement_csv",
]
