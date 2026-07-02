//! Node.js binding for `flag-core` via napi-rs.
//!
//! Exposes `evaluateJson(ruleJson, unitId) -> decisionJson` — the same JSON wire
//! format as the TS SDK, so `@relay/flag-sdk` can route `evaluate()` through the
//! native engine and keep the pure-TS path as a fallback.

use napi_derive::napi;

#[napi]
pub fn evaluate_json(rule_json: String, unit_id: String) -> napi::Result<String> {
    flag_core::evaluate_json(&rule_json, &unit_id).map_err(napi::Error::from_reason)
}
