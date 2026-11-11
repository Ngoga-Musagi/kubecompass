---
name: voice-interaction
description: Use when changing speech input/output, the agent microphone UI, spoken replies or adding a server speech provider. Keeps voice user-controlled, robust in noisy venues and swappable.
---

# Voice interaction

## When to use
Changes to `frontend/lib/voice.ts`, the mic/listen controls in `frontend/app/agent/page.tsx`, how
replies are phrased for speech, or adding a speech-to-text / text-to-speech provider.

## Rules
1. **Push-to-talk only.** Listening starts on a tap and ends after one utterance or a second tap.
   Never listen in the background, never call `start()` without a user gesture, and never assume
   microphone permission.
2. **Providers stay behind `SpeechInput` / `SpeechOutput`.** STT and TTS are swappable
   independently; UI code must not touch `webkitSpeechRecognition` or `speechSynthesis` directly.
3. **Noisy rooms:** low-confidence transcripts (`LOW_CONFIDENCE`) go into the text box for review;
   recognition errors map to plain-language messages (`ERRORS`). Text input must always work.
4. **Voice in, voice out:** speak replies to spoken questions; offer **Listen** on every reply;
   stop speaking when the mic starts. Speak `speakable(reply)`: no citation markers, URLs or
   markdown.
5. **Context is shared:** voice and text turns go into the same conversation history.
6. **Mobile first:** controls are at least 44×44 px and sit in the sticky composer.

## Test
- `frontend/tests/unit/agent.test.tsx` covers `speakable`. Browser speech APIs can't run headless,
  so test new providers through the interfaces (inject a fake `SpeechInput`).
- Manually check on a phone (Chrome Android, Safari iOS) before claiming a voice change works.
