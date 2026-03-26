"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Volume2, User, Bot } from "lucide-react";
import { cn } from "@/lib/utils";

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: Date;
  sources?: Array<{ source: string; file_type?: string }>;
}

interface ChatMessageProps {
  message: Message;
  onSpeak?: (text: string) => void;
  isSpeaking?: boolean;
}

export function ChatMessage({
  message,
  onSpeak,
  isSpeaking,
}: ChatMessageProps) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";

  return (
    <div
      className={cn(
        "flex gap-3 px-4 py-3",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      {!isUser && (
        <Avatar className="h-8 w-8 shrink-0">
          <AvatarImage src="" alt="AI" />
          <AvatarFallback className="bg-zinc-200 dark:bg-zinc-800">
            <Bot className="h-4 w-4" />
          </AvatarFallback>
        </Avatar>
      )}

      <div
        className={cn(
          "flex max-w-[80%] flex-col gap-1",
          isUser ? "items-end" : "items-start",
        )}
      >
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 text-sm",
            isUser
              ? "bg-zinc-900 text-zinc-50 dark:bg-zinc-50 dark:text-zinc-900"
              : isSystem
                ? "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                : "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-50",
          )}
        >
          <div className="prose prose-sm max-w-none break-words dark:prose-invert prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-li:my-1 prose-strong:text-inherit prose-headings:text-inherit prose-a:text-inherit">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => (
                  <p className="whitespace-pre-wrap">{children}</p>
                ),
                code: ({ children, className, ...props }) => (
                  <code
                    className={
                      className ??
                      "rounded bg-black/10 px-1 py-0.5 text-[0.85em] dark:bg-white/10"
                    }
                    {...props}
                  >
                    {children}
                  </code>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-zinc-500">
          {message.timestamp && (
            <span>
              {message.timestamp.toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          )}

          {!isUser && !isSystem && onSpeak && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={() => onSpeak(message.content)}
            >
              <Volume2
                className={cn("h-4 w-4", isSpeaking ? "text-blue-500" : "")}
              />
            </Button>
          )}
        </div>

        {!isUser && !isSystem && message.sources && message.sources.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {message.sources.map((s, i) => {
              const nameWithoutExt = s.source.replace(/\.[^.]+$/, "");
              const truncated = nameWithoutExt.slice(0, 40);
              return (
                <span
                  key={i}
                  title={s.source}
                  className="inline-flex items-center rounded bg-zinc-100 px-1.5 py-0.5 text-[0.7rem] text-zinc-500 dark:bg-zinc-700 dark:text-zinc-400"
                >
                  📄 {truncated}
                  {nameWithoutExt.length > 40 ? "…" : ""}
                </span>
              );
            })}
          </div>
        )}
      </div>

      {isUser && (
        <Avatar className="h-8 w-8 shrink-0">
          <AvatarImage src="" alt="You" />
          <AvatarFallback className="bg-blue-600 text-white">
            <User className="h-4 w-4" />
          </AvatarFallback>
        </Avatar>
      )}
    </div>
  );
}
