//! Relay flag-eval core.
//!
//! Byte-for-byte parity with `@relay/flag-sdk` (TypeScript) and the `prompt-ops`
//! Python port: the same FNV-1a hash over UTF-8 bytes, the same `flag:salt:unit`
//! bucket keys, and the same basis-point logic. This is the one verified engine
//! that the napi-rs / wasm-bindgen / PyO3 bindings (Phase 4b) all wrap, so a flag
//! decision is identical in Node, the browser/edge, and Python.

const FNV_OFFSET: u32 = 0x811c_9dc5;
const FNV_PRIME: u32 = 0x0100_0193;

/// FNV-1a, 32-bit, over UTF-8 bytes.
pub fn fnv1a(value: &str) -> u32 {
    let mut hash = FNV_OFFSET;
    for byte in value.as_bytes() {
        hash ^= u32::from(*byte);
        hash = hash.wrapping_mul(FNV_PRIME);
    }
    hash
}

/// Deterministic 0..9999 bucket for (flag, unit) under a salt namespace.
fn bucket(flag_key: &str, unit_id: &str, salt: &str) -> u32 {
    fnv1a(&format!("{flag_key}:{salt}:{unit_id}")) % 10000
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FlagVariant {
    pub key: String,
    pub weight_bps: u32,
    pub prompt_version_id: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FlagRule {
    pub key: String,
    pub enabled: bool,
    pub rollout_bps: u32,
    pub variants: Vec<FlagVariant>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Decision {
    pub enabled: bool,
    pub variant: Option<String>,
    pub reason: &'static str,
}

/// Evaluate a flag for a stable `unit_id`. Deterministic and side-effect free.
pub fn evaluate(rule: &FlagRule, unit_id: &str) -> Decision {
    if !rule.enabled {
        return Decision { enabled: false, variant: None, reason: "flag_disabled" };
    }
    if bucket(&rule.key, unit_id, "gate") >= rule.rollout_bps {
        return Decision { enabled: false, variant: None, reason: "out_of_rollout" };
    }
    if rule.variants.is_empty() {
        return Decision { enabled: true, variant: None, reason: "no_variants" };
    }

    let vb = bucket(&rule.key, unit_id, "variant");
    let mut cumulative = 0u32;
    for v in &rule.variants {
        cumulative += v.weight_bps;
        if vb < cumulative {
            return Decision { enabled: true, variant: Some(v.key.clone()), reason: "rollout" };
        }
    }
    // Weights summed to < 10000: assign the last variant.
    let last = rule.variants.last().expect("variants is non-empty");
    Decision { enabled: true, variant: Some(last.key.clone()), reason: "rollout" }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rule() -> FlagRule {
        FlagRule {
            key: "prompt.support-bot".into(),
            enabled: true,
            rollout_bps: 10000,
            variants: vec![
                FlagVariant { key: "A".into(), weight_bps: 5000, prompt_version_id: None },
                FlagVariant { key: "B".into(), weight_bps: 5000, prompt_version_id: None },
            ],
        }
    }

    #[test]
    fn fnv1a_canonical_vectors() {
        // Identical numbers to @relay/flag-sdk (TS) and prompt-ops (Python).
        assert_eq!(fnv1a(""), 2_166_136_261);
        assert_eq!(fnv1a("a"), 3_826_002_220);
    }

    #[test]
    fn disabled_flag() {
        let mut r = rule();
        r.enabled = false;
        let d = evaluate(&r, "u1");
        assert!(!d.enabled);
        assert_eq!(d.reason, "flag_disabled");
    }

    #[test]
    fn zero_rollout() {
        let mut r = rule();
        r.rollout_bps = 0;
        assert_eq!(evaluate(&r, "user-42").reason, "out_of_rollout");
    }

    #[test]
    fn stable_for_unit() {
        assert_eq!(evaluate(&rule(), "user-42"), evaluate(&rule(), "user-42"));
    }

    #[test]
    fn split_roughly_even() {
        let n = 10_000;
        let a = (0..n)
            .filter(|i| evaluate(&rule(), &format!("user-{i}")).variant.as_deref() == Some("A"))
            .count();
        let ratio = a as f64 / n as f64;
        assert!(ratio > 0.45 && ratio < 0.55, "ratio={ratio}");
    }
}
