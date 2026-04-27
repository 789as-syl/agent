"""验证SSE事件不重复的测试脚本"""
import asyncio
import json
import httpx

BASE_URL = "http://localhost:8000/api/v1"

async def test_sse_no_duplicate():
    async with httpx.AsyncClient() as client:
        # 登录
        login_response = await client.post(
            f"{BASE_URL}/auth/login",
            json={"phone": "13900139000", "password": "Password123"}
        )
        if login_response.status_code != 200:
            print(f"Login failed: {login_response.text}")
            return
        
        token = login_response.json()["access_token"]
        
        # 创建会话
        conv_response = await client.post(
            f"{BASE_URL}/conversations",
            json={"title": "Test"},
            headers={"Authorization": f"Bearer {token}"}
        )
        conv_id = conv_response.json()["id"]
        
        # 创建运行
        run_response = await client.post(
            f"{BASE_URL}/conversations/{conv_id}/runs",
            json={"query": "你好"},
            headers={"Authorization": f"Bearer {token}"}
        )
        run_id = run_response.json()["run_id"]
        
        # 连接SSE并统计事件
        print(f"\n=== Testing SSE for duplicates ===")
        print(f"Run ID: {run_id}\n")
        
        event_counts = {}
        total_events = 0
        
        async with client.stream(
            "GET",
            f"{BASE_URL}/conversations/{conv_id}/runs/{run_id}/stream",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60.0
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_type = line.split("event:")[1].strip()
                    event_counts[event_type] = event_counts.get(event_type, 0) + 1
                    total_events += 1
                    # 只显示非delta事件，避免输出过多
                    if event_type != 'generation_delta':
                        print(f"Event #{total_events}: {event_type}")
                    elif event_counts[event_type] == 1:
                        print(f"Event #{total_events}: {event_type} (开始流式输出...)")
                
                if '"event_type":"done"' in line or '"event_type":"error"' in line:
                    break
        
        print(f"\n=== Event Statistics ===")
        print(f"Total events: {total_events}")
        print(f"\nEvent type counts:")
        for event_type, count in sorted(event_counts.items()):
            # generation_delta 会有多个，这是正常的流式输出
            if event_type == 'generation_delta':
                status = "✓" 
                note = " (流式输出，正常)"
            elif count == 1:
                status = "✓"
                note = ""
            else:
                status = "✗ DUPLICATE!"
                note = ""
            print(f"  {status} {event_type}: {count}{note}")
        
        # 检查是否有重复（排除generation_delta）
        has_duplicates = any(
            count > 1 
            for event_type, count in event_counts.items() 
            if event_type != 'generation_delta'
        )
        if has_duplicates:
            print("\n❌ FAILED: Found duplicate events!")
        else:
            print("\n✅ SUCCESS: No duplicate events!")

if __name__ == "__main__":
    asyncio.run(test_sse_no_duplicate())
