import { createClient, type Session } from "@supabase/supabase-js";

export const SUPPORTED_LANGUAGES = ["en", "am", "om", "ti"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

export interface AnonymousHistoryAttachment {
  type: "image";
  url: string;
  name?: string;
  mimeType?: string;
}

export interface AnonymousHistoryMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string;
  attachment?: AnonymousHistoryAttachment;
}

export interface AnonymousHistoryConversation {
  id: string;
  title: string;
  createdAt: string;
  messages: AnonymousHistoryMessage[];
}

interface SyncConversationsResult {
  importedConversationIds: string[];
  failedConversationIds: string[];
}

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

let supabaseClient: ReturnType<typeof createClient> | null = null;

export function isSupabaseConfigured(): boolean {
  return Boolean(supabaseUrl && supabaseAnonKey);
}

export function getSupabaseClient() {
  if (!isSupabaseConfigured()) {
    throw new Error("Supabase is not configured.");
  }

  if (!supabaseClient) {
    supabaseClient = createClient(supabaseUrl, supabaseAnonKey);
  }

  return supabaseClient;
}

const ANONYMOUS_CONVERSATIONS_KEY = "anonymousConversations";
const AUTH_ERROR_FALLBACKS: Record<SupportedLanguage, string> = {
  en: "Authentication failed. Please try again.",
  am: "ማረጋገጥ አልተሳካም። እባክዎ እንደገና ይሞክሩ።",
  om: "Mirkaneessuun hin milkoofne. Mee irra deebi'ii yaali.",
  ti: "ምርግጋጽ ኣይተሳኸዐን። እንደገና ፈትኑ።",
};

const AUTH_ERROR_MESSAGES: Record<
  string,
  Partial<Record<SupportedLanguage, string>>
> = {
  "invalid login credentials": {
    en: "Invalid email or password.",
    am: "የኢሜይል ወይም የይለፍ ቃል ትክክል አይደለም።",
    om: "Imeelii yookaan jechi darbii sirrii miti.",
    ti: "ኢመይል ወይ ቃል ምስጢር ቅኑዕ ኣይኮነን።",
  },
  "email not confirmed": {
    en: "Please confirm your email before signing in.",
    am: "ከመግባትዎ በፊት ኢሜይልዎን ያረጋግጡ።",
    om: "Osoo hin seenin dura imeelii kee mirkaneessi.",
    ti: "ቅድሚ ምእታውካ ኢመይልካ ኣረጋግጽ።",
  },
  "user already registered": {
    en: "An account with this email already exists.",
    am: "በዚህ ኢሜይል የተመዘገበ መለያ አለ።",
    om: "Imeelii kanaan akkaawuntiin duraan galmaa'e jira.",
    ti: "ብዚ ኢመይል ኣቐዲሙ ዝተመዝገበ ኣካውንት ኣሎ።",
  },
  "password should be at least 6 characters": {
    en: "Password must be at least 6 characters long.",
    am: "የይለፍ ቃል ቢያንስ 6 ፊደላት መሆን አለበት።",
    om: "Jechi darbii qubee 6 yoo xiqqaate qabaachuu qaba.",
    ti: "ቃል ምስጢር ብውሑዱ 6 ፊደላት ክህሉ ኣለዎ።",
  },
  "signup is disabled": {
    en: "Account creation is currently disabled.",
    am: "በአሁኑ ጊዜ መለያ መፍጠር ተዘግቷል።",
    om: "Uuminsi akkaawuntii yeroo ammaa cufameera.",
    ti: "ምፍጣር ኣካውንት ኣብዚ ሕጂ ተዓጽዩ ኣሎ።",
  },
  "email address is invalid": {
    en: "Please enter a valid email address.",
    am: "እባክዎ ትክክለኛ የኢሜይል አድራሻ ያስገቡ።",
    om: "Maaloo teessoo imeelii sirrii galchi.",
    ti: "በጃኻ ቅኑዕ ኣድራሻ ኢመይል ኣእቱ።",
  },
  "network request failed": {
    en: "Network error. Please check your internet connection and try again.",
    am: "የኔትወርክ ችግር አለ። እባክዎ ኢንተርኔትዎን ያረጋግጡ እና እንደገና ይሞክሩ።",
    om: "Rakkoo neetworkii jira. Intarneeta kee ilaaliitii irra deebi'ii yaali.",
    ti: "ጌጋ ኔትወርክ ኣሎ። ኢንተርነትካ ርአ እንደገና ፈትን።",
  },
};

