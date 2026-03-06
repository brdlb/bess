"use client";

import { useEffect, useState } from "react";
import { Activity, AlertTriangle, CheckCircle } from "lucide-react";

type HoudiniEvent = {
    id: string;
    type: string;
    data: any;
    timestamp: Date;
};

export default function HoudiniEvents() {
    const [events, setEvents] = useState<HoudiniEvent[]>([]);
    const [isConnected, setIsConnected] = useState(false);

    useEffect(() => {
        const ws = new WebSocket("ws://localhost:9001");

        ws.onopen = () => setIsConnected(true);
        ws.onclose = () => setIsConnected(false);

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                setEvents((prev) => [
                    { id: Date.now().toString(), type: msg.type, data: msg.data, timestamp: new Date() },
                    ...prev, // Prepend new events
                ].slice(0, 50)); // Keep only latest 50 events
            } catch (err) {
                console.error("Failed to parse Houdini event", err);
            }
        };

        return () => ws.close();
    }, []);

    return (
        <aside className="hidden lg:flex flex-col w-96 shrink-0 rounded-xl border border-stone-800 bg-stone-950/30">
            <div className="h-12 border-b border-stone-800 flex items-center px-4 shrink-0 bg-stone-900/50">
                <span className="text-sm font-medium text-stone-400">Context & Events</span>
            </div>
            <div className="p-4 overflow-y-auto space-y-4 text-xs font-mono text-stone-300">
                <div className="p-3 bg-stone-900 rounded-lg border border-stone-800">
                    <div className="text-stone-500 mb-2 font-sans font-medium">Houdini Backend Status</div>
                    <div className="flex items-center gap-2">
                        <span className="relative flex h-2 w-2">
                            <span className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${isConnected ? 'bg-emerald-400 animate-ping' : 'bg-red-400'}`}></span>
                            <span className={`relative inline-flex rounded-full h-2 w-2 ${isConnected ? 'bg-emerald-500' : 'bg-red-500'}`}></span>
                        </span>
                        <span className={isConnected ? "text-emerald-500" : "text-red-500"}>
                            {isConnected ? "Connected (Port 9001)" : "Disconnected"}
                        </span>
                    </div>
                </div>

                <div className="flex flex-col flex-1 h-full min-h-0 bg-stone-900 rounded-lg border border-stone-800 overflow-hidden">
                    <div className="text-stone-500 p-3 border-b border-stone-800 font-sans font-medium flex justify-between items-center bg-stone-900/50">
                        <span>Recent Events</span>
                        {events.length > 0 && <span className="text-[10px] bg-stone-800 px-2 py-0.5 rounded-full">{events.length}</span>}
                    </div>

                    <div className="p-2 overflow-y-auto max-h-[500px] flex flex-col gap-2">
                        {events.length === 0 ? (
                            <span className="opacity-70 italic p-2 block text-center mt-4">Waiting for events from Python server...</span>
                        ) : (
                            events.map((ev) => (
                                <div key={ev.id} className="p-2 bg-stone-950 rounded border border-stone-800 relative group transition-colors hover:border-stone-700">
                                    <div className="flex items-center justify-between mb-1">
                                        <span className="flex items-center gap-1.5 text-stone-300 font-semibold" style={{
                                            color: ev.type === 'error' ? '#ef4444' : ev.type === 'cook_complete' ? '#10b981' : '#f59e0b'
                                        }}>
                                            {ev.type === 'error' ? <AlertTriangle className="w-3 h-3" /> : ev.type === 'cook_complete' ? <CheckCircle className="w-3 h-3" /> : <Activity className="w-3 h-3" />}
                                            {ev.type}
                                        </span>
                                        <span className="text-[10px] text-stone-600 group-hover:text-stone-500 transition-colors">
                                            {ev.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                        </span>
                                    </div>
                                    <div className="text-[11px] text-stone-400 break-words line-clamp-2 hover:line-clamp-none transition-all">
                                        {JSON.stringify(ev.data)}
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </div>
        </aside>
    );
}
