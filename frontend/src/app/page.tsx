"use client";

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ChatSidebar } from "@/components/chat/ChatSidebar";
import { ChatInput } from "@/components/chat/ChatInput";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { AuthModal } from "@/components/chat/AuthModal";
import { Button } from "@/components/ui/button";
import { HeartPulse, Menu, ShieldCheck, Sparkles, X } from "lucide-react";
import {
  clearAnonymousHistoryFromStorage,
  getSupabaseClient,
  getAnonymousHistoryFromStorage,
  isSupabaseConfigured,
  saveAnonymousHistoryToStorage,
  syncAnonymousHistoryToBackend,
} from "@/lib/supabase";
import { cn } from "@/lib/utils";

type SupportedLanguage = "en" | "am" | "om" | "ti";

interface MessageAttachment {
  type: "image";
  url: string;
  name?: string;
  mimeType?: string;
}

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: Date;
  attachment?: MessageAttachment;
  sources?: Array<{ source: string; file_type?: string }>;
}

interface Conversation {
  id: string;
  title: string;
  createdAt: Date;
  messages: Message[];
}

interface ConversationListItem {
  id: string;
  title: string;
  created_at?: string | null;
  updated_at?: string | null;
  message_count?: number;
}

interface ConversationMessageItem {
  id?: string | null;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string | null;
}

interface ConversationDetailResponse {
  id: string;
  title: string;
  created_at?: string | null;
  updated_at?: string | null;
  messages: ConversationMessageItem[];
}

interface ChatApiResponse {
  response: string;
  conversation_id: string;
  cached?: boolean;
  tts_url?: string | null;
  sources?: Array<{ source: string; file_type?: string }>;
  triage_level?: string | null;
}

interface ImageApiResponse {
  response: string;
  conversation_id: string;
}

interface SpeechApiResponse {
  text: string;
  detected_language?: string | null;
}

interface RenameConversationResponse {
  conversation_id: string;
  title: string;
}

interface InputMetadata {
  language: SupportedLanguage;
  imageName?: string;
  imageMimeType?: string;
}

interface VoiceMetadata {
  language: SupportedLanguage;
}

