import os
import json
import logging
import requests
from typing import TypedDict, Annotated, Sequence, List, Optional
import operator
import chromadb
from pydantic import BaseModel, Field

logger = logging.getLogger("orchestrator_graph")

system_prompt_path = os.path.join(os.path.dirname(__file__), "system_prompt.md")
with open(system_prompt_path, "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

# Load environment variables from .env if present
from dotenv import load_dotenv
load_dotenv()

from langchain_ollama import ChatOllama

use_ollama = os.environ.get("USE_OLLAMA", "true").lower() == "true"
ollama_model = os.environ.get("OLLAMA_MODEL", "qwen3-coder-next:cloud")
ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
ollama_api_key = os.environ.get("OLLAMA_API_KEY", "")

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    error_count: int
    scene_inspected: bool
    step_count: int

# --- Define Tools ---
@tool
def houdini_execute(code: str) -> dict:
    """Executes Python code in the live Houdini session using hou module."""
    logger.debug(f"Tool houdini_execute called with code:\n{code}")
    try:
        response = requests.post(
            "http://localhost:9000/execute", 
            json={"code": code},
            timeout=10
        )
        return response.json()
    except Exception as e:
        logger.error(f"Failed to connect to Houdini execute endpoint: {e}")
        return {"status": "error", "error": f"Failed to connect to Houdini: {e}"}

@tool
def houdini_get_scene(path: str = '/obj', max_depth: int = 3) -> dict:
    """Gets the current node graph structure in Houdini, traversing up to max_depth."""
    logger.debug(f"Tool houdini_get_scene called for path: {path}, max_depth: {max_depth}")
    try:
        response = requests.get(f"http://localhost:9000/scene", params={"path": path, "max_depth": max_depth}, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Failed to connect to Houdini scene endpoint: {e}")
        return {"status": "error", "error": f"Failed to connect: {e}"}

class AskUserSchema(BaseModel):
    question: str = Field(description="The question to ask the user. Include any options in the question text if applicable.")

@tool(args_schema=AskUserSchema)
def ask_user(question: str) -> str:
    """Ask the user a question to clarify intent OR ask for approval before performing a destructive operation."""
    logger.info(f"Tool ask_user called with question: {question}")
    return f"PAUSED: Waiting for user to respond to: '{question}'"

@tool
def hou_docs_search(query: str) -> str:
    """Search the Houdini Object Model (HOM) and Node documentation for API help, node parameters, and VEX usage patterns."""
    logger.debug(f"Tool hou_docs_search called with query: {query}")
    try:
        from indexer import get_collection
        collection = get_collection()
        results = collection.query(query_texts=[query], n_results=5)
        
        if not results['documents'][0]:
            logger.debug("No documentation found for query.")
            return "No relevant documentation found."
        
        formatted_results = []
        for i in range(len(results['documents'][0])):
            doc = results['documents'][0][i]
            meta = results['metadatas'][0][i]
            breadcrumb = meta.get('breadcrumb', 'Unknown')
            formatted_results.append(f"### Result from: {breadcrumb}\n{doc}")
            
        return "\n\n---\n\n".join(formatted_results)
    except Exception as e:
        logger.error(f"Documentation search failed: {e}")
        return f"Documentation search failed: {e}"

tools = [houdini_execute, houdini_get_scene, ask_user, hou_docs_search]
tool_node = ToolNode(tools)

if use_ollama:
    kwargs = {
        "model": ollama_model,
        "base_url": ollama_base_url,
        "temperature": 0,
    }
    if ollama_api_key:
        kwargs["client_kwargs"] = {
            "headers": {"Authorization": f"Bearer {ollama_api_key}"}
        }

    llm = ChatOllama(**kwargs)
    llm_with_tools = llm.bind_tools(tools)
    logger.info(f"Agent initialized with Ollama ({ollama_model} at {ollama_base_url}).")
else:
    logger.critical("USE_OLLAMA is not true. Please set USE_OLLAMA=true in .env to run with Ollama.")
    raise ValueError("USE_OLLAMA is not true. Please set USE_OLLAMA=true in .env to run with Ollama.")

# --- Define Nodes ---
def call_model(state: AgentState):
    """Call the LLM to decide the next action or generate a response."""
    logger.debug("Node 'agent' (call_model) execution started.")
    messages = state["messages"]
    
    # Check if we exhausted retries
    if state.get("error_count", 0) >= 3:
        logger.warning("Error count limit (3) reached. Stopping to prevent infinite loop.")
        return {
            "messages": [AIMessage(content="I've encountered repeated errors while trying to execute this. I am stopping to prevent an infinite loop. Please check the scene or correct my approach.")],
            "error_count": 0, # Reset for the next human input
            "step_count": 0
        }

    current_steps = state.get("step_count", 0)
    if current_steps >= 100:
        logger.warning("Step count limit (100) reached. Stopping to prevent infinite tool loop.")
        return {
            "messages": [AIMessage(content="I have exceeded the maximum number of steps allowed (100) for a single request. I am stopping to prevent an infinite loop. Please refine your request.")],
            "error_count": 0,
            "step_count": 0
        }

    # Inject our system prompt dynamically if the first message isn't a SystemMessage
    # (For simplicity here, we assume standard usage, or Anthropic accepts it)
    logger.debug("Invoking LLM with tools.")
    response = llm_with_tools.invoke([{"role": "system", "content": SYSTEM_PROMPT}] + messages)
    
    # Prevent infinite loops from identical consecutive tool calls
    if getattr(response, "tool_calls", None) and len(messages) > 0:
        last_ai_msg = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                last_ai_msg = msg
                break
                
        if last_ai_msg and response.tool_calls == last_ai_msg.tool_calls:
            logger.warning("LLM generated the exact same tool call as before! Intercepting to prevent loop.")
            loop_msg = "I'm having trouble making progress because I keep trying the same blocked action. I am pausing to prevent a loop. Please adjust your request or check the setup."
            return {
                "messages": [AIMessage(content=loop_msg)],
                "step_count": 0
            }

    logger.debug(f"LLM response received: {response}")
    return {
        "messages": [response],
        "step_count": current_steps + 1
    }

def call_tool(state: AgentState):
    """Execute the tool requested by the LLM."""
    logger.debug("Node 'action' (call_tool) execution started.")
    messages = state["messages"]
    last_message = messages[-1]
    scene_inspected = state.get("scene_inspected", False)
    error_count = state.get("error_count", 0)
    
    tool_call = last_message.tool_calls[0]
    logger.info(f"Agent requested tool call: {tool_call['name']}")
    
    # Enforce scene inspection constraint
    if tool_call["name"] == "houdini_execute" and not scene_inspected:
         logger.warning("Agent attempted to execute code without inspecting the scene first. Rejecting request.")
         error_msg = {"status": "error", "error": "FORBIDDEN: You must call 'houdini_get_scene' first to understand the scene context before executing code."}
         return {
             "messages": [ToolMessage(content=str(error_msg), name=tool_call["name"], tool_call_id=tool_call["id"])],
             "error_count": error_count + 1
         }
         
    # Execute the tools using ToolNode
    # ToolNode expects a state with "messages" containing the AIMessage with tool_calls
    # It returns a state dict with "messages" containing ToolMessages
    response_state = tool_node.invoke({"messages": [last_message]})
    new_messages = response_state["messages"]
    
    # State updates
    state_updates = {"messages": new_messages}
    
    if tool_call["name"] == "houdini_get_scene":
        logger.debug("Scene has been inspected. Updating state.")
        state_updates["scene_inspected"] = True
        
    # Check if any tool execution had an error out of the tool message
    tool_msg = new_messages[0].content
    if isinstance(tool_msg, str) and ("error" in tool_msg.lower() or "failed" in tool_msg.lower()):
        logger.warning(f"Tool execution returned an error. Incrementing error_count from {error_count} to {error_count + 1}.")
        state_updates["error_count"] = error_count + 1
    else:
        if error_count > 0:
            logger.debug("Tool execution successful. Resetting error_count to 0.")
        state_updates["error_count"] = 0 # Reset on success
             
    return state_updates

def should_continue(state: AgentState) -> str:
    """Determine whether to use a tool or end the conversation."""
    last_message = state["messages"][-1]
    # If there are tool calls, we route to call_tool
    if getattr(last_message, "tool_calls", None):
        logger.debug("Agent requested a tool call. Continuing to 'action' node.")
        return "continue"
    logger.debug("No tool call requested. Ending conversation.")
    return "end"

# --- Build the Graph ---
workflow = StateGraph(AgentState)

workflow.add_node("agent", call_model)
workflow.add_node("action", call_tool)

workflow.set_entry_point("agent")

def after_action(state: AgentState) -> str:
    messages = state["messages"]
    last_message = messages[-1]
    if getattr(last_message, "name", None) == "ask_user":
        logger.debug("Tool 'ask_user' executed. Halting graph to wait for human input.")
        return "end"
    return "continue"

workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "continue": "action",
        "end": END
    }
)
workflow.add_conditional_edges(
    "action",
    after_action,
    {
        "continue": "agent",
        "end": END
    }
)

compiled_graph = workflow.compile()
