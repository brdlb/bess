import asyncio
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from langchain_core.messages import HumanMessage
from graph import compiled_graph

# Set up logging for the orchestrator
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("orchestrator_main")

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
    logger.debug("Health check requested")
    return {"status": "healthy", "service": "Agent Orchestrator"}

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    logger.info("New WebSocket connection accepted")
    
    # Simple in-memory thread storage for session
    thread_id = "default"
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 100}
    
    # We need to maintain state messages for this user
    # In a real app this uses LangGraph Checkpointer
    chat_history = []
    
    try:
        while True:
            # Receive text from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get("message", "")
            
            logger.info(f"Received message from client: {user_message}")
            chat_history.append(HumanMessage(content=user_message))
            
            # Start graph iteration
            initial_state = {"messages": chat_history, "error_count": 0, "step_count": 0}
            logger.debug(f"Starting graph execution for message: {user_message[:50]}...")
            
            # Use LangChain astream_events for token-by-token streaming
            final_state = None
            async for event in compiled_graph.astream_events(initial_state, version="v1", config=config):
                kind = event["event"]
                name = event["name"]
                
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
                    logger.debug(f"Tool start: {name} with input: {event['data'].get('input')}")
                    await websocket.send_json({
                        "type": "tool_start",
                        "tool": name,
                        "input": event["data"].get("input")
                    })
                # Handle tool completion
                elif kind == "on_tool_end":
                    logger.debug(f"Tool end: {name} with output: {str(event['data'].get('output'))[:200]}...")
                    await websocket.send_json({
                        "type": "tool_end",
                        "tool": name,
                        "output": str(event["data"].get("output"))
                    })
                # Capture the final state from the stream
                elif kind == "on_chain_end":
                    output = event["data"].get("output")
                    if isinstance(output, dict) and "messages" in output:
                        final_state = output
            
            if final_state:
                chat_history = final_state["messages"]
            else:
                logger.warning("Could not extract final state from event stream.")
            
            logger.info("Graph iteration complete. Final state messages updated.")
            
            # Send completion
            await websocket.send_json({"type": "message_complete"})
            
    except WebSocketDisconnect:
        logger.info("Client disconnected from chat WebSocket.")
    except Exception as e:
        logger.error(f"WebSocket Error: {e}", exc_info=True)
        await websocket.close()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8555, reload=True)
