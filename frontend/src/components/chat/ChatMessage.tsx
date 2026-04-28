import React from "react";
import ReactMarkdown from "react-markdown";
import { User, Bot, FileText, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";

export type Role = "user" | "assistant";

export interface Source {
  id: number;
  text: string;
  file: string;
  score: number | null;
}

export interface Message {
  id: string;
  role: Role;
  content: string;
  sources?: Source[];
}

interface ChatMessageProps {
  message: Message;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div className="flex flex-col gap-3">
      <div
        className={cn(
          "group relative flex w-full gap-4 px-4 py-6 md:px-0",
          isUser ? "flex-row-reverse" : "flex-row"
        )}
      >
        <div
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border shadow-sm",
            isUser
              ? "border-blue-500/30 bg-blue-500/20 text-blue-300"
              : "border-purple-500/30 bg-purple-500/20 text-purple-300"
          )}
        >
          {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
        </div>
        <div
          className={cn(
            "relative flex max-w-[85%] flex-col gap-2 rounded-2xl px-5 py-4 shadow-sm",
            isUser
              ? "bg-blue-600 border border-blue-500 text-white rounded-tr-sm"
              : "bg-zinc-800 border border-white/10 text-zinc-100 rounded-tl-sm"
          )}
        >
          <div className="prose prose-invert max-w-none text-sm break-words whitespace-pre-wrap">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        </div>
      </div>

      {/* Citation Sources Panel */}
      {message.sources && message.sources.length > 0 && (
        <div className="ml-12 mr-4 md:ml-12 md:mr-0">
          <div className="rounded-xl border border-white/5 bg-zinc-900/60 backdrop-blur-sm overflow-hidden">
            <div className="flex items-center gap-2 border-b border-white/5 px-4 py-2">
              <FileText className="h-3.5 w-3.5 text-emerald-400" />
              <span className="text-xs font-medium text-emerald-400 tracking-wide">
                SOURCES ({message.sources.length})
              </span>
            </div>
            <div className="divide-y divide-white/5">
              {message.sources.map((source) => (
                <div
                  key={source.id}
                  className="flex gap-3 px-4 py-3 transition-colors hover:bg-white/[0.02]"
                >
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-emerald-500/15 text-[10px] font-bold text-emerald-400">
                    {source.id}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-xs font-medium text-zinc-300">
                        {source.file}
                      </span>
                      {source.score !== null && (
                        <span className="shrink-0 rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-500">
                          {(source.score * 100).toFixed(0)}% match
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-zinc-500 line-clamp-2">
                      {source.text}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
