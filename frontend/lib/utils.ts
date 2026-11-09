import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const ENTITY_LABEL: Record<string, string> = {
  topic: "Topic",
  technology: "Technology",
  project: "Project",
  speaker: "Speaker",
  organization: "Organization",
  session: "Session",
  track: "Track",
};

/** CSS variable for an entity type's semantic colour. */
export const entityColor = (type: string) => `var(--ent-${type in ENTITY_LABEL ? type : "session"})`;

export const ORIGIN_COPY: Record<string, { label: string; hint: string }> = {
  explicit: { label: "Official", hint: "Supplied directly by the official Sessionize schedule." },
  extracted: { label: "From text", hint: "Matched in the session or speaker text; the quoted sentence is the evidence." },
  curated: { label: "Curated", hint: "From KubeCompass's maintained cloud-native vocabulary." },
  inferred: { label: "Inferred", hint: "Computed by KubeCompass (similarity or co-occurrence). A likely connection, not a confirmed fact." },
  ai_extracted: { label: "AI-extracted", hint: "Produced by an AI model; not confirmed." },
  verified: { label: "Verified", hint: "Confirmed against an external source." },
};
