# Aperyn 1.27.2

This supersedes 1.27.1 before live deployment, so this is the complete first
server-only release from the new repository.

- The Agent can invoke an explicit non-root host SDK allow-list: .NET,
  Python/pip, Node/npm/npx, Rust/Cargo, Java, GCC/G++, CMake, Make, Go,
  Ruby/bundle and PHP/composer.
- The Agent may use OpenCode web search. Web fetches continue to ask for
  approval.
- Chat and Agent sessions receive a first-prompt title automatically; click a
  session title to rename it.
- Keeps first Dashboard cards clear of the floating desktop top bar.
- Keeps the experimental desktop client completely absent from the source,
  images, workflow and release assets.
