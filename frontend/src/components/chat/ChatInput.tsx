"use client";

import React, { useRef, useEffect, useState } from "react";
import { Send, Loader2, Paperclip, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChatInputProps {
  onSendMessage: (msg: string, imageBase64?: string) => void;
  isLoading: boolean;
}

export function ChatInput({ onSendMessage, isLoading }: ChatInputProps) {
  const [input, setInput] = useState("");
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSend = () => {
    if ((!input.trim() && !imagePreview) || isLoading) return;
    onSendMessage(input.trim() || "请分析这张图片", imagePreview || undefined);
    setInput("");
    setImagePreview(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) return;
    if (file.size > 10 * 1024 * 1024) {
      alert("Image must be smaller than 10MB");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setImagePreview(reader.result as string);
    reader.readAsDataURL(file);
  };

  const removeImage = () => {
    setImagePreview(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // Handle paste from clipboard
  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of Array.from(items)) {
      if (item.type.startsWith("image/")) {
        e.preventDefault();
        const file = item.getAsFile();
        if (file) {
          const reader = new FileReader();
          reader.onload = () => setImagePreview(reader.result as string);
          reader.readAsDataURL(file);
        }
        break;
      }
    }
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [input]);

  return (
    <div className="flex flex-col gap-2">
      {/* Image Preview */}
      {imagePreview && (
        <div className="relative inline-flex w-fit animate-fade-in">
          <div className="relative overflow-hidden rounded-xl border border-blue-500/30 bg-zinc-900/80 shadow-[0_0_15px_rgba(59,130,246,0.1)]">
            <img
              src={imagePreview}
              alt="Upload preview"
              className="h-24 max-w-[200px] object-cover"
            />
            <button
              onClick={removeImage}
              className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-black/70 text-white/80 backdrop-blur-sm transition-colors hover:bg-red-500/80 hover:text-white"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="relative flex w-full items-end gap-2 rounded-2xl border border-white/10 bg-white/5 p-2 shadow-sm backdrop-blur-md transition-all focus-within:ring-1 focus-within:ring-blue-500/50">
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleFileSelect}
          className="hidden"
        />
        {/* Upload Button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading}
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-all",
            imagePreview
              ? "bg-blue-500/20 text-blue-400"
              : "text-white/40 hover:bg-white/10 hover:text-white/70"
          )}
          title="Upload image (Ctrl+V to paste)"
        >
          <Paperclip className="h-4 w-4" />
        </button>

        <textarea
          ref={textareaRef}
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={
            imagePreview
              ? "Add a message about this image..."
              : "Message Enterprise RAG..."
          }
          className="max-h-[150px] w-full resize-none bg-transparent px-3 py-2 text-sm focus:outline-none disabled:opacity-50"
          disabled={isLoading}
        />

        <button
          onClick={handleSend}
          disabled={(!input.trim() && !imagePreview) || isLoading}
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-all",
            (input.trim() || imagePreview) && !isLoading
              ? "bg-blue-600 text-white hover:bg-blue-500 hover:shadow-[0_0_15px_rgba(59,130,246,0.5)]"
              : "bg-white/10 text-white/40"
          )}
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </button>
      </div>
    </div>
  );
}
