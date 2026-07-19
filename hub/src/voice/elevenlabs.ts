/** ElevenLabs TTS + conversational widget hooks */

export interface TtsResult {
  audioBase64?: string;
  mime: string;
  mock: boolean;
  widget?: Record<string, string>;
}

export function elevenLabsWidgetConfig() {
  return {
    agentId: process.env.ELEVENLABS_AGENT_ID || "",
    voiceId: process.env.ELEVENLABS_VOICE_ID || "",
    // Embed snippet for dashboard:
    // <elevenlabs-convai agent-id="..."></elevenlabs-convai>
    scriptSrc: "https://elevenlabs.io/convai-widget/index.js",
    persona:
      process.env.JARVIS_VOICE_PERSONA ||
      "British butler, precise, faintly sarcastic, loyal",
  };
}

export async function synthesizeElevenLabs(text: string): Promise<TtsResult> {
  const key = process.env.ELEVENLABS_API_KEY;
  const voice = process.env.ELEVENLABS_VOICE_ID;
  const model = process.env.ELEVENLABS_MODEL_ID || "eleven_turbo_v2_5";

  if (!key || !voice) {
    return {
      mock: true,
      mime: "audio/mpeg",
      widget: elevenLabsWidgetConfig() as unknown as Record<string, string>,
    };
  }

  const url = `https://api.elevenlabs.io/v1/text-to-speech/${voice}`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "xi-api-key": key,
      "Content-Type": "application/json",
      Accept: "audio/mpeg",
    },
    body: JSON.stringify({
      text,
      model_id: model,
      voice_settings: {
        stability: 0.4,
        similarity_boost: 0.75,
        style: 0.35,
        use_speaker_boost: true,
      },
    }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`ElevenLabs ${res.status}: ${err}`);
  }
  const buf = Buffer.from(await res.arrayBuffer());
  return {
    audioBase64: buf.toString("base64"),
    mime: "audio/mpeg",
    mock: false,
  };
}
