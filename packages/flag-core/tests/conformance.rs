//! Shared conformance suite: the same `conformance/cases.json` fixture that pins
//! the TypeScript (`@relay/flag-sdk`) and Python (`prompt-ops`) ports is asserted
//! here against the Rust core, so all engines stay decision-identical.

use flag_core::{evaluate, FlagRule, FlagVariant};
use serde::Deserialize;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct CaseVariant {
    key: String,
    weight_bps: u32,
    prompt_version_id: Option<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct CaseFlag {
    key: String,
    enabled: bool,
    rollout_bps: u32,
    variants: Vec<CaseVariant>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Expected {
    enabled: bool,
    variant: Option<String>,
    reason: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Case {
    flag: CaseFlag,
    unit_id: String,
    expected: Expected,
}

/// The same cases through the JSON boundary the bindings use (`evaluate_json`).
#[cfg(feature = "serde")]
#[test]
fn conformance_cases_json_boundary() {
    #[derive(Deserialize)]
    struct RawCase {
        flag: serde_json::Value,
        #[serde(rename = "unitId")]
        unit_id: String,
        expected: Expected,
    }

    let raw = include_str!("../conformance/cases.json");
    let cases: Vec<RawCase> = serde_json::from_str(raw).expect("cases.json parses");

    for (i, case) in cases.iter().enumerate() {
        let decision = flag_core::evaluate_json(&case.flag.to_string(), &case.unit_id)
            .expect("evaluate_json succeeds");
        let got: Expected = serde_json::from_str(&decision).expect("decision parses");
        assert_eq!(
            (got.enabled, got.variant.as_deref(), got.reason.as_str()),
            (
                case.expected.enabled,
                case.expected.variant.as_deref(),
                case.expected.reason.as_str()
            ),
            "case #{i} (json boundary): unit={}",
            case.unit_id,
        );
    }
}

#[test]
fn conformance_cases() {
    let raw = include_str!("../conformance/cases.json");
    let cases: Vec<Case> = serde_json::from_str(raw).expect("cases.json parses");
    assert!(!cases.is_empty());

    for (i, case) in cases.iter().enumerate() {
        let rule = FlagRule {
            key: case.flag.key.clone(),
            enabled: case.flag.enabled,
            rollout_bps: case.flag.rollout_bps,
            variants: case
                .flag
                .variants
                .iter()
                .map(|v| FlagVariant {
                    key: v.key.clone(),
                    weight_bps: v.weight_bps,
                    prompt_version_id: v.prompt_version_id.clone(),
                })
                .collect(),
        };
        let d = evaluate(&rule, &case.unit_id);
        assert_eq!(
            (d.enabled, d.variant.as_deref(), d.reason),
            (
                case.expected.enabled,
                case.expected.variant.as_deref(),
                case.expected.reason.as_str()
            ),
            "case #{i}: flag={} unit={}",
            case.flag.key,
            case.unit_id,
        );
    }
}
