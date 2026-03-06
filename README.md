# Houdini AI Assistant

An intelligent agentic assistant that integrates directly into SideFX Houdini to speed up and augment 3D workflows. It enables natural language communication, allowing users to control Houdini by seamlessly generating and executing Python code within a live Houdini session.

## Features

- **Natural Language Interface**: Describe what you want to achieve, and the AI agent translates your request into actionable Houdini operations.
- **Live Houdini Execution**: Generates and natively executes Python script snippets in an active Houdini instance via a robust WebSocket connection.
- **Asynchronous Architecture**: Employs non-blocking operations so neither your user interface nor the chat is blocked during long-running Houdini processes.
- **Agentic Capabilities**: Includes scene awareness, iterative self-correction based on execution feedback, and human-in-the-loop confirmation for critical operations.
- **RAG Implementation**: Augments the agent's knowledge with indexed Houdini documentation and examples using specific vector search capabilities.

## Architecture

The project is structured into three primary components separated by distinct responsibilities:

### 1. Frontend (`/frontend`)
A responsive user interface built using **Next.js**. It provides a sleek, persistent chat environment that communicates with the Agent Orchestrator over WebSockets for real-time streaming updates and feedback.

### 2. Agent Orchestrator (`/agent_orchestrator`)
The decision-making core of the system, powered by **Python, FastAPI, and LangGraph**. 
- It processes natural language inputs.
- Retrieves relevant Houdini API contexts and examples using Retrieval-Augmented Generation (RAG).
- Formulates the sequence of execution steps.
- Creates Python payloads.

### 3. Houdini Backend (`/houdini_backend`)
A lightweight web server interface (`ai_backend.py`) running as a background service directly inside the Houdini environment. It receives programmatic instructions from the Agent Orchestrator, safely executes the Python code within the Houdini context, and streams the results back to the agent.

## Getting Started

### Prerequisites
- SideFX Houdini installed with Python 3 support
- Core Python 3.x+ tools (for the agent orchestrator setup)
- Node.js & npm (for the Next.js frontend setup)

### Execution

1. **Start the Houdini Backend**
   - Open your Houdini instance.
   - Run the script `houdini_backend/ai_backend.py` inside the Houdini Python shell (or as a shelf tool) to start listening for incoming connections.

2. **Start the Agent Orchestrator**
   - Navigate to the `agent_orchestrator` directory.
   - Install requirements: 
     ```bash
     pip install -r requirements.txt
     ```
   - Make sure your `.env` is configured correctly with the required AI API keys (e.g., Gemini).
   - Start the orchestrator service:
     ```bash
     python main.py
     ```

3. **Start the Frontend**
   - Navigate to the `frontend` directory.
   - Install dependencies:
     ```bash
     npm install
     ```
   - Start the development server:
     ```bash
     npm run dev
     ```

## Vector Database & RAG Setup

The assistant uses **Chroma DB** to store and retrieve Houdini documentation for RAG (Retrieval-Augmented Generation).

> [!TIP]
> By default, the system uses a local sentence-transformers model for embeddings. If an `OPENAI_API_KEY` is provided in the `.env` file, it will use OpenAI's `text-embedding-3-small` for better performance.

### 1. Prepare Houdini Help Files
Ensure you have Houdini installed. The system indexes documentation from the following ZIP files usually located in:
`C:/Program Files/Side Effects Software/Houdini <version>/houdini/help/`

*   `nodes.zip`
*   `hom.zip`
*   `vex.zip`
*   `basics.zip`

### 2. Configure Indexer
Open `agent_orchestrator/reindex_all.py` and update the `HOUDINI_HELP_DIR` variable to point to your Houdini installation's help directory.

### 3. Run Reindexing
Run the following command from the `agent_orchestrator` directory (make sure your virtual environment is active):
```bash
python reindex_all.py
```
This will remove any existing `chroma_db` folder and create a fresh index.

### 4. Verify the Database
You can test if the database was populated correctly by running:
```bash
python test_chroma_db.py
```

## Extensibility
This system is built from the ground up for modularity. Adding new agent functionalities, refining vector representations, adding custom UI components, or upgrading the underlying model can be achieved independently.
