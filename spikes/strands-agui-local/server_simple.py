"""Server AG-UI tối thiểu bằng create_strands_app (API chính thức của ag-ui-strands).

Chạy: python server_simple.py --port 8102 [--origins http://localhost:5173]
Gọi:  curl -N -X POST http://127.0.0.1:8102/invocations -H "Content-Type: application/json" -d @request.json
"""
import argparse
import uvicorn
from strands import Agent, tool
from ag_ui_strands import StrandsAgent, create_strands_app
from common import model, JARS


@tool
def get_jar_balances() -> dict:
    """Lấy số dư hiện tại của các hũ chi tiêu của người dùng (VND)."""
    return {k: v for k, v in JARS.items()}


agent = Agent(model=model(512), system_prompt="Trợ lý Yofina, trả lời ngắn tiếng Việt, dùng tool để lấy số.",
              tools=[get_jar_balances], callback_handler=None)
agui = StrandsAgent(agent=agent, name="yofina", description="Hũ nhìn trước")

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8102)
ap.add_argument("--origins", nargs="*", default=None)
args = ap.parse_args()
app = create_strands_app(agui, "/invocations", "/ping", origins=args.origins or None,
                         allow_headers=["authorization", "content-type",
                                        "x-amzn-bedrock-agentcore-runtime-session-id"])
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
