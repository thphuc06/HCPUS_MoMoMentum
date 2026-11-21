from yofina_core.errors import HTTP_STATUS, ErrorCode, ToolStatus


def test_moi_ma_loi_co_http_status():
    assert set(HTTP_STATUS) == set(ErrorCode)
    assert all(400 <= s < 600 for s in HTTP_STATUS.values())


def test_tool_status_khop_ket_qua_tool():
    assert {s.value for s in ToolStatus} == {"OK", "NEEDS_CONFIRMATION", "ERROR"}
    assert ErrorCode.NEEDS_CONFIRMATION.value == ToolStatus.NEEDS_CONFIRMATION.value
