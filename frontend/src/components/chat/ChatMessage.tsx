"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { User, Bot, FileText, Copy, Check } from "lucide-react";
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
  imageUrl?: string;
}

interface ChatMessageProps {
  message: Message;
  isStreaming?: boolean;
}

function CodeBlock({ className, children, ...props }: React.ComponentPropsWithoutRef<"code"> & { inline?: boolean }) {
  const [copied, setCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || "");
  const codeString = String(children).replace(/\n$/, "");
  const isInline = !match && !codeString.includes("\n");

  if (isInline) {
    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  }

  const language = match?.[1] || "text";

  const handleCopy = async () => {
    await navigator.clipboard.writeText(codeString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="code-block-wrapper">
      <span className="code-lang-badge">{language}</span>
      <button onClick={handleCopy} className="code-copy-btn">
        {copied ? (
          <>
            <Check className="h-3 w-3" />
            Copied
          </>
        ) : (
          <>
            <Copy className="h-3 w-3" />
            Copy
          </>
        )}
      </button>
      <SyntaxHighlighter
        style={oneDark}
        language={language}
        PreTag="div"
        customStyle={{
          margin: 0,
          padding: "2.5rem 1rem 1rem 1rem",
          background: "transparent",
          fontSize: "0.85em",
        }}
      >
        {codeString}
      </SyntaxHighlighter>
    </div>
  );
}

export function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div className="flex flex-col gap-3 animate-fade-in-up">
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
          {message.imageUrl && (
            <div className="mb-2 overflow-hidden rounded-lg border border-white/10">
              <img
                src={message.imageUrl}
                alt="Uploaded"
                className="max-h-64 w-auto rounded-lg object-contain"
              />
            </div>
          )}
          <div className={cn(
              "prose prose-invert prose-sm md:prose-base max-w-none break-words whitespace-pre-wrap prose-a:text-blue-400 hover:prose-a:text-blue-300",
              isStreaming && "streaming-cursor"
            )}>
            {isStreaming ? (
              /* During streaming: render as plain text to avoid broken markdown */
              <p>{message.content}</p>
            ) : (
              /* After streaming: render full markdown */
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code: CodeBlock as any,
                  table({ children }) {
                    return (
                      <div className="overflow-x-auto my-3 rounded-lg border border-white/10">
                        <table className="min-w-full text-sm">{children}</table>
                      </div>
                    );
                  },
                  thead({ children }) {
                    return <thead className="bg-zinc-900/80 text-zinc-300">{children}</thead>;
                  },
                  th({ children }) {
                    return (
                      <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-zinc-400 border-b border-white/10">
                        {children}
                      </th>
                    );
                  },
                  td({ children }) {
                    return (
                      <td className="px-3 py-2 text-zinc-300 border-b border-white/5">
                        {children}
                      </td>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
            )}
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
                  className="group/source flex cursor-pointer gap-3 px-4 py-3 transition-all hover:bg-emerald-500/[0.04]"
                >
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-emerald-500/15 text-[10px] font-bold text-emerald-400 transition-colors group-hover/source:bg-emerald-500/25">
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
