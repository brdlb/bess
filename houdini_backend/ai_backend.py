"""
Houdini AI Assistant - MVP Backend Server
=========================================

Instructions:
Execute this script inside the Houdini Python Shell or create a Shelf Tool.
It creates a non-blocking background thread that listens for HTTP requests from the LangGraph Orchestrator.
"""

import threading
import json
import traceback
import asyncio
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import websockets
except ImportError:
    print("WARNING: 'websockets' module not found. Run 'pip install websockets' for realtime events.")
    websockets = None

try:
    import hou
except ImportError:
    print("WARNING: 'hou' module not found. Are you running this inside Houdini?")
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
    if not websockets or not _ws_clients:
        return
    
    # We need to run the send coroutines in the asyncio event loop
    message = json.dumps({"type": event_type, "data": data})
    
    async def send_all():
        if _ws_clients:
            await asyncio.gather(*[client.send(message) for client in _ws_clients], return_exceptions=True)
            
    # If there is a running loop in another thread, we can schedule it:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(send_all(), loop)
        else:
             asyncio.run(send_all())
    except Exception as e:
        print(f"Failed to broadcast WS event: {e}")

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
            
            result_container = {}
            
            # The execution environment allows the LLM to access `hou` and populate `result`
            exec_env = {'hou': hou, 'result': result_container}
            
            try:
                # Execute the provided code block
                exec(body.get('code', ''), exec_env)
                
                response = {
                    'status': 'ok', 
                    'data': result_container
                }
                # Emit success event over websocket
                broadcast_event('cook_complete', {'status': 'ok'})
                
            except Exception as e:
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
            self._send({"alive": True, "houdini_available": hou is not None})
            
        elif parsed_path.path == '/scene':
            query_params = parse_qs(parsed_path.query)
            scene_path = query_params.get('path', ['/obj'])[0]
            try:
                max_depth = int(query_params.get('max_depth', ['3'])[0])
            except ValueError:
                max_depth = 3

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
        _hou_server = HTTPServer(('localhost', port), HouHandler)
        print(f"Houdini AI HTTP Backend listening on http://localhost:{port}...")
        _hou_server.serve_forever()
    except OSError as e:
        print(f"HTTP Server could not start on port {port}: {e}")

def run_ws_server(port=9001):
    if websockets is None:
        print("Skipping WebSocket server (websockets package not installed).")
        return
        
    global _ws_loop
    
    async def main():
        global _ws_loop
        _ws_loop = asyncio.get_running_loop()
        print(f"Houdini AI WebSocket Backend listening on ws://localhost:{port}...")
        async with websockets.serve(ws_handler, "localhost", port):
            await asyncio.Future()  # run forever

    asyncio.run(main())

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
        print("\nRunning in standalone Test Mode (No Houdini). Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Server stopped.")
