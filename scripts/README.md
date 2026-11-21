# scripts/

Script triển khai và tiện ích (deploy frontend, nạp dữ liệu persona, đặt lại tài khoản demo...). Proposal §14, §13 (nút đặt lại cho giám khảo).

- `gen_contracts.mjs`: sinh Zod (`frontend/src/contracts/blocks.ts`) từ `contracts/blocks/*.schema.json`; `--check` báo lệch. Xem [contracts/README.md](../contracts/README.md).
