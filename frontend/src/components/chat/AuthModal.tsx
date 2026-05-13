"use client";

import React, { useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getSupabaseClient, isSupabaseConfigured } from "@/lib/supabase";
import { HeartPulse, Loader2 } from "lucide-react";

type SupportedLanguage = "en" | "am" | "om" | "ti";

interface AuthModalCopy {
  title: string;
  description: string;
  loginTab: string;
  signupTab: string;
  email: string;
  password: string;
  emailPlaceholder: string;
  passwordPlaceholder: string;
  loginButton: string;
  loginLoading: string;
  signupButton: string;
  signupLoading: string;
  authFailed: string;
  signupSuccess: string;
}

interface AuthModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAuthSuccess: () => void;
  language?: SupportedLanguage;
}

const COPY: Record<SupportedLanguage, AuthModalCopy> = {
  en: {
    title: "Sign in to save your chats",
    description: "Your conversations will be saved across devices.",
    loginTab: "Login",
    signupTab: "Sign Up",
    email: "Email",
    password: "Password",
    emailPlaceholder: "you@example.com",
    passwordPlaceholder: "••••••••",
    loginButton: "Login",
    loginLoading: "Logging in...",
    signupButton: "Create Account",
    signupLoading: "Creating account...",
    authFailed: "Authentication failed",
    signupSuccess:
      "Account created. Please check your email if confirmation is required.",
  },
  am: {
    title: "ውይይቶችዎን ለማስቀመጥ ይግቡ",
    description: "ውይይቶችዎ በተለያዩ መሳሪያዎች ላይ ይቀመጣሉ።",
    loginTab: "ግባ",
    signupTab: "ተመዝገብ",
    email: "ኢሜይል",
    password: "የይለፍ ቃል",
    emailPlaceholder: "you@example.com",
    passwordPlaceholder: "••••••••",
    loginButton: "ግባ",
    loginLoading: "በመግባት ላይ...",
    signupButton: "መለያ ፍጠር",
    signupLoading: "መለያ በመፍጠር ላይ...",
    authFailed: "ማረጋገጥ አልተሳካም",
    signupSuccess: "መለያው ተፈጥሯል። ማረጋገጫ ካስፈለገ እባክዎ ኢሜይልዎን ይመልከቱ።",
  },
  om: {
    title: "Marii kee kuusuuuf seeni",
    description: "Marii kee meeshaalee adda addaa irratti ni kuufama.",
    loginTab: "Seeni",
    signupTab: "Galmaa'i",
    email: "Imeelii",
    password: "Jecha darbii",
    emailPlaceholder: "you@example.com",
    passwordPlaceholder: "••••••••",
    loginButton: "Seeni",
    loginLoading: "Seenaa jira...",
    signupButton: "Akkaawuntii Uumi",
    signupLoading: "Akkaawuntii uumamaa jira...",
    authFailed: "Mirkaneessuun hin milkoofne",
    signupSuccess:
      "Akkaawuntiin uumameera. Yoo mirkaneessi imeelii barbaachise, imeelii kee ilaali.",
  },
  ti: {
    title: "ዝርርብኩም ንምዕቃብ እተኣተዉ",
    description: "ዝርርብኩም ኣብ ዝተፈላለዩ መሳርሒታት ክቕመጥ እዩ።",
    loginTab: "እቶ",
    signupTab: "ተመዝገብ",
    email: "ኢመይል",
    password: "ቃል ምስጢር",
    emailPlaceholder: "you@example.com",
    passwordPlaceholder: "••••••••",
    loginButton: "እቶ",
    loginLoading: "ብምእታው ላይ...",
    signupButton: "ኣካውንት ፍጠር",
    signupLoading: "ኣካውንት ብምፍጣር ላይ...",
    authFailed: "ምርግጋጽ ኣይተሳኸዐን",
    signupSuccess: "ኣካውንት ተፈጢሩ። ምርግጋጽ ኢመይል እንተደሊዩ ኢመይልኩም ተመልከቱ።",
  },
};

