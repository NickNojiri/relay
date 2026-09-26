//! WebAssembly binding for `flag-core` via wasm-bindgen.
//!
//! Same JSON wire format as the napi and PyO3 bindings: `evaluateJson(ruleJson,
//! unitId) -> decisionJson`. Built with `wasm-pack` (see package.json); intended
//! for edge runtimes and browsers where the native addon can't load.

use wasm_bindgen::prelude::*;

#[wasm_bindgen(js_name = evaluateJson)]
pub fn evaluate_json(rule_json: &str, unit_id: &str) -> Result<String, JsError> {
    flag_core::evaluate_json(rule_json, unit_id).map_err(|e| JsError::new(&e))
}
