"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Plus,
  MessageSquare,
  Trash2,
  LogOut,
  Pencil,
  Check,
  X,
  ChevronLeft,
  ChevronRight,
  HeartPulse,
} from "lucide-react";
import { cn } from "@/lib/utils";

type SupportedLanguage = "en" | "am" | "om" | "ti";

interface Conversation {
  id: string;
  title: string;
  createdAt: Date;
}

interface SidebarCopy {
  appTitle: string;
  newChat: string;
  noConversations: string;
  footerTitle: string;
  footerSupport: string;
  logout: string;
  renameConversation: string;
  languageLabel?: string;
  english?: string;
  amharic?: string;
  oromo?: string;
  tigrinya?: string;
  collapseSidebar?: string;
  expandSidebar?: string;
  copyrightLine?: string;
  developedByLine?: string;
}

interface ChatSidebarProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  onSelectConversation: (id: string | null) => void;
  onNewChat: () => void;
  onDeleteConversation: (id: string) => void;
  onLogout: () => void;
  onRenameConversation?: (id: string, title: string) => void | Promise<void>;
  isLoggedIn: boolean;
  copy: SidebarCopy;
  selectedLanguage?: SupportedLanguage;
  onLanguageChange?: (language: SupportedLanguage) => void;
  onCollapseChange?: (collapsed: boolean) => void;
}

const SIDEBAR_COLLAPSED_STORAGE_KEY = "chatSidebarCollapsed";
const CHAT_LANGUAGE_STORAGE_KEY = "preferredChatLanguage";

