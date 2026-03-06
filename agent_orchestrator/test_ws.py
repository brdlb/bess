import asyncio
import websockets
import json

async def test_chat():
    uri = "ws://localhost:8555/ws/chat"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to WebSocket")
            await websocket.send(json.dumps({"message": "Hello, who are you?"}))
            
            while True:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    data = json.loads(response)
                    print(f"Received: {data}")
                    if data.get("type") == "message_complete":
                        break
                except asyncio.TimeoutError:
                    print("Timeout waiting for response")
                    break
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_chat())