function normalizeLanguage(language?: string): SupportedLanguage {
  return SUPPORTED_LANGUAGES.includes(language as SupportedLanguage)
    ? (language as SupportedLanguage)
    : "en";
}

function normalizeErrorMessage(message: string): string {
  return message.trim().toLowerCase();
}

export function getLocalizedSupabaseAuthError(
  error: unknown,
  language?: string,
): string {
  const normalizedLanguage = normalizeLanguage(language);

  if (!error) {
    return AUTH_ERROR_FALLBACKS[normalizedLanguage];
  }

  if (typeof error === "string") {
    const normalized = normalizeErrorMessage(error);
    return (
      AUTH_ERROR_MESSAGES[normalized]?.[normalizedLanguage] ||
      error ||
      AUTH_ERROR_FALLBACKS[normalizedLanguage]
    );
  }

  if (typeof error === "object" && error !== null) {
    const maybeMessage =
      "message" in error && typeof error.message === "string"
        ? error.message
        : "error_description" in error &&
            typeof error.error_description === "string"
          ? error.error_description
          : "";

    if (!maybeMessage) {
      return AUTH_ERROR_FALLBACKS[normalizedLanguage];
    }

    const normalized = normalizeErrorMessage(maybeMessage);
    return (
      AUTH_ERROR_MESSAGES[normalized]?.[normalizedLanguage] ||
      maybeMessage ||
      AUTH_ERROR_FALLBACKS[normalizedLanguage]
    );
  }

  return AUTH_ERROR_FALLBACKS[normalizedLanguage];
}

export function getAnonymousHistoryFromStorage(): AnonymousHistoryConversation[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(ANONYMOUS_CONVERSATIONS_KEY);
    if (!raw) return [];

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    return parsed.filter(
      (conversation): conversation is AnonymousHistoryConversation =>
        Boolean(
          conversation &&
          typeof conversation.id === "string" &&
          typeof conversation.title === "string" &&
          Array.isArray(conversation.messages),
        ),
    );
  } catch {
    return [];
  }
}

export function saveAnonymousHistoryToStorage(
  conversations: AnonymousHistoryConversation[],
): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(
    ANONYMOUS_CONVERSATIONS_KEY,
    JSON.stringify(conversations),
  );
}

export function clearAnonymousHistoryFromStorage(): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.removeItem(ANONYMOUS_CONVERSATIONS_KEY);
}

async function getAccessTokenFromSession(
  session?: Session | null,
): Promise<string | null> {
  if (session?.access_token) {
    return session.access_token;
  }

  if (!isSupabaseConfigured()) {
    return null;
  }

  const supabase = getSupabaseClient();

  const {
    data: { session: currentSession },
  } = await supabase.auth.getSession();

  return currentSession?.access_token ?? null;
}

export async function syncAnonymousHistoryToBackend(
  apiBaseUrl: string,
  session?: Session | null,
): Promise<SyncConversationsResult> {
  const conversations = getAnonymousHistoryFromStorage();
  if (!conversations.length) {
    return { importedConversationIds: [], failedConversationIds: [] };
  }

  const accessToken = await getAccessTokenFromSession(session);
  if (!accessToken) {
    return {
      importedConversationIds: [],
      failedConversationIds: conversations.map(
        (conversation) => conversation.id,
      ),
    };
  }

  const importedConversationIds: string[] = [];
  const failedConversationIds: string[] = [];

  for (const conversation of conversations) {
    try {
      const createResponse = await fetch(
        `${apiBaseUrl}/api/conversations/conversations`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({
            title: conversation.title || "Imported Conversation",
          }),
        },
      );

      if (!createResponse.ok) {
        throw new Error("Failed to create conversation");
      }

      const created = (await createResponse.json()) as {
        conversation_id: string;
        title: string;
      };

      for (const message of conversation.messages) {
        await fetch(`${apiBaseUrl}/api/chat/chat`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({
            message: message.content,
            conversation_id: created.conversation_id,
            language: "en",
          }),
        });
      }

      importedConversationIds.push(conversation.id);
    } catch {
      failedConversationIds.push(conversation.id);
    }
  }

  if (failedConversationIds.length === 0) {
    clearAnonymousHistoryFromStorage();
  } else {
    const remaining = conversations.filter((conversation) =>
      failedConversationIds.includes(conversation.id),
    );
    saveAnonymousHistoryToStorage(remaining);
  }

  return { importedConversationIds, failedConversationIds };
}
