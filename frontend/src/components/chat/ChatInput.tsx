"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send, Mic, Image, Loader2, Trash2 } from "lucide-react";

type SupportedLanguage = "en" | "am" | "om" | "ti";

interface ChatInputLabels {
  placeholder: string;
  recording: string;
  newImageAlt: string;
  send: string;
  selectLanguage: string;
  imageButton: string;
  voiceButton: string;
  removeImage: string;
  english: string;
  amharic: string;
  oromo: string;
  tigrinya: string;
}

interface ChatInputProps {
  onSendMessage: (
    message: string,
    image?: string,
    metadata?: {
      language: SupportedLanguage;
      imageName?: string;
      imageMimeType?: string;
    },
  ) => void;
  onSendVoice: (
    audioBlob: Blob,
    metadata?: { language: SupportedLanguage },
  ) => void;
  disabled?: boolean;
  isLoading?: boolean;
  selectedLanguage?: SupportedLanguage;
}

const LABELS: Record<SupportedLanguage, ChatInputLabels> = {
  en: {
    placeholder: "Message the chatbot...",
    recording: "Recording...",
    newImageAlt: "Preview",
    send: "Send",
    selectLanguage: "Language",
    imageButton: "Upload image",
    voiceButton: "Record voice",
    removeImage: "Remove image",
    english: "English",
    amharic: "አማርኛ",
    oromo: "Afaan Oromo",
    tigrinya: "ትግርኛ",
  },
  am: {
    placeholder: "ለቻትቦቱ መልዕክት ይጻፉ...",
    recording: "በመቅዳት ላይ...",
    newImageAlt: "ቅድመ እይታ",
    send: "ላክ",
    selectLanguage: "ቋንቋ",
    imageButton: "ምስል ጫን",
    voiceButton: "ድምፅ ቅዳ",
    removeImage: "ምስሉን አስወግድ",
    english: "English",
    amharic: "አማርኛ",
    oromo: "Afaan Oromo",
    tigrinya: "ትግርኛ",
  },
  om: {
    placeholder: "Ergaa gara chatbot tti barreessi...",
    recording: "Sagalee waraabaa jira...",
    newImageAlt: "Durargii",
    send: "Ergi",
    selectLanguage: "Afaan",
    imageButton: "Suuraa olkaa'i",
    voiceButton: "Sagalee waraabi",
    removeImage: "Suuraa keessaa haqi",
    english: "English",
    amharic: "አማርኛ",
    oromo: "Afaan Oromo",
    tigrinya: "ትግርኛ",
  },
  ti: {
    placeholder: "መልእኽቲ ናብ ቻትቦት ጽሓፍ...",
    recording: "ድምጺ ብምቕዳሕ ላይ...",
    newImageAlt: "ቅድመ ርእይቶ",
    send: "ስደድ",
    selectLanguage: "ቋንቋ",
    imageButton: "ስእሊ ጽዓን",
    voiceButton: "ድምጺ ቅዳሕ",
    removeImage: "ስእሊ ኣውጽእ",
    english: "English",
    amharic: "አማርኛ",
    oromo: "Afaan Oromo",
    tigrinya: "ትግርኛ",
  },
};

