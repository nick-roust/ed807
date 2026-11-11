# Implemented ED807 JSON Contract

Contract: **`roust.bic.ed807` / `1.0.0`**. This public reference describes the existing offline implementation. It does not introduce a new contract or JSON Schema. It uses original factual wording and necessary source identifiers; [official-source attribution](../../ATTRIBUTION.md) supplies the specification references.

## Envelope

The top-level object has `format`, `metadata` and `participants`.

| Path | Implemented value / rule |
| --- | --- |
| `format` | `roust.bic.ed807` |
| `metadata.publicSchemaVersion` | `1.0.0` |
| `metadata.source.organization` | `Bank of Russia`; identifies the intended source organization, not a cryptographic authenticity assertion |
| `metadata.source.acquisition` | `mode=manual-import`; `requestedUrl`, `resolvedUrl`, `downloadedAt` are null |
| `metadata.source.artifact` | Original XML SHA-256 and parsed encoding; ZIP input additionally records archive SHA-256/member name |
| `metadata.source.document` | `rootElement`, `namespace`, `xmlVersion`, original root `attributes`, optional `InitialED` attributes |
| `metadata.processing` | `converterVersion`, supplied `convertedAt`, `xsdVersion`, `xsdPackageSha256` |
| `metadata.publication.publishedAt` | null; this converter does not publish |
| `metadata.counts` | Integer `participantCount` and `accountCount`, counting occurrences |
| `participants` | One entry per source `BICDirectoryEntry`, in source order |

Archive metadata makes XML and ZIP import envelopes differ even when the embedded XML is identical. The converter does not infer acquisition URLs/times, local absolute input paths or publication events. The unchanged format identifier is an internal contract name, not a runtime dependency.

## Mapping

XML attributes map to same-named JSON properties, preserving case and strings. Root attributes map to `metadata.source.document.attributes`; optional `InitialED` maps to the same-named object. Entry attributes map directly to each participant. `ParticipantInfo` is an object. `SWBICS` and `Accounts` are arrays. `RstrList` belongs inside `ParticipantInfo`; `AccRstrList` belongs inside its account. Each repeated child retains its own attributes and source order.

Supported attribute vocabulary:

| XML element | Attributes |
| --- | --- |
| `ED807` | `EDNo`, `EDDate`, `EDAuthor`, `EDReceiver`, `CreationReason`, `CreationDateTime`, `InfoTypeCode`, `BusinessDay`, `DirectoryVersion` |
| `InitialED` | `EDNo`, `EDDate`, `EDAuthor` |
| `BICDirectoryEntry` | `BIC`, `ChangeType` |
| `ParticipantInfo` | `NameP`, `EnglName`, `RegN`, `CntrCd`, `Rgn`, `Ind`, `Tnp`, `Nnp`, `Adr`, `PrntBIC`, `DateIn`, `DateOut`, `PtType`, `Srvcs`, `XchType`, `UID`, `ParticipantStatus` |
| `SWBICS` | `SWBIC`, `DefaultSWBIC` |
| `Accounts` | `Account`, `RegulationAccountType`, `CK`, `AccountCBRBIC`, `DateIn`, `DateOut`, `AccountStatus` |
| `RstrList` | `Rstr`, `RstrDate` |
| `AccRstrList` | `AccRstr`, `AccRstrDate`, `SuccessorBIC` |

This is a preservation vocabulary, not a statement that every listed attribute is required. Requiredness, lexical constraints and cardinalities are validated using the pinned official schema. Unknown structural fields/namespaces or unsupported content cause rejection rather than silent data loss. `PartInfo` is not part of the implemented accepted profile.

## Strings and Repeated Records

- All XML attributes remain strings, including dates, identifiers, numeric-looking codes and lexical booleans. No trimming, numeric coercion, case folding or Unicode normalization is applied.
- Missing attributes are omitted. Valid present empty strings remain present; schema-invalid empty attributes fail validation. Mapped XML attributes are not replaced by null or defaults.
- Repeated collections are arrays, including empty arrays. Duplicate account occurrences remain separate. There is no filtering by code, account presence or resolved reference.
- `PrntBIC`, `AccountCBRBIC` and restriction-scoped `SuccessorBIC` remain unchanged. Reference diagnostics do not fabricate targets or alter ownership.
- Original-byte hashing preserves provenance identity; comments, processing instructions and prefix spellings are not projected as JSON fields. Semantic attribute preservation does not mean byte-for-byte XML reconstruction.

## Ordering and Serialization

Participant, account, SWIFT and restriction arrays retain source order. Object keys sort lexicographically; compact JSON uses UTF-8, no BOM, no unnecessary ASCII escaping and exactly one trailing LF. NaN and infinity are forbidden.

Identical source bytes, input mode, schema, converter version and supplied event metadata yield identical bytes. Changing the timestamp or archive provenance changes the output. No cross-snapshot canonicalization, deduplication or self-referential JSON checksum is specified.

## Diagnostics and Validity

Diagnostics are a separate sidecar, not part of the core payload. Its `counts` additionally describe participants without accounts, SWIFT records and restriction occurrences; these are observed counts, not schema constraints. Error conditions reject the whole candidate; warnings retain the source values. Read [CLI exit codes](../README.md#exit-codes) and [technical reference](technical-reference.md#preservation-and-diagnostics).

A passed schema check does not prove all business rules, official origin, completeness or current validity. The project's MIT License does not grant rights to publish the source-derived banking content.
