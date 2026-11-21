# Spike: Strands Agents + AG-UI chạy local (2026-11-21)

Kết quả đầy đủ: `c:\moMo\docs\research\spike-strands-agui-local.md`. Thư mục này là code để chạy lại.

## Cài đặt (Windows, Git Bash hoặc PowerShell)

```bash
cd spikes/strands-agui-local
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.lock.txt   # bản đã chạy được
# hoặc bản mới nhất:  uv pip install --python .venv/Scripts/python.exe strands-agents ag-ui-strands ag-ui-protocol fastapi uvicorn httpx mcp "botocore[crt]"
export PYTHONUTF8=1 PYTHONUNBUFFERED=1      # PowerShell: $env:PYTHONUTF8=1
```

- Credential AWS có sẵn (`aws login`) cần `botocore[crt]`, nếu thiếu sẽ lỗi `MissingDependencyException`.
- Model mặc định: `global.anthropic.claude-haiku-4-5-20251001-v1:0` ở `ap-southeast-1`. Đổi bằng biến môi trường
  `SPIKE_MODEL`, `SPIKE_REGION` (xem `common.py`).
- Dữ liệu hũ trong `common.py` là giả.

## Script theo mục

| Mục | Lệnh | Gọi model? |
|---|---|---|
| 1 agent + tool + `limits` | `python s1_basic_tool.py` | có (~8 request) |
| 2 structured output | `python s2_structured.py` (2a-2c) rồi `python s2b_structured_errors.py d\|e\|g` | có |
| 2 (tiếp) không đặt `limits` thì vòng lặp | `python s2c_unbounded.py` (tự dừng sau 6 lần gọi model) | có |
| 3 streaming | `python s3_streaming.py` | có |
| 4, 8 server tối thiểu bằng `create_strands_app` | `python server_simple.py --port 8102 --origins http://localhost:5173` rồi `curl -N -X POST http://127.0.0.1:8102/invocations -H "Content-Type: application/json" -d @request.json` | có |
| 5, 6, 7, 8 server nhiều route | `python server.py --port 8101 --origins http://localhost:5173` rồi `python agui_call.py <route> "<câu hỏi>" --thread T` | có |
| 7 interrupt thuần Strands | `python s7a_native_interrupt.py tool\|hitl` | có |
| 9 MCP | `python mcp_server.py 8201` (cửa sổ khác) rồi `python s9_mcp_client.py [agent]` | chỉ khi có `agent` |

Route của `server.py`: `/base`, `/ui_custom` (CUSTOM), `/ui_activity` (ACTIVITY_SNAPSHOT), `/ui_state` (STATE_SNAPSHOT từ
`state_from_result`), `/ui_delta` (STATE_DELTA), `/ui_all` (gộp, chưa chạy), `/ui_gen` (tool async-generator yield state), `/ui_stream`
(tool async-generator + `tool_stream_event_handler`, cách nên dùng), `/structured`, `/structured2`, `/interrupt`
(`tool_context.interrupt` + `FileSessionManager`), `/interrupt_nosm` (không session manager), `/interrupt_hook`
(`ToolBehavior(interrupt_on_call=True)`), `/interrupt_hitl` (`HumanInTheLoop`, không dùng được qua adapter).

Trong Git Bash, truyền route KHÔNG có dấu `/` đầu (`agui_call.py ui_custom ...`) vì Git Bash đổi `/ui_custom` thành đường dẫn Windows.

Thử interrupt qua restart tiến trình:
1. `python agui_call.py interrupt "Chuyển 300000 đồng từ hũ giai_tri sang hũ an_uong" --thread t1` (lấy `interrupts[0].id` trong `RUN_FINISHED`)
2. Tắt server (`Ctrl+C`), bật lại với cùng `--session-dir`.
3. `python agui_call.py interrupt "" --thread t1 --resume '[{"interruptId":"<id>","status":"resolved","payload":{"approved":true}}]'`
4. `logs/pre_interrupt.log` có hai dòng khác pid (code trước `interrupt()` chạy lại).

## Tệp

- `out/sse_*.txt`: luồng SSE nguyên bản của từng lần thử; `out/out_s*.txt`: kết quả script; `show_sse.py file` in rút gọn.
- `logs/`: log phía server (pid trước/sau interrupt, kiểu `result_data`, ...).
- Mọi server đã được tắt sau khi chạy xong; không có tài nguyên AWS nào được tạo.
