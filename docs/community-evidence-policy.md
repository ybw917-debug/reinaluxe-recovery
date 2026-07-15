# Community Evidence and Retention Policy

## Evidence ladder

Highest to lowest support is:

1. official primary source;
2. first-party specimen inspection, measurement, or long-term use;
3. scoped supplier confirmation;
4. independent corroboration from multiple sources;
5. a single community report;
6. editorial inference;
7. unknown or unsupported material.

The ladder describes support, not automatic truth. Source independence is
counted from distinct source record IDs. Repetition inside one thread or from a
copied post does not establish independent corroboration. AI-assisted
extraction always reports `unsupported` until a human reviews the claim and
evidence.

## Atomicity, conflicts, and time

One candidate record contains one proposition. Split statements that combine a
material, factory, durability, and pricing assertion. Record qualifiers in the
claim scope rather than broadening wording. Conflicting claims stay separate,
link to each other in the decision, and cannot be silently resolved by source
count. A `contradicted`, `stale`, `rejected`, `duplicate`, `out_of_scope`, or
`needs_more_evidence` decision cannot create approved knowledge.

## Privacy and copyright minimization

- Author aliases are optional. Do not encourage or require real names.
- Hash a source identifier only when needed for deduplication.
- Do not retain contact details, addresses, payment or transaction details,
  private messages, or other unnecessary personal data without a separately
  approved justification.
- Keep only the excerpt necessary to support a claim. Do not store or republish
  a full community post merely because it was supplied.
- Preserve a public source URL and timestamp for audit when available; offline
  or private evidence may omit a URL.
- Select a copyright retention mode explicitly for every source.

## Supplier confidentiality and publication

Supplier statements default to `restricted_supplier_evidence`; supplier
confirmations default to the matching restricted confidentiality. Raw supplier
identity and confidential provenance never enter knowledge CSV output.
Supplier-backed knowledge defaults to `internal_only` unless the owner makes an
explicit publishable or publishable-with-attribution decision for a summary.
That decision does not authorize publication or disclosure of the underlying
supplier record.

No workflow command publishes automatically. `publishable` is a reviewed
classification for a later, separately approved editorial action.
