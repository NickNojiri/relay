/** App-domain types shared across studio, prompt-ops, and sync-server.
 *  (Feature-flag evaluation types live in @relay/flag-sdk, which is standalone.) */

export interface Prompt {
  id: string;
  key: string;
  name: string;
  createdAt: Date;
}

export interface PromptVersion {
  id: string;
  promptId: string;
  version: number;
  body: string;
  /** Optional pinned provider/model; falls back to RELAY_DEFAULT_* when null. */
  provider: string | null;
  model: string | null;
  createdAt: Date;
}

export interface TelemetryEvent {
  id: string;
  promptVersionId: string | null;
  flagKey: string | null;
  variant: string | null;
  provider: string;
  model: string;
  promptTokens: number;
  completionTokens: number;
  latencyMs: number;
  createdAt: Date;
}
