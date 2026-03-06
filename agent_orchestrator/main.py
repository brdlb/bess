import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from langchain_core.messages import HumanMessage
from graph import compiled_graph

app = FastAPI(title="Houdini AI Assistant Orchestrator")

# Allow CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Agent Orchestrator"}

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    
    # Simple in-memory thread storage for session
    thread_id = "default"
    config = {"configurable": {"thread_id": thread_id}}
    
    # We need to maintain state messages for this user
    # In a real app this uses LangGraph Checkpointer
    chat_history = []
    
    try:
        while True:
            # Receive text from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get("message", "")
            
            chat_history.append(HumanMessage(content=user_message))
            
            # Start graph iteration
            initial_state = {"messages": chat_history, "error_count": 0}
            
            # Use LangChain astream_events for token-by-token streaming
            # v2 streaming API
            async for event in compiled_graph.astream_events(initial_state, version="v1", config=config):
                kind = event["event"]
                
                # Handle Message generation chunking (LLM response stream)
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if getattr(chunk, "content", None):
                        await websocket.send_json({
                            "type": "token",
                            "content": str(chunk.content)
                        })
                # Handle tool start
                elif kind == "on_tool_start":
                    await websocket.send_json({
                        "type": "tool_start",
                        "tool": event["name"],
                        "input": event["data"].get("input")
                    })
                # Handle tool completion
                elif kind == "on_tool_end":
                    await websocket.send_json({
                        "type": "tool_end",
                        "tool": event["name"],
                        "output": str(event["data"].get("output"))
                    })
            
            # Wait for final state to update our in-memory history
            # The last event payload usually contains the updated state messages
            final_state = await compiled_graph.ainvoke(initial_state, config=config)
            chat_history = final_state["messages"]
            
            # Send completion
            await websocket.send_json({"type": "message_complete"})
            
    except WebSocketDisconnect:
        print("Client disconnected from chat WebSocket.")
    except Exception as e:
        print(f"WebSocket Error: {e}")
        await websocket.close()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8555, reload=True)
