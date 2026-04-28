"use client";

import React from "react";
import { MessageSquarePlus, Trash2, PanelLeftClose, PanelLeft, MessageCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export interface Session {
  session_id: string;
  title: string;
  message_count: number;
  last_active: number;
}

interface SidebarProps {
  sessions: Session[];
  activeSessionId: string | null;
  isOpen: boolean;
  onToggle: () => void;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
}

function timeAgo(timestamp: number): string {
  const seconds = Math.floor(Date.now() / 1000 - timestamp);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function Sidebar({
  sessions,
  activeSessionId,
  isOpen,
  onToggle,
  onNewChat,
  onSelectSession,
  onDeleteSession,
}: SidebarProps) {
  return (
    <>
      {/* Collapsed toggle button */}
      {!isOpen && (
        <button
          onClick={onToggle}
          className="absolute left-3 top-3 z-30 flex h-9 w-9 items-center justify-center rounded-lg bg-zinc-800/80 text-zinc-400 backdrop-blur-sm transition-all hover:bg-zinc-700 hover:text-white"
          title="Open sidebar"
        >
          <PanelLeft className="h-4 w-4" />
        </button>
      )}

      {/* Sidebar panel */}
      <div
        className={cn(
          "flex h-full flex-col border-r border-white/5 bg-zinc-950/80 backdrop-blur-xl transition-all duration-300",
          isOpen ? "w-[280px] min-w-[280px]" : "w-0 min-w-0 overflow-hidden"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/5 p-3">
          <button
            onClick={onNewChat}
            className="flex items-center gap-2 rounded-lg bg-blue-600/20 px-3 py-2 text-sm font-medium text-blue-400 transition-all hover:bg-blue-600/30 hover:text-blue-300"
          >
            <MessageSquarePlus className="h-4 w-4" />
            New Chat
          </button>
          <button
            onClick={onToggle}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-300"
            title="Close sidebar"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>

        {/* Session List */}
        <div className="flex-1 overflow-y-auto p-2">
          {sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center px-4 py-12 text-center">
              <MessageCircle className="mb-3 h-8 w-8 text-zinc-700" />
              <p className="text-xs text-zinc-600">No conversations yet</p>
              <p className="mt-1 text-xs text-zinc-700">
                Start chatting to see your history here
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              {sessions.map((session) => (
                <div
                  key={session.session_id}
                  className={cn(
                    "group flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2.5 text-sm transition-all",
                    activeSessionId === session.session_id
                      ? "bg-blue-600/15 text-blue-300"
                      : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                  )}
                  onClick={() => onSelectSession(session.session_id)}
                >
                  <MessageCircle className="h-3.5 w-3.5 shrink-0 opacity-50" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium leading-tight">
                      {session.title}
                    </p>
                    <p className="mt-0.5 text-[11px] text-zinc-600">
                      {session.message_count} msgs · {timeAgo(session.last_active)}
                    </p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteSession(session.session_id);
                    }}
                    className="flex h-6 w-6 shrink-0 items-center justify-center rounded opacity-0 transition-all hover:bg-red-500/20 hover:text-red-400 group-hover:opacity-100"
                    title="Delete conversation"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-white/5 p-3">
          <p className="text-center text-[10px] tracking-wider text-zinc-700">
            Enterprise RAG Agent v2.0
          </p>
        </div>
      </div>
    </>
  );
}
