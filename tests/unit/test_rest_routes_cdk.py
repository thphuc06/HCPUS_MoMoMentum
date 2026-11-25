"""Mọi đường dẫn + method của `contracts/rest/openapi.yaml` phải có route trên HTTP API thật (danh sách route trong
`infra-cdk/lib/*.ts`) và, với route nối vào Lambda ledger, phải có nhánh trong `rest_api._dispatch`.

Test cục bộ của REST gọi thẳng `rest_api._dispatch` nên không bắt được route thiếu ở CDK (HTTP API trả 404). Test này đọc
chữ của các file CDK (không synth: ToolsStack cần zip Lambda đã đóng), nên thêm route vào hợp đồng mà quên CDK là đỏ.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from yofina_core.errors import YofinaError

from yofina_ledger import rest_api

REPO = Path(__file__).resolve().parents[2]
CDK_LIB = REPO / "infra-cdk" / "lib"
SPEC = yaml.safe_load((REPO / "contracts" / "rest" / "openapi.yaml").read_text(encoding="utf-8"))
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

# `['/path', apigwv2.HttpMethod.GET]` (tools-stack.ts, memory.ts) và `['POST', '/ingest/...']` (ingest-stack.ts)
_CDK_PAIR = re.compile(r"\[\s*'(/[^']*)'\s*,\s*apigwv2\.HttpMethod\.([A-Z]+)\s*\]")
_INGEST_PAIR = re.compile(r"\[\s*'([A-Z]+)'\s*,\s*'(/[^']*)'\s*\]")
_NOT_FOUND = "Đường dẫn không tồn tại."


def _read(name: str) -> str:
    return (CDK_LIB / name).read_text(encoding="utf-8")


def _section(src: str, start: str, end: str) -> str:
    i = src.index(start)
    return src[i : src.index(end, i)]


def _pairs(text: str) -> set[str]:
    return {f"{m} {p}" for p, m in _CDK_PAIR.findall(text)}


def _const(src: str, name: str) -> str:
    """Thân hằng `export const NAME ... = [...];` (route khai riêng rồi trải vào danh sách)."""
    return _section(src, f"export const {name}", "];")


def _ledger_routes() -> set[str]:
    tools = _read("tools-stack.ts")
    body = _section(tools, "const routes: Array<", "for (const [routePath, method] of routes)")
    out = _pairs(body)
    # hằng trải vào danh sách (`...X_ROUTES,`): tìm ở tools-stack.ts hoặc memory.ts
    for name in re.findall(r"\.\.\.([A-Z_]+_ROUTES)", body):
        for fname in ("tools-stack.ts", "memory.ts"):
            src = _read(fname)
            if f"export const {name}" in src:
                out |= _pairs(_const(src, name))
                break
        else:
            raise AssertionError(f"không tìm thấy hằng {name} trong infra-cdk/lib")
    return out


def _forecast_routes() -> set[str]:
    tools = _read("tools-stack.ts")
    return _pairs(_section(tools, "const forecastRoutes", "for (const [routePath, method] of forecastRoutes)"))


def _ingest_routes() -> set[str]:
    return {f"{m} {p}" for m, p in _INGEST_PAIR.findall(_const(_read("ingest-stack.ts"), "INGEST_ROUTES"))}


def _openapi_routes() -> set[str]:
    return {
        f"{method.upper()} {path}"
        for path, item in SPEC["paths"].items()
        for method in item
        if method in HTTP_METHODS
    }


def test_danh_sach_route_cdk_doc_duoc():
    # bảo đảm bộ đọc chữ không im lặng trả rỗng khi ai đó đổi cách viết danh sách
    assert "GET /cashflow" in _ledger_routes()
    assert "DELETE /memory" in _ledger_routes()
    assert "POST /affordability" in _forecast_routes()
    assert "POST /ingest/uploads" in _ingest_routes()


def test_moi_route_cua_openapi_co_tren_http_api_cua_cdk():
    cdk = _ledger_routes() | _forecast_routes() | _ingest_routes()
    missing = sorted(_openapi_routes() - cdk)
    assert not missing, f"openapi.yaml có route mà CDK không nối (HTTP API sẽ trả 404): {missing}"


def test_cdk_khong_noi_route_ngoai_hop_dong():
    cdk = _ledger_routes() | _forecast_routes() | _ingest_routes()
    extra = sorted(cdk - _openapi_routes())
    assert not extra, f"CDK nối route không có trong openapi.yaml: {extra}"


def test_moi_route_chi_noi_vao_mot_lambda():
    ledger, forecast, ingest = _ledger_routes(), _forecast_routes(), _ingest_routes()
    assert not (ledger & forecast), ledger & forecast
    assert not (ledger & ingest), ledger & ingest
    assert not (forecast & ingest), forecast & ingest


def _concrete(path: str) -> tuple[str, dict[str, str]]:
    """Thay `{tham_số}` bằng giá trị đúng dạng (uuid cho id, số cho version) để nhánh định tuyến chạy tới handler."""
    params: dict[str, str] = {}

    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        value = "1" if name == "version" else "00000000-0000-4000-8000-000000000001"
        if name == "jar_code":
            value = "an_uong"
        params[name] = value
        return value

    return re.sub(r"\{([a-z_]+)\}", sub, path), params


def _dispatch_route(route: str) -> None:
    method, path = route.split(" ", 1)
    raw, params = _concrete(path)
    event = {
        "rawPath": raw,
        "requestContext": {"http": {"method": method, "path": raw}, "authorizer": {"jwt": {"claims": {"sub": "s"}}}},
        "pathParameters": params,
        "queryStringParameters": {},
        "body": "{}",
    }
    try:
        rest_api._dispatch(f"{method} {raw}", event, "s", "t" * 32, MagicMock())
    except YofinaError as exc:
        if exc.message == _NOT_FOUND:
            raise
    except Exception:  # noqa: BLE001 - handler chạy với service giả; chỉ cần đã qua bước định tuyến
        pass


def test_route_khong_co_trong_rest_api_bi_bat():
    with pytest.raises(YofinaError, match=_NOT_FOUND):
        _dispatch_route("POST /jars/khong-co")


@pytest.mark.parametrize("route", sorted(_ledger_routes()))
def test_moi_route_cdk_cua_ledger_co_nhanh_trong_rest_api(route: str):
    try:
        _dispatch_route(route)
    except YofinaError as exc:
        pytest.fail(f"rest_api không có nhánh cho {route}: {exc.message}")
