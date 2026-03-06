import os
import json
import requests
from typing import TypedDict, Annotated, Sequence, List, Optional
import operator
import chromadb
from langchain_core.pydantic_v1 import BaseModel, Field

from few_shot_examples import FEW_SHOT_EXAMPLES
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolExecutor, ToolInvocation
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

# Load environment variables from .env if present
from dotenv import load_dotenv
load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic

# Check for API keys in env
google_api_key = os.environ.get("GOOGLE_API_KEY")
anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    error_count: int
    scene_inspected: bool

# --- Define Tools ---
@tool
def houdini_execute(code: str) -> dict:
    """Executes Python code in the live Houdini session using hou module."""
    try:
        response = requests.post(
            "http://localhost:9000/execute", 
            json={"code": code},
            timeout=10
        )
        return response.json()
    except Exception as e:
        return {"status": "error", "error": f"Failed to connect to Houdini: {e}"}

@tool
def houdini_get_scene(path: str = '/obj') -> dict:
    """Gets the current node graph structure in Houdini."""
    try:
        response = requests.get(f"http://localhost:9000/scene", timeout=5)
        return response.json()
    except Exception as e:
         return {"status": "error", "error": f"Failed to connect: {e}"}

class AskUserSchema(BaseModel):
    question: str = Field(description="The question to ask the user. Include any options in the question text if applicable.")

@tool(args_schema=AskUserSchema)
def ask_user(question: str) -> str:
    """Ask the user a question to clarify intent OR ask for approval before performing a destructive operation."""
    return f"PAUSED: Waiting for user to respond to: '{question}'"

@tool
def hou_docs_search(query: str) -> str:
    """Search the Houdini Object Model (HOM) documentation for API help or Python usage patterns."""
    try:
        from indexer import get_collection
        collection = get_collection()
        results = collection.query(query_texts=[query], n_results=2)
        
        if not results['documents'][0]:
            return "No relevant documentation found."
            
        return "\n\n---\n\n".join(results['documents'][0])
    except Exception as e:
        return f"Documentation search failed: {e}"

tools = [houdini_execute, houdini_get_scene, ask_user, hou_docs_search]
tool_executor = ToolExecutor(tools)

if google_api_key:
    # Recommended model for logic, tools and quick reasoning
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    llm_with_tools = llm.bind_tools(tools)
    print("Agent initialized with Google Gemini (gemini-2.5-flash).")
elif anthropic_api_key:
    llm = ChatAnthropic(model="claude-3-5-sonnet-20240620", temperature=0)
    llm_with_tools = llm.bind_tools(tools)
    print("Agent initialized with Anthropic Claude.")
else:
    raise ValueError("Neither GOOGLE_API_KEY nor ANTHROPIC_API_KEY found. An API key is required.")

# --- Define Nodes ---
def call_model(state: AgentState):
    """Call the LLM to decide the next action or generate a response."""
    messages = state["messages"]
    
    # Check if we exhausted retries
    if state.get("error_count", 0) >= 3:
        return {
            "messages": [AIMessage(content="I've encountered repeated errors while trying to execute this. I am stopping to prevent an infinite loop. Please check the scene or correct my approach.")],
            "error_count": 0 # Reset for the next human input
        }

    system_prompt = (
        "You are a Houdini AI Assistant. "
        "1. ALWAYS inspect the scene with 'houdini_get_scene' first.\n"
        "2. ALWAYS ask the user with 'ask_user' before destructive operations.\n"
        "3. If you are unsure of a hou module syntax, use 'hou_docs_search' to query the HOM documentation.\n"
        "4. Use the 'hou' module for code."
        f"\n\n{FEW_SHOT_EXAMPLES}"
    )
    
    # Inject our system prompt dynamically if the first message isn't a SystemMessage
    # (For simplicity here, we assume standard usage, or Anthropic accepts it)
    response = llm_with_tools.invoke([{"role": "system", "content": system_prompt}] + messages)
    return {"messages": [response]}

def call_tool(state: AgentState):
    """Execute the tool requested by the LLM."""
    messages = state["messages"]
    last_message = messages[-1]
    scene_inspected = state.get("scene_inspected", False)
    error_count = state.get("error_count", 0)
    
    tool_call = last_message.tool_calls[0]
    action = ToolInvocation(
        tool=tool_call["name"],
        tool_input=tool_call["args"],
    )
    
    # Enforce scene inspection constraint
    if action.tool == "houdini_execute" and not scene_inspected:
         error_msg = {"status": "error", "error": "FORBIDDEN: You must call 'houdini_get_scene' first to understand the scene context before executing code."}
         return {
             "messages": [ToolMessage(content=str(error_msg), name=action.tool, tool_call_id=tool_call["id"])],
             "error_count": error_count + 1
         }
         
    # Execute the tool
    response = tool_executor.invoke(action)
    
    # State updates
    state_updates = {"messages": [ToolMessage(content=str(response), name=action.tool, tool_call_id=tool_call["id"])]}
    
    if action.tool == "houdini_get_scene":
        state_updates["scene_inspected"] = True
        
    if action.tool == "houdini_execute":
        # Check if the execution had an error
        if isinstance(response, dict) and response.get("status") == "error":
            state_updates["error_count"] = error_count + 1
        else:
             state_updates["error_count"] = 0 # Reset on success
             
    return state_updates

def should_continue(state: AgentState) -> str:
    """Determine whether to use a tool or end the conversation."""
    last_message = state["messages"][-1]
    # If there are tool calls, we route to call_tool
    if getattr(last_message, "tool_calls", None):
        return "continue"
    return "end"

# --- Build the Graph ---
workflow = StateGraph(AgentState)

workflow.add_node("agent", call_model)
workflow.add_node("action", call_tool)

workflow.set_entry_point("agent")

workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "continue": "action",
        "end": END
    }
)
workflow.add_edge("action", "agent")

compiled_graph = workflow.compile()
