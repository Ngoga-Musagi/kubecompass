// Voice for the event agent, behind two small interfaces so either side can be swapped
// independently (e.g. a server speech-to-text for noisy venues) without touching the UI.
//
// Push-to-talk only: listening starts when the attendee taps the mic and stops after one
// utterance or a second tap. There is no background listening, and microphone permission is
// requested by the browser only when the attendee first taps the mic.

export interface ListenHandlers {
  onPartial: (text: string) => void;
  /** confidence is 0..1, or null when the engine doesn't report it */
  onFinal: (text: string, confidence: number | null) => void;
  onError: (message: string) => void;
  onEnd: () => void;
}

export interface SpeechInput {
  readonly supported: boolean;
  start(handlers: ListenHandlers): void;
  stop(): void;
}

export interface SpeechOutput {
  readonly supported: boolean;
  speak(text: string, onEnd?: () => void): void;
  cancel(): void;
}

/** Below this, a transcript is put in the text box for review instead of being sent. */
export const LOW_CONFIDENCE = 0.55;

const ERRORS: Record<string, string> = {
  "not-allowed": "Microphone access was blocked. Allow it in your browser, or type instead.",
  "service-not-allowed": "Voice input isn't allowed here. You can type instead.",
  "no-speech": "I didn't catch that. Tap the mic and try again, closer to the phone if it's noisy.",
  "audio-capture": "No microphone was found. You can type instead.",
  network: "Voice input needs a network connection. You can type instead.",
  aborted: "",
};

// Minimal typing for the Web Speech API (not in TypeScript's DOM lib everywhere).
interface RecognitionResult {
  isFinal: boolean;
  0: { transcript: string; confidence: number };
}
interface RecognitionEvent {
  resultIndex: number;
  results: ArrayLike<RecognitionResult>;
}
interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  onresult: ((e: RecognitionEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export class BrowserSpeechInput implements SpeechInput {
  private rec: Recognition | null = null;

  get supported(): boolean {
    return recognitionCtor() !== null;
  }

  start(h: ListenHandlers): void {
    const Ctor = recognitionCtor();
    if (!Ctor) {
      h.onError("Voice input isn't supported in this browser. Try Chrome, Edge or Safari, or type instead.");
      h.onEnd();
      return;
    }
    this.stop();
    const rec = new Ctor();
    rec.lang = typeof navigator !== "undefined" ? navigator.language || "en-US" : "en-US";
    rec.interimResults = true;
    rec.continuous = false; // one utterance per tap
    rec.maxAlternatives = 1;
    let delivered = false;
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (!r) continue;
        if (r.isFinal) {
          delivered = true;
          const c = r[0].confidence;
          h.onFinal(r[0].transcript.trim(), c > 0 ? c : null);
        } else {
          interim += r[0].transcript;
        }
      }
      if (interim) h.onPartial(interim.trim());
    };
    rec.onerror = (e) => {
      const msg = ERRORS[e.error] ?? "Voice input stopped unexpectedly. You can try again or type.";
      if (msg) h.onError(msg);
    };
    rec.onend = () => {
      this.rec = null;
      if (!delivered) h.onPartial("");
      h.onEnd();
    };
    this.rec = rec;
    try {
      rec.start();
    } catch {
      h.onError("Couldn't start the microphone. Try again.");
      h.onEnd();
    }
  }

  stop(): void {
    this.rec?.stop();
  }
}

/** Plain text for speech: no citation markers, markdown or URLs. */
export function speakable(text: string): string {
  return text
    .replace(/\[(S|P)\d+\]/g, "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/[*_#`>]/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

export class BrowserSpeechOutput implements SpeechOutput {
  get supported(): boolean {
    return typeof window !== "undefined" && "speechSynthesis" in window;
  }

  speak(text: string, onEnd?: () => void): void {
    if (!this.supported) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(speakable(text));
    u.lang = navigator.language || "en-US";
    u.rate = 1.03;
    if (onEnd) {
      u.onend = onEnd;
      u.onerror = onEnd;
    }
    window.speechSynthesis.speak(u);
  }

  cancel(): void {
    if (this.supported) window.speechSynthesis.cancel();
  }
}

export const speechInput: SpeechInput = new BrowserSpeechInput();
export const speechOutput: SpeechOutput = new BrowserSpeechOutput();
