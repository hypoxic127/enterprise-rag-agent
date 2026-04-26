import React from "react";
import ReactMarkdown from "react-markdown";
import { User, Bot } from "lucide-react";
import { cn } from "@/lib/utils";

export type Role = "user" | "assistant";

export interface Message {
  id: string;
  role: Role;
  content: string;
}

interface ChatMessageProps {
  message: Message;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
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
  );
}
