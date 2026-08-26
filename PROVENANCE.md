# Provenance audit — 1.27.0

Audit date: 2026-08-24. The supplied 1.22-era ZIP (originally named `ollama-control-redesign-v22.zip`) was compared with:

- `manzolo/ollama-model-train-guide`, commit `d1ba90bc3ee9086829d38e9ff40c15ff444227be` (MIT)
- `ollama-admin/ollama-admin`, commit `9966814c4210b87a79584e6f71541bdc55a08638`

The audit used file hashes, `cmp`, repository-wide searches, and `git diff --no-index --stat`. This is a technical inventory, not legal advice.

## Findings

The supplied 1.22-era archive was not wholly original. It contained byte-identical baseline documentation, example datasets and Modelfiles, GitHub workflows, shell utilities, `.gitignore`, `mkdocs.yml`, and the upstream MIT license. Its top-level directory retained the baseline name. The Flask application was heavily modified; the proxy, host helper, operations UI, telemetry, and many later assets were project-specific additions.

The named `ollama-admin` repository is a materially different Next.js/TypeScript/Prisma application. No byte-identical source files or shared implementation topology were found in the supplied archive. Similar model-management and authentication concepts are functional ideas, not evidence of copied implementation.

## 1.27.0 classification

- **Inherited/legacy:** the MIT license; portions of the large Flask control/converter lineage; limited Compose concepts; historical work predating 1.17. Required upstream notice remains intact.
- **Heavily modified:** `chat/app.py`, WebUI templates/styles/scripts, Docker configuration, hardware detection, preflight, and the host helper.
- **Newly written through 1.27.0:** local multi-user auth/migrations, CSRF/session controls, per-user preferences, user-management UI, Signal Glass, current logo and navigation icon family, launcher, helper identity/status flow, per-message generation metrics, the Aperyn Agent gateway and interface, contained folder picker, encrypted provider store, external Chat adapters, current tests, publishing workflow, and security/release/brand documentation.

## Agent provenance

The 1.24 Agent interface, session-ownership mapping, SQLite schema, authenticated Flask gateway, activity renderer, approval UI, context-meter UI, disclosure-state handling, line-numbered file-change review and non-VCS structured-tool fallback, Compose security boundary, and runtime bootstrap are Aperyn-specific implementations. OpenCode 1.18.17 is used unchanged as a separately built headless runtime under MIT and is credited in `THIRD_PARTY_NOTICES.md`; its WebUI source, DOM, CSS, assets, logo, and layout are not included or reproduced. The context meter and change review consume OpenCode's server-provided token, provider-limit, unified-diff, and structured-tool fields. API field names and arithmetic required for interoperability are not copied UI implementation. The Dashboard deletion workflow and its authenticated internal proxy clear operation are Aperyn-specific code.

The 1.27.0 directory browser, path-containment rules, encrypted connection store, Settings provider cards, and OpenAI/Anthropic/Gemini streaming translators are Aperyn-specific code. Vendor endpoint names and event fields necessarily follow their public API contracts; no vendor UI, branding asset, SDK source, or application layout is copied.

## Removed from the releasable product

Version 1.23.1 removes unused byte-identical baseline guides, example datasets/models, training-guide CLI scripts, workflows, legacy chat template, and build debris. This reduces provenance ambiguity and release surface. It does not erase the origin of remaining substantial code or cancel MIT attribution duties.

A second normalized-text similarity pass caught and replaced a highly similar Dataset Converter template and removed a highly similar obsolete quick-test script. After that rewrite, same-path similarity against the baseline peaked at approximately 30.5% for preflight, 22.3% for Compose, 13.3% for the much larger Flask application, and 11.1% for the new converter template. Against `ollama-admin`, the highest same-path result was approximately 18% for generic Compose structure; its README was under 5%. At that audit stage the retained `LICENSE` was byte-identical to upstream; 1.23.4 later added the repository owner's copyright line without removing or changing the upstream notice or MIT terms.

## Licensing

The baseline is MIT-licensed. `LICENSE` preserves Andrea Manzi's 2026 copyright notice for inherited portions and the repository owner's existing ItzFrexite notice for their contributions, followed by the MIT permission text. No claim is made that the repository owner authored inherited portions. The compared `ollama-admin` checkout exposed no top-level license during this audit, but no implementation reuse was identified; that uncertainty is recorded without asserting a license.

## Similarity caveat

No responsible audit can guarantee that no line resembles any public project. Common Flask, Compose, SQLite, and Ollama API idioms are constrained by interfaces. Version 1.27.0 aims for independently branded, project-specific implementation with transparent attribution—not a false claim that generic programming patterns are unique.

## Final 1.27.0 cross-file rescan

Both comparison repositories were checked again on 2026-08-24. Their heads were unchanged at the commits listed above. The rescan compared hashes and normalized source lines across every compatible file pair, not only matching paths, so renamed or moved source was included. It initially detected long retained runs in the legacy dataset-conversion and basic model-management endpoints; 1.24 rewrote those blocks into path-confined, timeout-aware Aperyn implementations before the final scan.

- Against `ollama-model-train-guide`, no current file is byte-identical. `LICENSE` differs only by the added repository-owner copyright line; Andrea Manzi's upstream notice and the MIT terms remain intact.
- No current source file has a shared run of five normalized source lines with the baseline. The highest reported whole-file similarity was 24.0% between deployment documentation and a baseline example README; this is short conventional installation language, not shared application implementation.
- Against `ollama-admin`, there are no byte-identical files and no shared five-line source runs. The highest whole-file line similarity is 15.4% for conventional Compose structure.
- The Python/Flask application, proxy, helper, JavaScript, templates, styles, tests, Nym signal-moth mark, and navigation icon sprite produced no substantial cross-file match in this scan.

## Product ownership conclusion

The current codebase is technically suitable to publish and operate as the independently branded Aperyn product, provided the retained MIT notice and this provenance record remain with distributions. MIT permits use, modification, publication, sublicensing, and sale. It does not transfer Andrea Manzi's copyright in inherited portions, so Aperyn should not be described as entirely authored from scratch or as exclusively owning every historical line. The project owner can claim the Aperyn name, mark, current product direction, and newly written portions, subject to a separate trademark/name-availability check. This is a technical and licensing assessment, not legal advice.
