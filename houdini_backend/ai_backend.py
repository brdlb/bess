"""
Houdini AI Assistant - MVP Backend Server
=========================================

Instructions:
Execute this script inside the Houdini Python Shell or create a Shelf Tool.
It creates a non-blocking background thread that listens for HTTP requests from the LangGraph Orchestrator.
"""

import os
import threading
import json
import traceback
import asyncio
import logging
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler

# Set up logging for the backend
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("houdini_backend")

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    logger.warning("!!! 'websockets' module not found !!!")
    logger.warning("To enable realtime events in the frontend, run in Houdini's Python or matching environment:")
    logger.warning("hython -m pip install websockets")
    websockets = None
    HAS_WEBSOCKETS = False


try:
    import hou
except ImportError:
    logger.warning("'hou' module not found. Are you running this inside Houdini?")
    hou = None

# Global set of connected websocket clients
_ws_clients = set()

async def ws_handler(websocket, path):
    _ws_clients.add(websocket)
    try:
        async for message in websocket:
            # We're mostly just sending events to clients, but we can accept messages if needed
            pass
    finally:
        _ws_clients.remove(websocket)

def broadcast_event(event_type, data):
    """Utility to broadcast an event to all connected websocket clients."""
    if not websockets or not _ws_clients or not _ws_loop:
        return
    
    # We need to run the send coroutines in the asyncio event loop
    message = json.dumps({"type": event_type, "data": data})
    
    async def send_all():
        if _ws_clients:
            # Create a list of send tasks
            await asyncio.gather(*[client.send(message) for client in _ws_clients], return_exceptions=True)
            
    # Send to the background loop from whatever thread we are in
    try:
        if _ws_loop.is_running():
            asyncio.run_coroutine_threadsafe(send_all(), _ws_loop)
    except Exception as e:
        logger.error(f"Failed to broadcast WS event: {e}")

class HouHandler(BaseHTTPRequestHandler):
    
    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path == '/execute':
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            
            logger.info(f"Received /execute request")
            logger.debug(f"Execution code block: {body.get('code', '')}")
            
            result_container = {}
            
            # The execution environment allows the LLM to access `hou` and populate `result`
            exec_env = {'hou': hou, 'result': result_container}
            
            try:
                def run_code():
                    if hou and hasattr(hou, "undos") and hasattr(hou.undos, "group"):
                        try:
                            with hou.undos.group("Agent Execution"):
                                exec(body.get('code', ''), exec_env)
                        except Exception as script_err:
                            # If an error happens, we undo the actions of this script
                            if hasattr(hou.undos, "performUndo"):
                                try:
                                    hou.undos.performUndo()
                                    logger.info("Actions of failed script successfully undone.")
                                except Exception as undo_err:
                                    logger.error(f"Failed to undo actions: {undo_err}")
                            raise script_err
                    else:
                        exec(body.get('code', ''), exec_env)

                # Execute the provided code block
                if hou and hasattr(hou, "executeInMainThreadWithResult"):
                    # Safer to run Houdini commands in the main thread
                    hou.executeInMainThreadWithResult(run_code)
                else:
                    run_code()
                
                response = {
                    'status': 'ok', 
                    'data': result_container
                }
                logger.info(f"Execution successful. Result: {result_container}")
                # Emit success event over websocket
                broadcast_event('cook_complete', {'status': 'ok'})
                
            except Exception as e:
                logger.error(f"Execution failed: {e}", exc_info=True)
                response = {
                    'status': 'error', 
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }
                # Emit error event over websocket
                broadcast_event('error', {'error': str(e)})
                
            self._send(response)
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path == '/health':
            self._send({
                "alive": True, 
                "houdini_available": hou is not None,
                "has_websockets": HAS_WEBSOCKETS
            })

            
        elif parsed_path.path == '/scene':
            query_params = parse_qs(parsed_path.query)
            scene_path = query_params.get('path', ['/obj'])[0]
            try:
                max_depth = int(query_params.get('max_depth', ['3'])[0])
            except ValueError:
                max_depth = 3

            logger.info(f"Received /scene request for path: '{scene_path}', max_depth: {max_depth}")

            try:
                if hou:
                    root_node = hou.node(scene_path)
                    if not root_node:
                        self._send({"status": "error", "error": f"Node not found: {scene_path}"})
                        return

                    def get_node_info(node, current_depth, max_depth):
                        info = {
                            "name": node.name(),
                            "path": node.path(),
                            "type": node.type().name()
                        }
                        if current_depth < max_depth:
                            children = node.children()
                            if children:
                                info["children"] = [get_node_info(c, current_depth + 1, max_depth) for c in children]
                        return info

                    nodes_data = []
                    for n in root_node.children():
                        nodes_data.append(get_node_info(n, 1, max_depth))
                        
                    data = {"context": scene_path, "nodes": nodes_data}
                else:
                    data = {"error": "Houdini environment not found"}
                    
                self._send({"status": "ok", "data": data})
            except Exception as e:
                self._send({
                    "status": "error", 
                    "error": str(e),
                    "traceback": traceback.format_exc()
                })
        else:
            self.send_response(404)
            self.end_headers()

    def _send(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        # Convert dictionary to JSON string and encode to bytes
        self.wfile.write(json.dumps(data).encode('utf-8'))

# Global references
_hou_server = None
_ws_loop = None

def run_http_server(port=9000):
    global _hou_server
    try:
        _hou_server = HTTPServer(('127.0.0.1', port), HouHandler)
        logger.info(f"Houdini AI HTTP Backend listening on http://127.0.0.1:{port}...")
        _hou_server.serve_forever()

    except OSError as e:
        logger.error(f"HTTP Server could not start on port {port}: {e}")

def run_ws_server(port=9001):
    if websockets is None:
        logger.info("Skipping WebSocket server (websockets package not installed).")
        return
        
    global _ws_loop
    
    # To bypass Houdini's haio (which enforces main thread), we create 
    # a standard selector loop specifically for this background thread
    try:
        # On Windows, we need the Selector loop for websockets to work reliably in a thread
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        _ws_loop = loop
        
        async def main():
            logger.info(f"Houdini AI WebSocket Backend listening on ws://127.0.0.1:{port}...")
            async with websockets.serve(ws_handler, "127.0.0.1", port):
                await asyncio.Future()  # run forever

        loop.run_until_complete(main())

    except Exception as e:
        logger.error(f"WebSocket server failed: {e}", exc_info=True)
    finally:
        if _ws_loop:
            _ws_loop.close()

def start_server(http_port=9000, ws_port=9001):
    http_thread = threading.Thread(target=run_http_server, args=(http_port,), daemon=True)
    http_thread.start()
    
    ws_thread = threading.Thread(target=run_ws_server, args=(ws_port,), daemon=True)
    ws_thread.start()
    
    return http_thread, ws_thread

if __name__ == '__main__':
    # Start servers in background threads so Houdini UI is not blocked
    start_server(9000, 9001)
    
    # If running outside Houdini (from a standard terminal for testing), 
    # keep the main thread alive so the background threads don't exit immediately.
    if hou is None:
        import time
        logger.info("Running in standalone Test Mode (No Houdini). Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Server stopped.")
