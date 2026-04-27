"""测试流式输出增量是否正确"""
import asyncio
import json
import httpx

BASE_URL = "http://localhost:8000/api/v1"

async def test_streaming_delta():
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
        
        # 创建运行 - 测试简单问候语
        print("\n=== Test 1: 简单问候语（不应检索）===")
        run_response = await client.post(
            f"{BASE_URL}/conversations/{conv_id}/runs",
            json={"query": "你好"},
            headers={"Authorization": f"Bearer {token}"}
        )
        run_id = run_response.json()["run_id"]
        
        event_counts = {}
        deltas = []
        full_text = ""
        
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
                
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                        if data.get("event_type") == "generation_delta":
                            delta = data["trace_data"]["delta"]
                            deltas.append(delta)
                            full_text += delta
                        elif data.get("event_type") == "agent_thought":
                            print(f"Thought: {data['trace_data']['thought']}")
                            print(f"Reasoning: {data['trace_data']['reasoning']}")
                    except:
                        pass
                
                if '"event_type":"done"' in line:
                    break
        
        print(f"\nEvent counts: {event_counts}")
        print(f"Total delta events: {len(deltas)}")
        print(f"Full response length: {len(full_text)}")
        print(f"Full response:\n{full_text[:200]}...")
        
        # 检查是否有重复
        has_duplicate = False
        for i, delta in enumerate(deltas[:-1]):
            if delta in deltas[i+1]:
                print(f"\n❌ Found duplicate delta[{i}]: {delta}")
                has_duplicate = True
        
        if not has_duplicate:
            print("\n✅ No duplicate deltas found!")
        
        # 测试2: 需要检索的问题
        print("\n\n=== Test 2: 实质性问题（应检索）===")
        run_response2 = await client.post(
            f"{BASE_URL}/conversations/{conv_id}/runs",
            json={"query": "什么是Python编程语言？"},
            headers={"Authorization": f"Bearer {token}"}
        )
        run_id2 = run_response2.json()["run_id"]
        
        event_counts2 = {}
        thought_reasoning = ""
        
        async with client.stream(
            "GET",
            f"{BASE_URL}/conversations/{conv_id}/runs/{run_id2}/stream",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60.0
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_type = line.split("event:")[1].strip()
                    event_counts2[event_type] = event_counts2.get(event_type, 0) + 1
                
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                        if data.get("event_type") == "agent_thought":
                            thought_reasoning = data['trace_data']['reasoning']
                    except:
                        pass
                
                if '"event_type":"done"' in line:
                    break
        
        print(f"Event counts: {event_counts2}")
        print(f"Thought reasoning: {thought_reasoning}")
        
        if 'tool_start' in event_counts2:
            print("✅ Retrieval was triggered for substantive question")
        else:
            print("❌ Retrieval was NOT triggered for substantive question")

if __name__ == "__main__":
    asyncio.run(test_streaming_delta())
