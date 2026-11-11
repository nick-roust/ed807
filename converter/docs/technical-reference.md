# ED807 Technical Reference

This is an original factual guide to the implemented converter, prepared on 2026-11-11. It retains necessary technical identifiers and validation facts; it is not a reproduction of the official descriptive code lists. [ATTRIBUTION.md](../../ATTRIBUTION.md) identifies the authoritative documentation and rights boundaries.

## Supported Profile

The accepted namespace is `urn:cbr-ru:ed:v2.0`, with an ED807 root, `InfoTypeCode=FIRR`, and the supported current header fields. SIRR, multipart and unsupported historical structures are rejected. Optional `InitialED` is supported. A namespace alone does not establish that an older document matches this profile. The pinned XSD validates syntax; it does not establish every conditional business rule, source authenticity or completeness.

## Schema Identity

External package: **UFEBS 2026.09.0**, SHA-256 `3ca5333743462c7ccce34914765c15d45b1f26e3ca227f75f04bce01062e3566`.

The four resources under the archive's `XMLSchemas/ed/` dependency closure are:

| Member basename | SHA-256 |
| --- | --- |
| `cbr_ed807_v2026.09.0.xsd` | `9b898e49185a52b83603af3bff1d92381f7c8b3e91439be1be0ba1e72098ede5` |
| `cbr_ed_objects_v2026.09.0.xsd` | `a764939da35c9a884451c9d70ab60504f49635cd684eb74974a18865a2ceae25` |
| `cbr_ed_leaftypes_v2026.09.0.xsd` | `2a474499dabfa50aece0dbb17747a6258ac3a784462806496f2350a31ff1e6c8` |
| `cbr_ed_basetypes_v2018.3.0.xsd` | `7fc20aa13386459f73d9b96d6d3df43d0d6b22761eea3c1d152aa6ed233c9b0e` |

The loader's exact member paths and hashes are authoritative for implementation. The older base-types filename is intentional: it is the member included in the pinned official package. Obtain the entire archive separately using the [installation guide](../README.md#official-schema); no schema bytes are distributed here.

## Fields, Code Values and Constraints

The [implemented contract](json-contract.md) lists supported XML attributes and ownership. Values remain textual. The converter validates against the official XSD rather than duplicating its restrictions into a replacement schema.

The warning registry uses official code values for `CreationReason`, `InfoTypeCode`, `ChangeType`, `PtType`, `Srvcs`, `XchType`, `RegulationAccountType`, statuses and restrictions. Exact known values appear in `code_diagnostics` in the source. For authoritative meanings, consult UFEBS code entries 65–67 and 72–81 through [the official-source references](../../ATTRIBUTION.md#official-technical-sources). No translated participant/account classification table is included here.

These code sets are description coverage for diagnostics, not extra closed XSD domains. An unknown XSD-valid value remains unchanged and receives `UNKNOWN_CODE_DESCRIPTION`. Do not infer code membership from one dataset, infer account type from an account prefix, or turn a status code into an unqualified active/inactive classification.

## Preservation and Diagnostics

The source hierarchy determines ownership. BIC references do not replace that nesting. Repeated account numbers remain separate occurrences; unresolved references are retained. Duplicate BICs, parent cycles and projection/count mismatches reject the whole candidate. Duplicate UID, unresolved/ambiguous references and unknown described codes warn; absent accounts and repeated account strings produce informational diagnostics.

Source hashes identify bytes, not origin or freshness. No cross-snapshot identity, lifecycle matching, classification normalization or dataset publication is implemented. These engineering choices define the supported converter; official definitions remain in the authoritative specification.