export function ChatSidebar({
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  onLogout,
  onRenameConversation,
  isLoggedIn,
  copy,
  selectedLanguage,
  onLanguageChange,
  onCollapseChange,
}: ChatSidebarProps) {
  const [editingConversationId, setEditingConversationId] = useState<
    string | null
  >(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [isSavingRename, setIsSavingRename] = useState(false);

  const [isCollapsed, setIsCollapsed] = useState(false);
  const [internalLanguage, setInternalLanguage] = useState<SupportedLanguage>(
    selectedLanguage ?? "en",
  );

  const editingConversation = useMemo(
    () =>
      conversations.find(
        (conversation) => conversation.id === editingConversationId,
      ) || null,
    [conversations, editingConversationId],
  );

  useEffect(() => {
    if (!editingConversation) return;
    setDraftTitle(editingConversation.title);
  }, [editingConversation]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const storedCollapsed = localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY);
    if (storedCollapsed === "true" || storedCollapsed === "false") {
      setIsCollapsed(storedCollapsed === "true");
    }

    const storedLanguage = localStorage.getItem(
      CHAT_LANGUAGE_STORAGE_KEY,
    ) as SupportedLanguage | null;
    if (storedLanguage && ["en", "am", "om", "ti"].includes(storedLanguage)) {
      setInternalLanguage(storedLanguage);
    }
  }, []);

  useEffect(() => {
    if (selectedLanguage) {
      setInternalLanguage(selectedLanguage);
    }
  }, [selectedLanguage]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    localStorage.setItem(
      SIDEBAR_COLLAPSED_STORAGE_KEY,
      isCollapsed ? "true" : "false",
    );
    onCollapseChange?.(isCollapsed);
  }, [isCollapsed, onCollapseChange]);

  const startRename = (conversation: Conversation) => {
    if (isCollapsed) return;
    setEditingConversationId(conversation.id);
    setDraftTitle(conversation.title);
  };

  const cancelRename = () => {
    if (isSavingRename) return;
    setEditingConversationId(null);
    setDraftTitle("");
  };

  const submitRename = async () => {
    const conversationId = editingConversationId;
    const nextTitle = draftTitle.trim();

    if (!conversationId || !nextTitle || !onRenameConversation) {
      cancelRename();
      return;
    }

    try {
      setIsSavingRename(true);
      await onRenameConversation(conversationId, nextTitle);
      setEditingConversationId(null);
      setDraftTitle("");
    } finally {
      setIsSavingRename(false);
    }
  };

  const handleLanguageChange = (language: SupportedLanguage) => {
    setInternalLanguage(language);
    if (typeof window !== "undefined") {
      localStorage.setItem(CHAT_LANGUAGE_STORAGE_KEY, language);
    }
    onLanguageChange?.(language);
  };

  const toggleCollapsed = () => {
    setIsCollapsed((prev) => !prev);
  };

  return (
    <div className="flex h-full flex-col bg-transparent">
      <div className="flex items-center justify-between p-3">
        {!isCollapsed && (
          <div className="flex min-w-0 items-center gap-2">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-teal-700 text-white shadow-sm dark:bg-teal-400 dark:text-zinc-950">
              <HeartPulse className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                {copy.appTitle}
              </h2>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                Maternal health AI
              </p>
            </div>
          </div>
        )}

        <div
          className={cn(
            "flex items-center gap-1",
            isCollapsed && "w-full justify-center",
          )}
        >
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleCollapsed}
            className="h-8 w-8 rounded-lg"
            aria-label={
              isCollapsed
                ? (copy.expandSidebar ?? "Expand sidebar")
                : (copy.collapseSidebar ?? "Collapse sidebar")
            }
            title={
              isCollapsed
                ? (copy.expandSidebar ?? "Expand sidebar")
                : (copy.collapseSidebar ?? "Collapse sidebar")
            }
          >
            {isCollapsed ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronLeft className="h-4 w-4" />
            )}
          </Button>

          {isLoggedIn && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onLogout}
              className="h-8 w-8 rounded-lg"
              aria-label={copy.logout}
              title={copy.logout}
            >
              <LogOut className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      <div className={cn("mb-3 px-3", isCollapsed && "px-2")}>
        <Button
          variant="outline"
          className={cn(
            "h-10 w-full gap-2 rounded-xl border-zinc-200/80 bg-white/80 shadow-sm hover:border-teal-200 hover:bg-teal-50 dark:border-white/10 dark:bg-white/5 dark:hover:border-teal-400/30 dark:hover:bg-teal-400/10",
            isCollapsed ? "justify-center px-2" : "justify-start",
          )}
          onClick={onNewChat}
          aria-label={copy.newChat}
          title={copy.newChat}
        >
          <Plus className="h-4 w-4" />
          {!isCollapsed && copy.newChat}
        </Button>
      </div>

      <div className={cn("flex-1 overflow-y-auto px-2", isCollapsed && "px-1")}>
        {conversations.length === 0 ? (
          <div
            className={cn(
              "rounded-xl border border-dashed border-zinc-200/80 bg-white/50 px-3 py-8 text-center text-sm text-zinc-500 dark:border-white/10 dark:bg-white/5",
              isCollapsed && "px-1 text-xs",
            )}
            title={copy.noConversations}
          >
            {isCollapsed ? "—" : copy.noConversations}
          </div>
        ) : (
          <div className="space-y-1">
            {conversations.map((conv) => {
              const isEditing = editingConversationId === conv.id;

              return (
                <div
                  key={conv.id}
                  className={cn(
                    "group flex items-center gap-2 rounded-xl px-2.5 py-2.5 text-zinc-700 transition-all dark:text-zinc-200",
                    isEditing
                      ? "bg-white shadow-sm dark:bg-white/10"
                      : activeConversationId === conv.id
                        ? "cursor-pointer bg-teal-50 text-teal-900 shadow-sm ring-1 ring-teal-100 dark:bg-teal-400/10 dark:text-teal-100 dark:ring-teal-400/20"
                        : "cursor-pointer hover:bg-white/80 hover:shadow-sm dark:hover:bg-white/10",
                    isCollapsed && "justify-center px-2",
                  )}
                  onClick={() => {
                    if (!isEditing) onSelectConversation(conv.id);
                  }}
                  title={conv.title}
                >
                  <MessageSquare className="h-4 w-4 shrink-0 text-teal-700 dark:text-teal-300" />

                  {!isCollapsed &&
                    (isEditing ? (
                      <div className="flex min-w-0 flex-1 items-center gap-1">
                        <input
                          value={draftTitle}
                          onChange={(e) => setDraftTitle(e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              void submitRename();
                            }
                            if (e.key === "Escape") {
                              e.preventDefault();
                              cancelRename();
                            }
                          }}
                          className="flex-1 rounded-lg border border-zinc-300 bg-white px-2 py-1 text-sm text-zinc-900 outline-none ring-0 focus:border-teal-500 dark:border-white/10 dark:bg-zinc-950 dark:text-zinc-100"
                          autoFocus
                          disabled={isSavingRename}
                          maxLength={255}
                        />
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={(e) => {
                            e.stopPropagation();
                            void submitRename();
                          }}
                          disabled={isSavingRename || !draftTitle.trim()}
                          aria-label="Save conversation title"
                          title="Save conversation title"
                        >
                          <Check className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={(e) => {
                            e.stopPropagation();
                            cancelRename();
                          }}
                          disabled={isSavingRename}
                          aria-label="Cancel rename"
                          title="Cancel rename"
                        >
                          <X className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    ) : (
                      <>
                        <span className="truncate text-sm">{conv.title}</span>

                        <div className="ml-auto flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                          {onRenameConversation && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6"
                              onClick={(e) => {
                                e.stopPropagation();
                                startRename(conv);
                              }}
                              aria-label={`Rename ${conv.title}`}
                              title={`Rename ${conv.title}`}
                            >
                              <Pencil className="h-3 w-3" />
                            </Button>
                          )}

                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDeleteConversation(conv.id);
                            }}
                            aria-label={`Delete ${conv.title}`}
                            title={`Delete ${conv.title}`}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </>
                    ))}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="border-t border-zinc-200/70 p-3 dark:border-white/10">
        <div className={cn("mb-3", isCollapsed && "mb-2")}>
          {!isCollapsed && (
            <label
              htmlFor="sidebar-language-select"
              className="mb-1.5 block text-xs font-medium text-zinc-600 dark:text-zinc-300"
            >
              {copy.languageLabel ?? "Language"}
            </label>
          )}
          <select
            id="sidebar-language-select"
            value={internalLanguage}
            onChange={(e) =>
              handleLanguageChange(e.target.value as SupportedLanguage)
            }
            className={cn(
              "w-full rounded-xl border border-zinc-200/80 bg-white/80 py-2 text-sm text-zinc-900 outline-none ring-0 transition focus:border-teal-500 dark:border-white/10 dark:bg-white/5 dark:text-zinc-100",
              isCollapsed ? "px-1 text-center" : "px-3",
            )}
            aria-label={copy.languageLabel ?? "Language"}
            title={copy.languageLabel ?? "Language"}
          >
            <option value="en">{copy.english ?? "English"}</option>
            <option value="am">{copy.amharic ?? "አማርኛ"}</option>
            <option value="om">{copy.oromo ?? "Afaan Oromo"}</option>
            <option value="ti">{copy.tigrinya ?? "ትግርኛ"}</option>
          </select>
        </div>

        {!isCollapsed && (
          <div className="text-center text-xs text-zinc-500">
            <p>{copy.footerTitle}</p>
            <p className="mt-1">{copy.footerSupport}</p>
            <p className="mt-2">{copy.copyrightLine ?? "© 2026"}</p>
            <p>{copy.developedByLine ?? "Developed by DerAI"}</p>
          </div>
        )}
      </div>
    </div>
  );
}
