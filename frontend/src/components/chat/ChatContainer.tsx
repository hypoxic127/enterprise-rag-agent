"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { ChatInput } from "./ChatInput";
import { ChatMessage, type Message } from "./ChatMessage";
import { Sidebar, type Session } from "./Sidebar";

const WELCOME_MESSAGE: Message = {
  id: "welcome",
  role: "assistant",
  content:
    "Hello! I am the Enterprise RAG Agent. I can search through our internal knowledge base or the web. How can I help you today?",
};

export function ChatContainer() {
  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE]);
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const apiBase =
    process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Fetch sessions on mount
  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/sessions`);
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
      }
    } catch {
      // Silently fail — backend may not be running
    }
  }, [apiBase]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleNewChat = () => {
    setSessionId(null);
    setMessages([WELCOME_MESSAGE]);
  };

  const handleSelectSession = async (sid: string) => {
    setSessionId(sid);
    // Load real messages from backend
    try {
      const res = await fetch(`${apiBase}/api/sessions/${sid}/messages`);
      if (res.ok) {
        const data: { role: string; content: string }[] = await res.json();
        const loaded: Message[] = data.map((msg, i) => ({
          id: `${sid}-${i}`,
          role: msg.role as "user" | "assistant",
          content: msg.content,
        }));
        setMessages(loaded.length > 0 ? loaded : [WELCOME_MESSAGE]);
      } else {
        setMessages([WELCOME_MESSAGE]);
      }
    } catch {
      setMessages([WELCOME_MESSAGE]);
    }
  };

  const handleDeleteSession = async (sid: string) => {
    try {
      await fetch(`${apiBase}/api/sessions/${sid}`, { method: "DELETE" });
      setSessions((prev) => prev.filter((s) => s.session_id !== sid));
      if (sessionId === sid) {
        handleNewChat();
      }
    } catch (error) {
      console.error("Failed to delete session:", error);
    }
  };

  const handleSendMessage = async (query: string) => {
    if (!query.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: query,
    };
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    const assistantMessageId = (Date.now() + 1).toString();
    setMessages((prev) => [
      ...prev,
      { id: assistantMessageId, role: "assistant", content: "" },
    ]);

    try {
      const response = await fetch(`${apiBase}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          session_id: sessionId,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to connect to the backend");
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder("utf-8");

      if (reader) {
        let sseBuffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          sseBuffer += decoder.decode(value, { stream: true });
          // SSE events are delimited by double newlines
          const events = sseBuffer.split("\n\n");
          // Keep the last (possibly incomplete) chunk in the buffer
          sseBuffer = events.pop() || "";

          for (const event of events) {
            const lines = event.split("\n");
            for (const line of lines) {
              if (!line.startsWith("data: ")) continue;
              const data = line.slice(6);

              if (data === "[DONE]") {
                break;
              }
              // Capture session_id from backend
              if (data.startsWith("[SESSION:") && data.endsWith("]")) {
                const newSid = data.slice(9, -1);
                setSessionId(newSid);
                fetchSessions();
                continue;
              }
              // Capture citation sources from backend
              if (data.startsWith("[SOURCES:")) {
                try {
                  // Strip the outer [SOURCES: ... ] wrapper
                  const sourcesJson = data.slice(9, -1);
                  const sources = JSON.parse(sourcesJson);
                  setMessages((prev) =>
                    prev.map((msg) =>
                      msg.id === assistantMessageId
                        ? { ...msg, sources }
                        : msg
                    )
                  );
                } catch (e) {
                  console.warn("Failed to parse sources:", e);
                }
                continue;
              }
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? { ...msg, content: msg.content + data }
                    : msg
                )
              );
            }
          }
        }
      }
    } catch (error) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: "assistant",
          content: "Sorry, an error occurred while processing your request.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        sessions={sessions}
        activeSessionId={sessionId}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
      />

      {/* Main Chat Area */}
      <div className="flex flex-1 flex-col bg-background/50">
        {/* Header */}
        <header className="w-full p-4 text-center border-b border-white/5 bg-background/50 backdrop-blur-md shrink-0">
          <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-400">
            Enterprise RAG Agent
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5 tracking-widest uppercase">
            Powered by Gemini 2.5 Pro &amp; Next.js
          </p>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-6 scroll-smooth">
          <div className="mx-auto flex max-w-3xl flex-col space-y-6">
            {messages.map((message) => (
              <div key={message.id} className="animate-fade-in">
                <ChatMessage message={message} />
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>
        <div className="border-t border-white/5 bg-background/80 p-4 backdrop-blur-md">
          <div className="mx-auto max-w-3xl">
            <ChatInput onSendMessage={handleSendMessage} isLoading={isLoading} />
          </div>
        </div>
      </div>
    </div>
  );
}