export function AuthModal({
  open,
  onOpenChange,
  onAuthSuccess,
  language = "en",
}: AuthModalProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"login" | "signup">("login");

  const copy = useMemo(() => COPY[language] ?? COPY.en, [language]);

  const handleAuth = async (type: "login" | "signup") => {
    setIsLoading(true);
    setError("");

    try {
      if (!isSupabaseConfigured()) {
        throw new Error("Supabase is not configured.");
      }

      const supabase = getSupabaseClient();

      if (type === "signup") {
        const { error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
      } else {
        const { error } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        if (error) throw error;
      }

      onAuthSuccess();
      onOpenChange(false);
      setEmail("");
      setPassword("");
      setActiveTab("login");
    } catch (err: unknown) {
      const message =
        err instanceof Error && err.message ? err.message : copy.authFailed;
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const submitLabel =
    activeTab === "login"
      ? isLoading
        ? copy.loginLoading
        : copy.loginButton
      : isLoading
        ? copy.signupLoading
        : copy.signupButton;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="border-white/80 bg-white/95 shadow-2xl backdrop-blur-xl dark:border-white/10 dark:bg-zinc-950/95 sm:max-w-[420px] sm:rounded-2xl">
        <DialogHeader className="items-center text-center">
          <div className="mb-2 flex h-12 w-12 items-center justify-center rounded-2xl bg-teal-700 text-white shadow-lg shadow-teal-700/20 dark:bg-teal-400 dark:text-zinc-950">
            <HeartPulse className="h-6 w-6" />
          </div>
          <DialogTitle className="text-xl">{copy.title}</DialogTitle>
          <DialogDescription className="max-w-sm">{copy.description}</DialogDescription>
        </DialogHeader>

        <Tabs
          value={activeTab}
          onValueChange={(value) => setActiveTab(value as "login" | "signup")}
          className="w-full"
        >
          <TabsList className="grid w-full grid-cols-2 rounded-xl bg-zinc-100 p-1 dark:bg-white/10">
            <TabsTrigger value="login">{copy.loginTab}</TabsTrigger>
            <TabsTrigger value="signup">{copy.signupTab}</TabsTrigger>
          </TabsList>

          <TabsContent value="login">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleAuth("login");
              }}
              className="space-y-4"
            >
              <div className="space-y-2">
                <Label htmlFor="login-email">{copy.email}</Label>
                <Input
                  id="login-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={copy.emailPlaceholder}
                  className="rounded-xl"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="login-password">{copy.password}</Label>
                <Input
                  id="login-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={copy.passwordPlaceholder}
                  className="rounded-xl"
                  required
                />
              </div>
              {error && <p className="text-sm text-red-500">{error}</p>}
              <Button
                type="submit"
                className="w-full rounded-xl bg-teal-700 hover:bg-teal-800 dark:bg-teal-400 dark:text-zinc-950 dark:hover:bg-teal-300"
                disabled={isLoading}
              >
                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {submitLabel}
              </Button>
            </form>
          </TabsContent>

          <TabsContent value="signup">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleAuth("signup");
              }}
              className="space-y-4"
            >
              <div className="space-y-2">
                <Label htmlFor="signup-email">{copy.email}</Label>
                <Input
                  id="signup-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={copy.emailPlaceholder}
                  className="rounded-xl"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="signup-password">{copy.password}</Label>
                <Input
                  id="signup-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={copy.passwordPlaceholder}
                  className="rounded-xl"
                  required
                />
              </div>
              {error && <p className="text-sm text-red-500">{error}</p>}
              <Button
                type="submit"
                className="w-full rounded-xl bg-teal-700 hover:bg-teal-800 dark:bg-teal-400 dark:text-zinc-950 dark:hover:bg-teal-300"
                disabled={isLoading}
              >
                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {submitLabel}
              </Button>
            </form>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
