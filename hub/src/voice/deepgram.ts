/** Deepgram speech-to-text hooks */

export interface SttResult {
  transcript: string;
  confidence?: number;
  mock: boolean;
}

/**
 * Transcribe audio bytes via Deepgram REST.
 * When DEEPGRAM_API_KEY is missing, returns empty mock (UI should use Web Speech fallback).
 */
export async function transcribeDeepgram(
  audio: Buffer,
  mime = "audio/wav"
): Promise<SttResult> {
  const key = process.env.DEEPGRAM_API_KEY;
  if (!key) {
    return { transcript: "", mock: true, confidence: 0 };
  }

  const url =
    "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&punctuate=true";
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Token ${key}`,
      "Content-Type": mime,
    },
    // Node 22 fetch typings reject Buffer — Uint8Array is accepted BodyInit
    body: new Uint8Array(audio),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Deepgram ${res.status}: ${err}`);
  }
  const data = (await res.json()) as {
    results?: {
      channels?: { alternatives?: { transcript?: string; confidence?: number }[] }[];
    };
  };
  const alt = data.results?.channels?.[0]?.alternatives?.[0];
  return {
    transcript: alt?.transcript || "",
    confidence: alt?.confidence,
    mock: false,
  };
}

/** Browser-side note: prefer Deepgram JS SDK streaming; this endpoint is for uploads. */
export const deepgramBrowserHint = {
  streaming: "wss://api.deepgram.com/v1/listen",
  model: "nova-2",
};
