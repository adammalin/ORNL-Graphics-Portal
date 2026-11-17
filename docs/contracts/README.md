# Proposed AI contract artifacts

These files define the implementation target described in [the specification](../ai-agent-implementation-spec.md). They do not add a running endpoint, model connection or Smartsheet field.

- [intake-analysis.schema.json](intake-analysis.schema.json): Draft 2020-12 JSON Schema for untrusted external-agent output.
- [examples/intake-context.synthetic.json](examples/intake-context.synthetic.json): a fictional complete request with its date supplied in notes instead of the structured field.
- [examples/intake-analysis.synthetic.json](examples/intake-analysis.synthetic.json): the matching proposed brief, sourced date extraction and zero follow-up questions.
- [Shared analysis instructions](../prompts/intake-analysis-v1.md): client/model-neutral prompt.

The example job, context IDs and repeated-character hashes are placeholders for contract testing, not live identifiers or computed production fingerprints. The fixture cannot be imported into the real service: only a server-created, authorized, fresh context may accept output.

Validate the schema itself and enable date-format validation when validating examples. Structural validation is only the first step. The server must also enforce the specification's semantic rules: context/job binding, authorization, freshness, supported/native field values, blank targets, exact evidence membership, unique IDs/proposals, legitimate issue/question links and honest source coverage.

The full schema is the backend acceptance contract. A future model provider may need a restricted generation schema; such an adapter must not remove backend validation.

Do not put real job exports, attachments, employee addresses, tokens or customer text in this directory.