export function ChatInput({
  onSendMessage,
  onSendVoice,
  disabled,
  isLoading,
  selectedLanguage = "en",
}: ChatInputProps) {
  const [message, setMessage] = useState("");
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageName, setImageName] = useState<string | null>(null);
  const [imageMimeType, setImageMimeType] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const labels = useMemo(
    () => LABELS[selectedLanguage] ?? LABELS.en,
    [selectedLanguage],
  );

  useEffect(() => {
    if (!textareaRef.current) return;
    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height = `${Math.min(
      textareaRef.current.scrollHeight,
      200,
    )}px`;
  }, [message]);

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
      if (mediaRecorderRef.current?.stream) {
        mediaRecorderRef.current.stream
          .getTracks()
          .forEach((track) => track.stop());
      }
    };
  }, []);

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if ((!message.trim() && !imagePreview) || disabled) return;

    onSendMessage(message, imagePreview || undefined, {
      language: selectedLanguage,
      imageName: imageName ?? undefined,
      imageMimeType: imageMimeType ?? undefined,
    });

    setMessage("");
    setImagePreview(null);
    setImageName(null);
    setImageMimeType(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onloadend = () => {
      setImagePreview(reader.result as string);
      setImageName(file.name);
      setImageMimeType(file.type || "image/jpeg");
    };
    reader.readAsDataURL(file);
  };

  const removeImage = () => {
    setImagePreview(null);
    setImageName(null);
    setImageMimeType(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorderRef.current = new MediaRecorder(stream);
      chunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorderRef.current.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        onSendVoice(blob, { language: selectedLanguage });
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorderRef.current.start();
      setIsRecording(true);
      setRecordingTime(0);

      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => prev + 1);
      }, 1000);
    } catch (error) {
      console.error("Failed to start recording:", error);
    }
  };

  const stopRecording = () => {
    if (!mediaRecorderRef.current || !isRecording) return;

    mediaRecorderRef.current.stop();
    setIsRecording(false);

    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-zinc-200/80 bg-white/90 p-2 shadow-[0_18px_50px_rgba(15,23,42,0.10)] backdrop-blur-xl dark:border-white/10 dark:bg-white/5">
      {imagePreview && (
        <div className="relative w-fit px-1 pt-1">
          <img
            src={imagePreview}
            alt={labels.newImageAlt}
            className="max-h-32 rounded-xl border border-zinc-200 object-cover dark:border-white/10"
          />
          {imageName && (
            <div className="mt-1 max-w-40 truncate text-xs text-zinc-500">
              {imageName}
            </div>
          )}
          <Button
            type="button"
            variant="destructive"
            size="icon"
            className="absolute -right-2 -top-2 h-6 w-6"
            onClick={removeImage}
            aria-label={labels.removeImage}
            title={labels.removeImage}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex items-end gap-2">
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleImageUpload}
          accept="image/*"
          className="hidden"
        />

        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || isLoading}
          aria-label={labels.imageButton}
          title={labels.imageButton}
          className="h-11 w-11 shrink-0 rounded-xl text-zinc-500 hover:bg-teal-50 hover:text-teal-700 dark:text-zinc-300 dark:hover:bg-teal-400/10 dark:hover:text-teal-200"
        >
          <Image className="h-5 w-5" />
        </Button>

        <div className="relative flex-1">
          <Textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyPress}
            placeholder={
              isRecording
                ? `${labels.recording} ${formatTime(recordingTime)}`
                : labels.placeholder
            }
            className="min-h-11 resize-none rounded-xl border-0 bg-zinc-50/80 py-3 pr-14 shadow-none focus-visible:ring-1 focus-visible:ring-teal-600 focus-visible:ring-offset-0 dark:bg-zinc-950/60 dark:focus-visible:ring-teal-300"
            disabled={disabled || isRecording}
            rows={1}
          />

          <div className="absolute right-2 top-1/2 flex -translate-y-1/2 gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onMouseDown={startRecording}
              onMouseUp={stopRecording}
              onMouseLeave={stopRecording}
              onTouchStart={startRecording}
              onTouchEnd={stopRecording}
              disabled={disabled || isLoading}
              className={`h-8 w-8 rounded-lg ${isRecording ? "animate-pulse text-red-500" : "text-zinc-500 hover:text-teal-700 dark:text-zinc-300 dark:hover:text-teal-200"}`}
              aria-label={labels.voiceButton}
              title={labels.voiceButton}
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Mic className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>

        <Button
          type="submit"
          disabled={
            disabled || (!message.trim() && !imagePreview) || isRecording
          }
          className="h-11 w-11 shrink-0 rounded-xl bg-teal-700 p-0 shadow-sm hover:bg-teal-800 dark:bg-teal-400 dark:text-zinc-950 dark:hover:bg-teal-300"
          aria-label={labels.send}
          title={labels.send}
        >
          <Send className="h-5 w-5" />
        </Button>
      </form>
    </div>
  );
}
