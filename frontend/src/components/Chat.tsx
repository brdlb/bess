"use client";

import { useState, useEffect, useRef } from "react";
import { Send, Loader2, Wrench, CheckCircle2, AlertCircle } from "lucide-react";

type Message = {
    id: string;
    role: "user" | "assistant" | "system";
    content: string;
    isStreaming?: boolean;
    toolCalls?: { name: string; input?: any; output?: string }[];
};

export default function Chat() {
    const [messages, setMessages] = useState<Message[]>([
        {
            id: "welcome",
            role: "assistant",
            content: "Hello! I am your Houdini AI Assistant. I can manipulate your Houdini scene, inspect geometry, and execute HOM Python code. How can I help you today?",
        },
    ]);
    const [input, setInput] = useState("");
    const [isConnected, setIsConnected] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Auto-scroll
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    // Connect WebSocket
    useEffect(() => {
        const ws = new WebSocket("ws://localhost:8555/ws/chat");
        wsRef.current = ws;

        ws.onopen = () => setIsConnected(true);
        ws.onclose = () => setIsConnected(false);

        let currentAssistantMessageId: string | null = null;

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === "token") {
                setMessages((prev) => {
                    const lastMsg = prev[prev.length - 1];
                    if (lastMsg?.role === "assistant" && lastMsg.isStreaming && currentAssistantMessageId === lastMsg.id) {
                        return [
                            ...prev.slice(0, -1),
                            { ...lastMsg, content: lastMsg.content + data.content },
                        ];
                    } else {
                        currentAssistantMessageId = Date.now().toString();
                        return [
                            ...prev,
                            {
                                id: currentAssistantMessageId,
                                role: "assistant",
                                content: data.content,
                                isStreaming: true,
                            },
                        ];
                    }
                });
            } else if (data.type === "tool_start") {
                // Display tool usage
                setMessages((prev) => {
                    currentAssistantMessageId = null; // End current text stream
                    return [
                        ...prev,
                        {
                            id: Date.now().toString(),
                            role: "system",
                            content: `Executing tool: ${data.tool}...`
                        }
                    ]
                });
            } else if (data.type === "tool_end") {
                setMessages((prev) => {
                    const msgs = [...prev];
                    const lastMsg = msgs[msgs.length - 1];
                    if (lastMsg.role === "system") {
                        lastMsg.content = `Finished: ${data.tool}`;
                    }
                    currentAssistantMessageId = null; // Ensure new text gets new bubble
                    return msgs;
                });
            } else if (data.type === "message_complete") {
                setIsProcessing(false);
                setMessages((prev) => {
                    const newMsgs = [...prev];
                    const lastMsg = newMsgs[newMsgs.length - 1];
                    if (lastMsg && lastMsg.isStreaming) {
                        lastMsg.isStreaming = false;
                    }
                    return newMsgs;
                });
            }
        };

        return () => ws.close();
    }, []);

    const sendMessage = (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || !isConnected || isProcessing) return;

        const userMsg: Message = { id: Date.now().toString(), role: "user", content: input };
        setMessages((prev) => [...prev, userMsg]);
        setInput("");
        setIsProcessing(true);

        wsRef.current?.send(JSON.stringify({ message: input }));
    };

    return (
        <div className="flex flex-col h-full bg-stone-900 border-r border-stone-800">
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {messages.map((msg) => (
                    <div
                        key={msg.id}
                        className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                        {msg.role === "system" ? (
                            <div className="flex items-center gap-2 text-xs font-mono text-emerald-500 bg-emerald-500/10 px-3 py-2 rounded-lg border border-emerald-500/20 max-w-[80%]">
                                <Loader2 className="w-3 h-3 animate-spin" />
                                {msg.content}
                            </div>
                        ) : (
                            <div
                                className={`max-w-[80%] rounded-2xl px-5 py-3.5 shadow-sm text-sm ${msg.role === "user"
                                        ? "bg-orange-600 text-white rounded-br-none"
                                        : "bg-stone-800 text-stone-200 rounded-bl-none border border-stone-700/50"
                                    }`}
                            >
                                <div className="whitespace-pre-wrap">{msg.content}</div>
                                {msg.isStreaming && (
                                    <span className="inline-block w-1.5 h-4 ml-1 bg-stone-400 animate-pulse mt-0.5 align-middle" />
                                )}
                            </div>
                        )}
                    </div>
                ))}
                {isProcessing && !messages[messages.length - 1]?.isStreaming && messages[messages.length - 1]?.role !== "system" && (
                    <div className="flex justify-start">
                        <div className="bg-stone-800 text-stone-200 rounded-2xl rounded-bl-none px-5 py-3.5 border border-stone-700/50 shadow-sm flex items-center gap-2">
                            <span className="w-1.5 h-1.5 bg-stone-400 rounded-full animate-bounce"></span>
                            <span className="w-1.5 h-1.5 bg-stone-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                            <span className="w-1.5 h-1.5 bg-stone-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                        </div>
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            <div className="p-4 bg-stone-900 border-t border-stone-800">
                <form
                    onSubmit={sendMessage}
                    className="relative flex items-center w-full max-w-4xl mx-auto"
                >
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        disabled={!isConnected || isProcessing}
                        placeholder={
                            !isConnected
                                ? "Connecting to Orchestrator..."
                                : isProcessing
                                    ? "Agent is thinking..."
                                    : "Ask me to modify the Houdini scene..."
                        }
                        className="w-full bg-stone-950 border border-stone-800 text-stone-200 rounded-full pl-6 pr-14 py-4 focus:outline-none focus:ring-1 focus:ring-orange-500/50 focus:border-orange-500/50 transition-all placeholder:text-stone-600 shadow-inner disabled:opacity-50"
                    />
                    <button
                        type="submit"
                        disabled={!input.trim() || !isConnected || isProcessing}
                        className="absolute right-2 p-2.5 rounded-full bg-orange-600 hover:bg-orange-500 text-white disabled:opacity-50 disabled:hover:bg-orange-600 transition-colors shadow-md flex items-center justify-center"
                    >
                        {isProcessing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    </button>
                </form>
                <div className="text-center mt-3 text-[10px] text-stone-600 font-medium tracking-wide w-full flex items-center justify-center gap-2">
                    {!isConnected ? (
                        <>
                            <AlertCircle className="w-3 h-3 text-red-500" />
                            <span className="text-red-400">Disconnected from server</span>
                        </>
                    ) : (
                        <>
                            <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                            <span className="text-emerald-500/80">Agent WebSocket Connected</span>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
