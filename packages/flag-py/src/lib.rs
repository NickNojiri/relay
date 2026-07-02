//! Python binding for `flag-core` via PyO3.
//!
//! Same JSON wire format as the napi and wasm bindings: `evaluate_json(rule_json,
//! unit_id) -> decision_json`. Built as the `relay-flag-py` wheel with maturin;
//! `services/prompt-ops` uses it when importable and falls back to its Python port.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyfunction]
fn evaluate_json(rule_json: &str, unit_id: &str) -> PyResult<String> {
    flag_core::evaluate_json(rule_json, unit_id).map_err(PyValueError::new_err)
}

#[pymodule]
fn relay_flag_py(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(evaluate_json, m)?)?;
    Ok(())
}
