"""注册用户并测试SSE聊天"""
import asyncio
import json
import httpx

BASE_URL = "http://localhost:8000/api/v1"

async def register_and_test():
    async with httpx.AsyncClient() as client:
        # 1. 注册用户
        print("=== Registering user ===")
        register_response = await client.post(
            f"{BASE_URL}/auth/register",
            json={"phone": "13900139000", "password": "Password123"}
        )
        print(f"Register response: {register_response.status_code}")
        print(f"Response: {register_response.text}")
        
        if register_response.status_code not in [200, 201, 409]:  # 409 = already exists
            print("Registration failed")
            return
        
        # 2. 登录
        print("\n=== Logging in ===")
        login_response = await client.post(
            f"{BASE_URL}/auth/login",
            json={"phone": "13900139000", "password": "Password123"}
        )
        print(f"Login response: {login_response.status_code}")
        if login_response.status_code != 200:
            print(f"Login failed: {login_response.text}")
            return
        
        token = login_response.json()["access_token"]
        print(f"Token obtained: {token[:30]}...")
        
        # 3. 创建会话
        print("\n=== Creating conversation ===")
        conv_response = await client.post(
            f"{BASE_URL}/conversations",
            json={"title": "Test Conversation"},
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"Create conversation: {conv_response.status_code}")
        if conv_response.status_code not in [200, 201]:
            print(f"Failed: {conv_response.text}")
            return
        
        conv_id = conv_response.json()["id"]
        print(f"Conversation ID: {conv_id}")
        
        # 4. 创建聊天运行
        print("\n=== Creating chat run ===")
        run_response = await client.post(
            f"{BASE_URL}/conversations/{conv_id}/runs",
            json={"query": "你好"},
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"Create run: {run_response.status_code}")
        if run_response.status_code not in [200, 201]:
            print(f"Failed: {run_response.text}")
            return
        
        run_id = run_response.json()["run_id"]
        print(f"Run ID: {run_id}")
        
        # 5. 连接SSE流
        print("\n=== Connecting to SSE stream ===")
        try:
            async with client.stream(
                "GET",
                f"{BASE_URL}/conversations/{conv_id}/runs/{run_id}/stream",
                headers={"Authorization": f"Bearer {token}"},
                timeout=60.0
            ) as response:
                print(f"SSE response status: {response.status_code}")
                print(f"Content-Type: {response.headers.get('content-type')}")
                
                event_count = 0
                async for line in response.aiter_lines():
                    if line:
                        print(f"\nLine: {line[:100]}")
                        if line.startswith("data:"):
                            event_count += 1
                            data = line[5:].strip()
                            try:
                                event_data = json.loads(data)
                                event_type = event_data.get('event_type')
                                print(f"✓ Event #{event_count}: {event_type}")
                                trace_data = event_data.get('trace_data', {})
                                if event_type == 'generation_delta':
                                    delta = trace_data.get('delta', '')
                                    print(f"  Delta: {delta[:50]}")
                                elif event_type == 'final_answer':
                                    answer = trace_data.get('answer', '')
                                    print(f"  Answer length: {len(answer)} chars")
                                elif event_type == 'done':
                                    print(f"  Done! Total steps: {trace_data.get('total_steps')}")
                            except json.JSONDecodeError as e:
                                print(f"  ✗ Failed to parse: {e}")
                        
                        if '"event_type":"done"' in line or '"event_type":"error"' in line:
                            print("\n=== Stream completed ===")
                            break
                
                print(f"\n=== Total events received: {event_count} ===")
        except Exception as e:
            print(f"SSE connection error: {e}")

if __name__ == "__main__":
    asyncio.run(register_and_test())
