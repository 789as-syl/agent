"""测试SSE聊天运行的脚本"""
import asyncio
import json
import httpx

BASE_URL = "http://localhost:8000/api/v1"

async def test_sse_chat():
    # 1. 登录获取token
    async with httpx.AsyncClient() as client:
        login_response = await client.post(
            f"{BASE_URL}/auth/login",
            json={"phone": "13800138000", "password": "password123"}
        )
        print(f"Login response: {login_response.status_code}")
        if login_response.status_code != 200:
            print(f"Login failed: {login_response.text}")
            return
        
        token = login_response.json()["access_token"]
        print(f"Token: {token[:20]}...")
        
        # 2. 创建会话
        conv_response = await client.post(
            f"{BASE_URL}/conversations",
            json={"title": "Test Conversation"},
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"Create conversation: {conv_response.status_code}")
        if conv_response.status_code != 200:
            print(f"Failed to create conversation: {conv_response.text}")
            return
        
        conv_id = conv_response.json()["id"]
        print(f"Conversation ID: {conv_id}")
        
        # 3. 创建聊天运行
        run_response = await client.post(
            f"{BASE_URL}/conversations/{conv_id}/runs",
            json={"query": "你好，请介绍一下你自己"},
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"Create run: {run_response.status_code}")
        if run_response.status_code != 200:
            print(f"Failed to create run: {run_response.text}")
            return
        
        run_id = run_response.json()["run_id"]
        print(f"Run ID: {run_id}")
        
        # 4. 连接SSE流
        print("\n=== Connecting to SSE stream ===")
        async with client.stream(
            "GET",
            f"{BASE_URL}/conversations/{conv_id}/runs/{run_id}/stream",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0
        ) as response:
            print(f"SSE response status: {response.status_code}")
            print(f"Content-Type: {response.headers.get('content-type')}")
            
            event_count = 0
            async for line in response.aiter_lines():
                if line:
                    print(f"Line: {line}")
                    if line.startswith("data:"):
                        event_count += 1
                        data = line[5:].strip()
                        try:
                            event_data = json.loads(data)
                            print(f"Event #{event_count}: {event_data.get('event_type')}")
                            print(f"  Data: {json.dumps(event_data.get('trace_data', {}), ensure_ascii=False)[:200]}")
                        except json.JSONDecodeError as e:
                            print(f"  Failed to parse: {e}")
                    
                    if "done" in line or "error" in line:
                        print("\n=== Stream completed ===")
                        break
            
            print(f"\nTotal events received: {event_count}")

if __name__ == "__main__":
    asyncio.run(test_sse_chat())
