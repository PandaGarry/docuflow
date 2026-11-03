# Working agreement

- Publish progress frequently: commit and push small, reviewable milestones to the
  environment-assigned working branch. Do not accumulate multiple iterations
  only in the sandbox. Never force-push over remote work; reconcile it first.
- Include durable review images in `studio/reviews/` and link the current report.
  `.cache/` and `studio/out/` contain disposable/generated runtime artifacts;
  they are not the only location for a requested visual deliverable.
- Keep technical tests separate from visual, anatomical and user approval.
  Passing schemas/strain tests is not evidence of cinema-industry quality.
  Label failed experiments and incomplete assets honestly; preserve their evidence.
- Preserve historical recipes, canonical reference art and receipts. New revisions
  need their own package/provenance, native measurements and actual render frames.
- The renderer/native tools verify real generated binaries. Pure contract tests
  must work on clean checkouts without these binaries; test source provenance
  separately rather than turning off runtime integrity checks.
- Run the pipeline suites and planning checks before publishing. Native checks
  are separate from lightweight GitHub Actions; report which actually ran.
- Do not merge/close the PR or claim production/artistic acceptance merely because
  work has been pushed or CI is green.
