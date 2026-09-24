-- Demo data so /playground, /flags and /telemetry work on first load.
-- provider/model are left NULL so the gateway labels telemetry with the provider it
-- actually runs (DEMO_PROVIDER), rather than a name it isn't using.
INSERT INTO prompts (id, key, name) VALUES
  ('00000000-0000-0000-0000-000000000001', 'prompt.support-bot', 'Support bot');

INSERT INTO prompt_versions (id, prompt_id, version, body) VALUES
  ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-000000000001', 1,
   'You are a terse support agent. Answer in one sentence.'),
  ('00000000-0000-0000-0000-00000000000b', '00000000-0000-0000-0000-000000000001', 2,
   'You are a warm, empathetic support agent. Acknowledge the customer''s frustration before helping.');

INSERT INTO flags (key, enabled, rollout_bps, variants) VALUES
  ('prompt.support-bot', true, 10000, '[
    {"key": "A", "weightBps": 5000, "promptVersionId": "00000000-0000-0000-0000-00000000000a"},
    {"key": "B", "weightBps": 5000, "promptVersionId": "00000000-0000-0000-0000-00000000000b"}
  ]');