interface UiCopy {
  pageTitle: string;
  welcomeTitle: string;
  welcomeDescription: string;
  signInToSave: string;
  newChat: string;
  appTitle: string;
  noConversations: string;
  footerTitle: string;
  footerSupport: string;
  logout: string;
  languageLabel: string;
  english: string;
  amharic: string;
  oromo: string;
  tigrinya: string;
  collapseSidebar: string;
  expandSidebar: string;
  copyrightLine: string;
  developedByLine: string;
  loadMore: string;
  loadingMore: string;
  noMoreConversations: string;
  errorGeneric: string;
  errorAudioRead: string;
  errorNoSpeech: string;
  errorAudioProcess: string;
  imageAnalysisFallback: string;
  renameConversation: string;
  renamePrompt: string;
  renameFailed: string;
  syncSuccess: string;
  syncPartial: string;
  syncFailed: string;
  suggestions: string[];
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const CONVERSATIONS_PAGE_SIZE = 20;
const SIDEBAR_COLLAPSED_STORAGE_KEY = "chatSidebarCollapsed";

const UI_COPY: Record<SupportedLanguage, UiCopy> = {
  en: {
    pageTitle: "New Chat",
    welcomeTitle: "Welcome to TenaChat",
    welcomeDescription:
      "Ask me anything about maternal health, family planning, reproductive health, and women's wellness in Ethiopia.",
    signInToSave: "Sign in to save chats",
    newChat: "New Chat",
    appTitle: "TenaChat",
    noConversations: "No conversations yet",
    footerTitle: "TenaChat",
    footerSupport: "Supports English, Amharic, Afaan Oromo, and Tigrinya",
    logout: "Logout",
    languageLabel: "Language",
    english: "English",
    amharic: "አማርኛ",
    oromo: "Afaan Oromo",
    tigrinya: "ትግርኛ",
    collapseSidebar: "Collapse sidebar",
    expandSidebar: "Expand sidebar",
    copyrightLine: "© 2026",
    developedByLine: "Developed by DerAI",
    loadMore: "Load more",
    loadingMore: "Loading more...",
    noMoreConversations: "No more conversations",
    errorGeneric: "Sorry, something went wrong. Please try again.",
    errorAudioRead: "Could not read the recorded audio. Please try again.",
    errorNoSpeech: "No speech was detected. Please try speaking again.",
    errorAudioProcess:
      "Sorry, the audio could not be processed. Please try again.",
    imageAnalysisFallback: "Please analyze this health-related image.",
    renameConversation: "Rename conversation",
    renamePrompt: "Enter a new title for this conversation:",
    renameFailed: "Failed to rename conversation.",
    syncSuccess: "Anonymous chats were synced to your account.",
    syncPartial:
      "Some anonymous chats were synced, but a few could not be imported.",
    syncFailed: "Could not sync anonymous chats to your account.",
    suggestions: [
      "What is obstetric fistula?",
      "How often should I have antenatal care?",
      "What are the signs of breast cancer?",
      "Where can I get family planning services in Addis?",
    ],
  },
  am: {
    pageTitle: "አዲስ ውይይት",
    welcomeTitle: "እንኳን ወደ TenaChat በደህና መጡ",
    welcomeDescription:
      "ስለ የእናቶች ጤና፣ የቤተሰብ ዕቅድ፣ የመራቢያ ጤና እና የሴቶች ጤና በኢትዮጵያ የሚመለከቱ ጥያቄዎችን ይጠይቁ።",
    signInToSave: "ውይይቶችን ለማስቀመጥ ይግቡ",
    newChat: "አዲስ ውይይት",
    appTitle: "የኢትዮጵያ የሴቶች ጤና",
    noConversations: "እስካሁን ምንም ውይይት የለም",
    footerTitle: "TenaChat",
    footerSupport: "እንግሊዝኛ፣ አማርኛ፣ Afaan Oromo እና ትግርኛን ይደግፋል",
    logout: "ውጣ",
    languageLabel: "ቋንቋ",
    english: "English",
    amharic: "አማርኛ",
    oromo: "Afaan Oromo",
    tigrinya: "ትግርኛ",
    collapseSidebar: "ዳር አሞሌን ሰብስብ",
    expandSidebar: "ዳር አሞሌን ዘርጋ",
    copyrightLine: "© 2026",
    developedByLine: "Developed by DerAI",
    loadMore: "ተጨማሪ አሳይ",
    loadingMore: "በመጫን ላይ...",
    noMoreConversations: "ተጨማሪ ውይይቶች የሉም",
    errorGeneric: "ይቅርታ፣ ችግር ተፈጥሯል። እባክዎ እንደገና ይሞክሩ።",
    errorAudioRead: "የተቀዳውን ድምፅ ማንበብ አልተቻለም። እባክዎ እንደገና ይሞክሩ።",
    errorNoSpeech: "ምንም ድምፅ አልተገኘም። እባክዎ እንደገና ይናገሩ።",
    errorAudioProcess: "ይቅርታ፣ ድምፁን ማስኬድ አልተቻለም። እባክዎ እንደገና ይሞክሩ።",
    imageAnalysisFallback: "እባክዎ ይህን ከጤና ጋር የተያያዘ ምስል ይተንትኑ።",
    renameConversation: "ውይይቱን እንደገና ስም ስጥ",
    renamePrompt: "አዲስ የውይይቱን ርዕስ ያስገቡ፦",
    renameFailed: "የውይይቱን ርዕስ መቀየር አልተቻለም።",
    syncSuccess: "ያልተገቡ ውይይቶች ወደ መለያዎ ተዛውረዋል።",
    syncPartial: "አንዳንድ ያልተገቡ ውይይቶች ተዛውረዋል፣ ጥቂቶቹ ግን አልተሳኩም።",
    syncFailed: "ያልተገቡ ውይይቶችን ወደ መለያዎ ማስተላለፍ አልተቻለም።",
    suggestions: [
      "የወሊድ ፊስቱላ ምንድን ነው?",
      "የእርግዝና ክትትል ምን ያህል ጊዜ ልደርስ ይገባል?",
      "የጡት ካንሰር ምልክቶች ምንድን ናቸው?",
      "በአዲስ አበባ የቤተሰብ ዕቅድ አገልግሎት የት ላገኝ እችላለሁ?",
    ],
  },
  om: {
    pageTitle: "Marii Haaraa",
    welcomeTitle: "Baga gara TenaChat dhuftan",
    welcomeDescription:
      "Waa'ee fayyaa haadholii, karoora maatii, fayyaa hormaataa fi fayyaa dubartootaa Itoophiyaa keessatti gaafachuu dandeessu.",
    signInToSave: "Marii kuusuuuf seeni",
    newChat: "Marii Haaraa",
    appTitle: "Fayyaa Dubartootaa Itoophiyaa",
    noConversations: "Marii amma hin jiru",
    footerTitle: "TenaChat",
    footerSupport: "English, አማርኛ, Afaan Oromo fi ትግርኛ ni deeggara",
    logout: "Ba'i",
    languageLabel: "Afaan",
    english: "English",
    amharic: "አማርኛ",
    oromo: "Afaan Oromo",
    tigrinya: "ትግርኛ",
    collapseSidebar: "Gara cinaatti cufi",
    expandSidebar: "Gara cinaatti bani",
    copyrightLine: "© 2026",
    developedByLine: "Developed by DerAI",
    loadMore: "Dabalataan fe'i",
    loadingMore: "Fe'aa jira...",
    noMoreConversations: "Marii dabalataa hin jiru",
    errorGeneric: "Rakkoon uumameera. Mee irra deebi'ii yaali.",
    errorAudioRead:
      "Sagalee waraabame dubbisuu hin dandeenye. Mee irra deebi'ii yaali.",
    errorNoSpeech: "Sagaleen hin argamne. Mee irra deebi'ii dubbadhu.",
    errorAudioProcess:
      "Dhiifama, sagaleen sun hojjetamuu hin dandeenye. Mee irra deebi'ii yaali.",
    imageAnalysisFallback: "Mee suuraa fayyaa waliin walqabatu kana xiinxali.",
    renameConversation: "Maqaa marichaa jijjiiri",
    renamePrompt: "Maqaa haaraa marii kanaaf galchi:",
    renameFailed: "Maqaa marii jijjiiruun hin milkoofne.",
    syncSuccess: "Mariin anon keessaa gara akkaawuntii keetti galfameera.",
    syncPartial:
      "Mariin anon keessaa tokko tokko galfameera; garuu muraasni hin milkoofne.",
    syncFailed:
      "Mariin anon keessaa gara akkaawuntii keetti galchuun hin milkoofne.",
    suggestions: [
      "Fiistulaa ulfaa maal jechuudha?",
      "Tajaajila ulfaa hordoffii yeroo meeqa fudhachuu qaba?",
      "Mallattoon kaansarii harmaa maal fa'i?",
      "Tajaajila karoora maatii Finfinne keessatti eessa argachuu danda'a?",
    ],
  },
  ti: {
    pageTitle: "ሓድሽ ዝርርብ",
    welcomeTitle: "እንቋዕ ናብ TenaChat ብደሓን መጻእኩም",
    welcomeDescription:
      "ብዛዕባ ጥዕና ኣዴታት፣ ውጥን ስድራ፣ ጥዕና ምውላድን ጥዕና ደቂ ኣንስትዮን ኣብ ኢትዮጵያ ሕቶታት ክትሓቱ ትኽእሉ።",
    signInToSave: "ዝርርብ ንምዕቃብ እተኣተዉ",
    newChat: "ሓድሽ ዝርርብ",
    appTitle: "ጥዕና ደቂ ኣንስትዮ ኢትዮጵያ",
    noConversations: "ዛጊት ዝርርብ የለን",
    footerTitle: "TenaChat",
    footerSupport: "English, አማርኛ, Afaan Oromo እና ትግርኛ ይድግፍ",
    logout: "ውጻእ",
    languageLabel: "ቋንቋ",
    english: "English",
    amharic: "አማርኛ",
    oromo: "Afaan Oromo",
    tigrinya: "ትግርኛ",
    collapseSidebar: "ጎናዊ መተሓላለፊ ኣጥብቕ",
    expandSidebar: "ጎናዊ መተሓላለፊ ኣርፍሕ",
    copyrightLine: "© 2026",
    developedByLine: "Developed by DerAI",
    loadMore: "ተወሳኺ ጽዓን",
    loadingMore: "ብምጽዓን ላይ...",
    noMoreConversations: "ተወሳኺ ዝርርባት የለን",
    errorGeneric: "ይቕረታ፣ ጌጋ ተፈጢሩ። እንደገና ፈትኑ።",
    errorAudioRead: "ዝተቐድሐ ድምጺ ከንብብ ኣይተኻእለን። እንደገና ፈትኑ።",
    errorNoSpeech: "ድምጺ ኣይተረኽበን። እንደገና ተዛረቡ።",
    errorAudioProcess: "ይቕረታ፣ እቲ ድምጺ ክሰርሕ ኣይተኻእለን። እንደገና ፈትኑ።",
    imageAnalysisFallback: "በጃኹም ነዚ ምስሊ ምስ ጥዕና ብተኣሳሰረ መልክዕ ተንትኑ።",
    renameConversation: "ስም ዝርርቡ ቀይር",
    renamePrompt: "ሓድሽ ርእሲ ናይዚ ዝርርብ ኣእቱ:",
    renameFailed: "ስም ዝርርቡ ምቕያር ኣይተሳኸዐን።",
    syncSuccess: "ኣኖኒማዊ ዝርርባት ናብ ኣካውንትካ ተዛዊሮም።",
    syncPartial: "ገለ ኣኖኒማዊ ዝርርባት ተዛዊሮም፣ ገለ ግን ኣይተሳኸዑን።",
    syncFailed: "ኣኖኒማዊ ዝርርባት ናብ ኣካውንትካ ምዝዋር ኣይተሳኸዐን።",
    suggestions: [
      "ፊስቱላ ሕርሲ እንታይ እዩ?",
      "ክንደይ ግዜ ናይ ጥንሲ ክትትል ክግበረለይ ኣለዎ?",
      "ምልክታት ካንሰር ጡብ እንታይ እዮም?",
      "ኣብ ኣዲስ ኣበባ ኣገልግሎት ውጥን ስድራ ኣበይ ክረክብ እኽእል?",
    ],
  },
};

function detectTextDirection(_language: SupportedLanguage) {
  return "ltr";
}

function stripMarkdownForSpeech(text: string) {
  return text
    .replace(/!\[[^\]]*\]\([^)]+\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[`*_>#-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function toStoredConversations(conversations: Conversation[]) {
  return conversations.map((conversation) => ({
    id: conversation.id,
    title: conversation.title,
    createdAt: conversation.createdAt.toISOString(),
    messages: conversation.messages.map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      timestamp: message.timestamp?.toISOString(),
      attachment: message.attachment,
    })),
  }));
}

function fromStoredConversations(
  stored: ReturnType<typeof toStoredConversations>,
): Conversation[] {
  return stored.map((conversation) => ({
    id: conversation.id,
    title: conversation.title,
    createdAt: new Date(conversation.createdAt),
    messages: conversation.messages.map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      timestamp: message.timestamp ? new Date(message.timestamp) : new Date(),
      attachment: message.attachment,
    })),
  }));
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [anonymousId, setAnonymousId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [speakingMessageId, setSpeakingMessageId] = useState<string | null>(
    null,
  );
  const [selectedLanguage, setSelectedLanguage] =
    useState<SupportedLanguage>("en");
  const [conversationsOffset, setConversationsOffset] = useState(0);
  const [hasMoreConversations, setHasMoreConversations] = useState(false);
  const [isLoadingMoreConversations, setIsLoadingMoreConversations] =
    useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const copy = useMemo(
    () => UI_COPY[selectedLanguage] ?? UI_COPY.en,
    [selectedLanguage],
  );

  const getRequestHeaders = useCallback(async () => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    if (anonymousId) {
      headers["x-anonymous-id"] = anonymousId;
    }

    if (isSupabaseConfigured()) {
      try {
        const supabase = getSupabaseClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();

        if (session?.access_token) {
          headers.Authorization = `Bearer ${session.access_token}`;
        }
      } catch (error) {
        console.error("Error getting auth session for request headers:", error);
      }
    }

    return headers;
  }, [anonymousId]);

  const persistAnonymousHistory = useCallback(
    (nextConversations: Conversation[]) => {
      if (isLoggedIn) return;
      saveAnonymousHistoryToStorage(toStoredConversations(nextConversations));
    },
    [isLoggedIn],
  );

  const appendSystemMessage = useCallback((content: string) => {
    const systemMessage: Message = {
      id: `msg_${Date.now()}_system`,
      role: "system",
      content,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, systemMessage]);
  }, []);

  const loadConversationDetail = useCallback(
    async (conversationId: string) => {
      try {
        if (!isSupabaseConfigured()) {
          return;
        }

        const supabase = getSupabaseClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();

        const accessToken = session?.access_token;
        if (!accessToken) return;

        const response = await fetch(
          `${API_BASE_URL}/api/conversations/conversations/${conversationId}`,
          {
            headers: {
              Authorization: `Bearer ${accessToken}`,
            },
          },
        );

        if (!response.ok) {
          throw new Error("Failed to load conversation detail");
        }

        const data: ConversationDetailResponse = await response.json();

        const loadedMessages: Message[] = data.messages.map((item, index) => ({
          id: item.id || `${conversationId}_${index}`,
          role: item.role,
          content: item.content,
          timestamp: item.timestamp ? new Date(item.timestamp) : new Date(),
        }));

        setMessages(loadedMessages);
        setConversations((prev) =>
          prev.map((conversation) =>
            conversation.id === conversationId
              ? {
                  ...conversation,
                  title: data.title || conversation.title,
                  createdAt: data.created_at
                    ? new Date(data.created_at)
                    : conversation.createdAt,
                  messages: loadedMessages,
                }
              : conversation,
          ),
        );
      } catch (error) {
        console.error("Error loading conversation detail:", error);
        appendSystemMessage(copy.errorGeneric);
      }
    },
    [appendSystemMessage, copy.errorGeneric],
  );

  const loadSavedConversations = useCallback(
    async (options?: { append?: boolean }) => {
      try {
        if (!isSupabaseConfigured()) {
          setConversations([]);
          setConversationsOffset(0);
          setHasMoreConversations(false);
          return;
        }

        const supabase = getSupabaseClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();

        const accessToken = session?.access_token;
        if (!accessToken) {
          setConversations([]);
          setConversationsOffset(0);
          setHasMoreConversations(false);
          return;
        }

        const append = options?.append ?? false;
        const offset = append ? conversationsOffset : 0;

        if (append) {
          setIsLoadingMoreConversations(true);
        }

        const response = await fetch(
          `${API_BASE_URL}/api/conversations/conversations?limit=${CONVERSATIONS_PAGE_SIZE}&offset=${offset}`,
          {
            headers: {
              Authorization: `Bearer ${accessToken}`,
            },
          },
        );

        if (!response.ok) {
          throw new Error("Failed to load conversations");
        }

        const data: ConversationListItem[] = await response.json();

        const mapped = data.map((item) => ({
          id: item.id,
          title: item.title || copy.newChat,
          createdAt: item.created_at ? new Date(item.created_at) : new Date(),
          messages: [],
        }));

        setConversations((prev) => {
          if (!append) {
            return mapped;
          }

          const existingIds = new Set(
            prev.map((conversation) => conversation.id),
          );
          const nextPage = mapped.filter(
            (conversation) => !existingIds.has(conversation.id),
          );
          return [...prev, ...nextPage];
        });

        const nextOffset = offset + mapped.length;
        setConversationsOffset(nextOffset);
        setHasMoreConversations(mapped.length === CONVERSATIONS_PAGE_SIZE);
      } catch (error) {
        console.error("Error loading conversations:", error);
      } finally {
        setIsLoadingMoreConversations(false);
      }
    },
    [conversationsOffset, copy.newChat],
  );

  const updateConversationTitle = useCallback(
    async (conversationId: string, nextTitle: string) => {
      const trimmedTitle = nextTitle.trim();
      if (!trimmedTitle) return;

      if (!isLoggedIn) {
        setConversations((prev) => {
          const next = prev.map((conversation) =>
            conversation.id === conversationId
              ? { ...conversation, title: trimmedTitle }
              : conversation,
          );
          persistAnonymousHistory(next);
          return next;
        });
        return;
      }

      try {
        if (!isSupabaseConfigured()) {
          throw new Error("Supabase is not configured.");
        }

        const supabase = getSupabaseClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();

        const accessToken = session?.access_token;
        if (!accessToken) {
          throw new Error("Missing access token");
        }

        const response = await fetch(
          `${API_BASE_URL}/api/conversations/conversations/${conversationId}`,
          {
            method: "PATCH",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${accessToken}`,
            },
            body: JSON.stringify({ title: trimmedTitle }),
          },
        );

        if (!response.ok) {
          throw new Error("Failed to rename conversation");
        }

        const data: RenameConversationResponse = await response.json();

        setConversations((prev) =>
          prev.map((conversation) =>
            conversation.id === conversationId
              ? { ...conversation, title: data.title || trimmedTitle }
              : conversation,
          ),
        );
      } catch (error) {
        console.error("Error renaming conversation:", error);
        appendSystemMessage(copy.renameFailed);
      }
    },
    [
      appendSystemMessage,
      copy.renameFailed,
      isLoggedIn,
      persistAnonymousHistory,
    ],
  );

  const upsertConversation = useCallback(
    (conversationId: string, title: string, nextMessages: Message[]) => {
      setConversations((prev) => {
        const existing = prev.find(
          (conversation) => conversation.id === conversationId,
        );

        const next = existing
          ? prev.map((conversation) =>
              conversation.id === conversationId
                ? {
                    ...conversation,
                    title:
                      conversation.title || title.slice(0, 50) || copy.newChat,
                    messages: nextMessages,
                  }
                : conversation,
            )
          : [
              {
                id: conversationId,
                title: title.slice(0, 50) || copy.newChat,
                createdAt: new Date(),
                messages: nextMessages,
              },
              ...prev,
            ];

        persistAnonymousHistory(next);
        return next;
      });
    },
    [copy.newChat, persistAnonymousHistory],
  );

  const sendTextMessage = useCallback(
    async (
      content: string,
      language: SupportedLanguage,
    ): Promise<ChatApiResponse> => {
      const headers = await getRequestHeaders();
      const response = await fetch(`${API_BASE_URL}/api/chat/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          message: content,
          ...(activeConversationId && {
            conversation_id: activeConversationId,
          }),
          language,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to get text response");
      }

      return response.json();
    },
    [activeConversationId, getRequestHeaders],
  );

  const sendImageMessage = useCallback(
    async (
      content: string,
      image: string,
      metadata?: InputMetadata,
    ): Promise<ImageApiResponse> => {
      const imageBase64 = image.includes(",") ? image.split(",")[1] : image;
      const headers = await getRequestHeaders();

      const response = await fetch(`${API_BASE_URL}/api/chat/image`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          image_base64: imageBase64,
          message: content || copy.imageAnalysisFallback,
          language: metadata?.language ?? selectedLanguage,
          ...(activeConversationId && {
            conversation_id: activeConversationId,
          }),
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to analyze image");
      }

      return response.json();
    },
    [
      activeConversationId,
      copy.imageAnalysisFallback,
      getRequestHeaders,
      selectedLanguage,
    ],
  );

  const sendMessage = useCallback(
    async (content: string, image?: string, metadata?: InputMetadata) => {
      const trimmedContent = content.trim();
      if (!trimmedContent && !image) return;

      const language = metadata?.language ?? selectedLanguage;

      const userMessage: Message = {
        id: `msg_${Date.now()}`,
        role: "user",
        content: trimmedContent || copy.imageAnalysisFallback,
        timestamp: new Date(),
        attachment: image
          ? {
              type: "image",
              url: image,
              name: metadata?.imageName,
              mimeType: metadata?.imageMimeType,
            }
          : undefined,
      };

      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);

      try {
        const data = image
          ? await sendImageMessage(trimmedContent, image, metadata)
          : await sendTextMessage(trimmedContent, language);

        const assistantMessage: Message = {
          id: `msg_${Date.now()}_ai`,
          role: "assistant",
          content: data.response,
          timestamp: new Date(),
          sources: (data as ChatApiResponse).sources ?? [],
        };

        setMessages((prev) => {
          const nextMessages = [...prev, assistantMessage];
          if (data.conversation_id) {
            upsertConversation(
              data.conversation_id,
              trimmedContent || copy.newChat,
              nextMessages,
            );
          }
          return nextMessages;
        });

        if (data.conversation_id) {
          setActiveConversationId(data.conversation_id);
        }
      } catch (error) {
        console.error("Error sending message:", error);
        appendSystemMessage(copy.errorGeneric);
      } finally {
        setIsLoading(false);
      }
    },
    [
      appendSystemMessage,
      copy.errorGeneric,
      copy.imageAnalysisFallback,
      copy.newChat,
      selectedLanguage,
      sendImageMessage,
      sendTextMessage,
      upsertConversation,
    ],
  );

  const sendVoice = useCallback(
    async (audioBlob: Blob, metadata?: VoiceMetadata) => {
      const reader = new FileReader();

      reader.onloadend = async () => {
        const base64 = reader.result?.toString().split(",")[1];
        if (!base64) {
          appendSystemMessage(copy.errorAudioRead);
          return;
        }

        setIsLoading(true);

        try {
          const headers = await getRequestHeaders();
          const response = await fetch(`${API_BASE_URL}/api/chat/speech`, {
            method: "POST",
            headers,
            body: JSON.stringify({
              audio_base64: base64,
              format: "webm",
              language_hint: metadata?.language ?? selectedLanguage,
            }),
          });

          if (!response.ok) {
            throw new Error("Failed to transcribe audio");
          }

          const data: SpeechApiResponse = await response.json();

          if (!data.text?.trim()) {
            appendSystemMessage(copy.errorNoSpeech);
            return;
          }

          await sendMessage(data.text.trim(), undefined, {
            language: metadata?.language ?? selectedLanguage,
          });
        } catch (error) {
          console.error("Error transcribing audio:", error);
          appendSystemMessage(copy.errorAudioProcess);
        } finally {
          setIsLoading(false);
        }
      };

      reader.readAsDataURL(audioBlob);
    },
    [
      appendSystemMessage,
      copy.errorAudioProcess,
      copy.errorAudioRead,
      copy.errorNoSpeech,
      getRequestHeaders,
      selectedLanguage,
      sendMessage,
    ],
  );

  const handleSpeak = useCallback(
    async (text: string, messageId: string) => {
      const cleanedText = stripMarkdownForSpeech(text);
      if (!cleanedText) return;

      setSpeakingMessageId(messageId);

      try {
        const response = await fetch(
          `${API_BASE_URL}/api/chat/tts?text=${encodeURIComponent(cleanedText)}`,
        );

        if (!response.ok) {
          throw new Error("TTS request failed");
        }

        const contentType = response.headers.get("content-type") || "";

        if (contentType.startsWith("audio/")) {
          const audioBlob = await response.blob();
          const audioUrl = URL.createObjectURL(audioBlob);
          const audio = new Audio(audioUrl);
          audio.onended = () => {
            URL.revokeObjectURL(audioUrl);
            setSpeakingMessageId(null);
          };
          audio.onerror = () => {
            URL.revokeObjectURL(audioUrl);
            setSpeakingMessageId(null);
          };
          await audio.play();
          return;
        }

        if ("speechSynthesis" in window) {
          window.speechSynthesis.cancel();
          const utterance = new SpeechSynthesisUtterance(cleanedText);
          utterance.lang =
            selectedLanguage === "am"
              ? "am-ET"
              : selectedLanguage === "om"
                ? "om-ET"
                : selectedLanguage === "ti"
                  ? "ti-ET"
                  : "en-US";
          utterance.onend = () => setSpeakingMessageId(null);
          utterance.onerror = () => setSpeakingMessageId(null);
          window.speechSynthesis.speak(utterance);
          return;
        }

        setSpeakingMessageId(null);
      } catch (error) {
        console.error("Error speaking text:", error);
        if ("speechSynthesis" in window) {
          window.speechSynthesis.cancel();
          const utterance = new SpeechSynthesisUtterance(cleanedText);
          utterance.lang =
            selectedLanguage === "am"
              ? "am-ET"
              : selectedLanguage === "om"
                ? "om-ET"
                : selectedLanguage === "ti"
                  ? "ti-ET"
                  : "en-US";
          utterance.onend = () => setSpeakingMessageId(null);
          utterance.onerror = () => setSpeakingMessageId(null);
          window.speechSynthesis.speak(utterance);
        } else {
          setSpeakingMessageId(null);
        }
      }
    },
    [selectedLanguage],
  );

  const startNewChat = useCallback(() => {
    setMessages([]);
    setActiveConversationId(null);
    setSidebarOpen(false);
  }, []);

  const selectConversation = useCallback(
    async (id: string | null) => {
      setActiveConversationId(id);

      if (!id) {
        setMessages([]);
        setSidebarOpen(false);
        return;
      }

      const conversation = conversations.find((item) => item.id === id);

      if (conversation?.messages?.length) {
        setMessages(conversation.messages);
      } else {
        setMessages([]);
      }

      setSidebarOpen(false);
    },
    [conversations],
  );

  const deleteConversation = useCallback(
    async (id: string) => {
      if (isLoggedIn) {
        try {
          if (!isSupabaseConfigured()) {
            throw new Error("Supabase is not configured.");
          }

          const supabase = getSupabaseClient();
          const {
            data: { session },
          } = await supabase.auth.getSession();

          const accessToken = session?.access_token;
          if (accessToken) {
            await fetch(
              `${API_BASE_URL}/api/conversations/conversations/${id}`,
              {
                method: "DELETE",
                headers: {
                  Authorization: `Bearer ${accessToken}`,
                },
              },
            );
          }
        } catch (error) {
          console.error("Error deleting conversation:", error);
        }
      }

      setConversations((prev) => {
        const next = prev.filter((conversation) => conversation.id !== id);
        persistAnonymousHistory(next);
        return next;
      });

      if (activeConversationId === id) {
        startNewChat();
      }
    },
    [activeConversationId, isLoggedIn, persistAnonymousHistory, startNewChat],
  );

  const loadAnonymousConversations = useCallback(() => {
    const stored = getAnonymousHistoryFromStorage();
    if (!stored.length) return;

    const shouldAutoSelectFirstConversation =
      conversations.length === 0 && !activeConversationId;

    const parsed = fromStoredConversations(
      stored as ReturnType<typeof toStoredConversations>,
    );
    setConversations(parsed);
    setConversationsOffset(parsed.length);
    setHasMoreConversations(false);

    if (shouldAutoSelectFirstConversation && parsed.length > 0) {
      const first = parsed[0];
      setActiveConversationId(first.id);
      setMessages(first.messages);
    }
  }, [activeConversationId, conversations.length]);

  const syncAnonymousHistoryAfterLogin = useCallback(async () => {
    const anonymousConversations = getAnonymousHistoryFromStorage();
    if (!anonymousConversations.length) {
      return;
    }

    try {
      if (!isSupabaseConfigured()) {
        appendSystemMessage(copy.syncFailed);
        return;
      }

      const supabase = getSupabaseClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();

      const result = await syncAnonymousHistoryToBackend(API_BASE_URL, session);

      if (
        result.importedConversationIds.length > 0 &&
        result.failedConversationIds.length === 0
      ) {
        appendSystemMessage(copy.syncSuccess);
      } else if (result.importedConversationIds.length > 0) {
        appendSystemMessage(copy.syncPartial);
      } else if (result.failedConversationIds.length > 0) {
        appendSystemMessage(copy.syncFailed);
      }

      if (result.importedConversationIds.length > 0) {
        clearAnonymousHistoryFromStorage();
        setMessages([]);
        setActiveConversationId(null);
        setConversations([]);
        setConversationsOffset(0);
        setHasMoreConversations(false);
        await loadSavedConversations();
      }
    } catch (error) {
      console.error("Error syncing anonymous history:", error);
      appendSystemMessage(copy.syncFailed);
    }
  }, [
    appendSystemMessage,
    copy.syncFailed,
    copy.syncPartial,
    copy.syncSuccess,
    loadSavedConversations,
  ]);

  const loadMoreConversations = useCallback(async () => {
    if (!isLoggedIn || !hasMoreConversations || isLoadingMoreConversations) {
      return;
    }
    await loadSavedConversations({ append: true });
  }, [
    hasMoreConversations,
    isLoggedIn,
    isLoadingMoreConversations,
    loadSavedConversations,
  ]);

  const handleLogout = useCallback(async () => {
    if (!isSupabaseConfigured()) {
      setIsLoggedIn(false);
      setConversations([]);
      setMessages([]);
      setActiveConversationId(null);
      setConversationsOffset(0);
      setHasMoreConversations(false);
      loadAnonymousConversations();
      return;
    }

    const supabase = getSupabaseClient();
    await supabase.auth.signOut();
    setIsLoggedIn(false);
    setConversations([]);
    setMessages([]);
    setActiveConversationId(null);
    setConversationsOffset(0);
    setHasMoreConversations(false);
    loadAnonymousConversations();
  }, [loadAnonymousConversations]);

  useEffect(() => {
    const checkAuth = async () => {
      if (!isSupabaseConfigured()) {
        setIsLoggedIn(false);
        loadAnonymousConversations();
        return;
      }

      const supabase = getSupabaseClient();
      const {
        data: { user },
      } = await supabase.auth.getUser();
      const authenticated = !!user;
      setIsLoggedIn(authenticated);

      if (!authenticated) {
        loadAnonymousConversations();
      }
    };

    void checkAuth();

    if (!isSupabaseConfigured()) {
      return;
    }

    const supabase = getSupabaseClient();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, session) => {
      const isAuthenticated = !!session?.user;
      setIsLoggedIn(isAuthenticated);

      if (!isAuthenticated) {
        setConversations([]);
        setMessages([]);
        setActiveConversationId(null);
        setConversationsOffset(0);
        setHasMoreConversations(false);
        loadAnonymousConversations();
        return;
      }

      setConversations([]);
      setMessages([]);
      setActiveConversationId(null);
      setConversationsOffset(0);
      setHasMoreConversations(false);

      await syncAnonymousHistoryAfterLogin();
      await loadSavedConversations();
    });

    return () => subscription.unsubscribe();
  }, [
    loadAnonymousConversations,
    loadSavedConversations,
    syncAnonymousHistoryAfterLogin,
  ]);

  useEffect(() => {
    const savedId = localStorage.getItem("anonymousId");
    if (savedId) {
      setAnonymousId(savedId);
    } else {
      const newId = `anon_${Date.now()}`;
      localStorage.setItem("anonymousId", newId);
      setAnonymousId(newId);
    }

    const savedLanguage = localStorage.getItem(
      "preferredChatLanguage",
    ) as SupportedLanguage | null;
    if (savedLanguage && ["en", "am", "om", "ti"].includes(savedLanguage)) {
      setSelectedLanguage(savedLanguage);
    }

    const savedSidebarCollapsed = localStorage.getItem(
      SIDEBAR_COLLAPSED_STORAGE_KEY,
    );
    if (savedSidebarCollapsed === "true" || savedSidebarCollapsed === "false") {
      setIsSidebarCollapsed(savedSidebarCollapsed === "true");
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("preferredChatLanguage", selectedLanguage);
    document.documentElement.lang = selectedLanguage;
    document.documentElement.dir = detectTextDirection(selectedLanguage);
  }, [selectedLanguage]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (isLoggedIn) {
      void loadSavedConversations();
    }
  }, [isLoggedIn, loadSavedConversations]);

  useEffect(() => {
    if (activeConversationId && isLoggedIn) {
      const conversation = conversations.find(
        (item) => item.id === activeConversationId,
      );

      if (conversation && conversation.messages.length === 0) {
        void loadConversationDetail(activeConversationId);
      }
    }
  }, [activeConversationId, conversations, isLoggedIn, loadConversationDetail]);

  return (
    <div className="flex h-screen overflow-hidden bg-[radial-gradient(circle_at_top_left,#ecfeff_0,#f8fafc_32%,#ffffff_64%)] text-zinc-950 dark:bg-[radial-gradient(circle_at_top_left,#0f172a_0,#09090b_48%,#020617_100%)] dark:text-zinc-50">
      <Button
        variant="ghost"
        size="icon"
        className="fixed left-4 top-4 z-50 border border-white/70 bg-white/90 shadow-sm backdrop-blur lg:hidden dark:border-white/10 dark:bg-zinc-950/80"
        onClick={() => setSidebarOpen(!sidebarOpen)}
      >
        {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </Button>

      <div
        className={cn(
          "fixed inset-y-0 left-0 z-40 w-72 transform transition-[transform,width] duration-300 lg:relative lg:translate-x-0",
          isSidebarCollapsed ? "lg:w-20" : "lg:w-72",
          sidebarOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-full flex-col border-r border-white/70 bg-white/80 shadow-[8px_0_40px_rgba(15,23,42,0.06)] backdrop-blur-xl dark:border-white/10 dark:bg-zinc-950/70">
          <div className="min-h-0 flex-1">
            <ChatSidebar
              conversations={conversations}
              activeConversationId={activeConversationId}
              onSelectConversation={selectConversation}
              onNewChat={startNewChat}
              onDeleteConversation={deleteConversation}
              onLogout={handleLogout}
              isLoggedIn={isLoggedIn}
              onRenameConversation={updateConversationTitle}
              selectedLanguage={selectedLanguage}
              onLanguageChange={setSelectedLanguage}
              onCollapseChange={setIsSidebarCollapsed}
              copy={{
                appTitle: copy.appTitle,
                newChat: copy.newChat,
                noConversations: copy.noConversations,
                footerTitle: copy.footerTitle,
                footerSupport: copy.footerSupport,
                logout: copy.logout,
                renameConversation: copy.renameConversation,
                languageLabel: copy.languageLabel,
                english: copy.english,
                amharic: copy.amharic,
                oromo: copy.oromo,
                tigrinya: copy.tigrinya,
                collapseSidebar: copy.collapseSidebar,
                expandSidebar: copy.expandSidebar,
                copyrightLine: copy.copyrightLine,
                developedByLine: copy.developedByLine,
              }}
            />
          </div>

          {isLoggedIn && (
            <div className="border-t border-zinc-200/70 p-3 dark:border-white/10">
              {hasMoreConversations ? (
                <Button
                  variant="outline"
                  className="w-full"
                  disabled={isLoadingMoreConversations}
                  onClick={() => void loadMoreConversations()}
                >
                  {isLoadingMoreConversations
                    ? copy.loadingMore
                    : copy.loadMore}
                </Button>
              ) : conversations.length > 0 ? (
                <p className="text-center text-xs text-zinc-500">
                  {copy.noMoreConversations}
                </p>
              ) : null}
            </div>
          )}
        </div>
      </div>

      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-white/70 bg-white/75 px-4 py-3 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-zinc-950/60">
          <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3">
            <div className="min-w-0 pl-12 lg:pl-0">
              <div className="flex items-center gap-2 text-xs font-medium text-teal-700 dark:text-teal-300">
                <HeartPulse className="h-4 w-4" />
                <span>TenaChat Health Assistant</span>
              </div>
              <h1 className="truncate text-base font-semibold text-zinc-950 dark:text-zinc-50 sm:text-lg">
                {activeConversationId
                  ? conversations.find((c) => c.id === activeConversationId)
                      ?.title || copy.pageTitle
                  : copy.pageTitle}
              </h1>
            </div>

            <nav className="hidden items-center gap-1 rounded-full border border-zinc-200/80 bg-white/80 p-1 text-sm shadow-sm dark:border-white/10 dark:bg-white/5 md:flex">
              <button className="rounded-full bg-zinc-950 px-3 py-1.5 text-white dark:bg-white dark:text-zinc-950">
                Chat
              </button>
              <button className="rounded-full px-3 py-1.5 text-zinc-600 transition hover:bg-zinc-100 hover:text-zinc-950 dark:text-zinc-300 dark:hover:bg-white/10 dark:hover:text-white">
                History
              </button>
              <button className="rounded-full px-3 py-1.5 text-zinc-600 transition hover:bg-zinc-100 hover:text-zinc-950 dark:text-zinc-300 dark:hover:bg-white/10 dark:hover:text-white">
                Languages
              </button>
            </nav>

            {!isLoggedIn && (
              <Button
                variant="default"
                size="sm"
                className="shrink-0 bg-teal-700 shadow-sm hover:bg-teal-800 dark:bg-teal-400 dark:text-zinc-950 dark:hover:bg-teal-300"
                onClick={() => setShowAuthModal(true)}
              >
                {copy.signInToSave}
              </Button>
            )}

            {isLoggedIn && (
              <div className="hidden items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-300 sm:flex">
                <ShieldCheck className="h-4 w-4" />
                Saved
              </div>
            )}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <div className="flex min-h-full items-center justify-center px-4 py-10">
              <div className="w-full max-w-3xl text-center">
                <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-teal-700 text-white shadow-lg shadow-teal-700/20 dark:bg-teal-400 dark:text-zinc-950">
                  <Sparkles className="h-7 w-7" />
                </div>
                <h2 className="mb-3 text-3xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50 sm:text-4xl">
                  {copy.welcomeTitle}
                </h2>
                <p className="mx-auto mb-8 max-w-2xl text-base leading-7 text-zinc-600 dark:text-zinc-300">
                  {copy.welcomeDescription}
                </p>
                <div className="mx-auto grid max-w-2xl gap-2 sm:grid-cols-2">
                  {copy.suggestions.map((suggestion, index) => (
                    <Button
                      key={index}
                      variant="outline"
                      className="h-auto justify-start whitespace-normal rounded-xl border-zinc-200/80 bg-white/85 px-4 py-3 text-left text-sm shadow-sm backdrop-blur transition hover:-translate-y-0.5 hover:border-teal-200 hover:bg-teal-50 dark:border-white/10 dark:bg-white/5 dark:hover:border-teal-400/30 dark:hover:bg-teal-400/10"
                      onClick={() =>
                        sendMessage(suggestion, undefined, {
                          language: selectedLanguage,
                        })
                      }
                    >
                      {suggestion}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="mx-auto flex w-full max-w-5xl flex-col px-2 py-6 sm:px-4">
              {messages.map((msg) => (
                <div key={msg.id} className="flex flex-col">
                  {msg.attachment?.type === "image" && (
                    <div
                      className={cn(
                        "px-4",
                        msg.role === "user" ? "self-end" : "self-start",
                      )}
                    >
                      <div className="mb-2 max-w-[320px] overflow-hidden rounded-2xl border border-zinc-200/80 bg-white/90 p-2 shadow-sm dark:border-white/10 dark:bg-white/5">
                        <img
                          src={msg.attachment.url}
                          alt={msg.attachment.name || "Uploaded image"}
                          className="max-h-72 w-full rounded-xl object-cover"
                        />
                        {msg.attachment.name && (
                          <p className="mt-2 truncate text-xs text-zinc-500">
                            {msg.attachment.name}
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                  <ChatMessage
                    message={msg}
                    onSpeak={(text) => handleSpeak(text, msg.id)}
                    isSpeaking={speakingMessageId === msg.id}
                  />
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <div className="border-t border-white/70 bg-white/75 p-3 backdrop-blur-xl dark:border-white/10 dark:bg-zinc-950/60 sm:p-4">
          <div className="mx-auto w-full max-w-4xl">
            <ChatInput
              onSendMessage={sendMessage}
              onSendVoice={sendVoice}
              disabled={isLoading}
              isLoading={isLoading}
              selectedLanguage={selectedLanguage}
            />
          </div>
        </div>
      </div>

      <AuthModal
        open={showAuthModal}
        onOpenChange={setShowAuthModal}
        onAuthSuccess={() => {
          setIsLoggedIn(true);
          void syncAnonymousHistoryAfterLogin();
          void loadSavedConversations();
        }}
        language={selectedLanguage}
      />
    </div>
  );
}
