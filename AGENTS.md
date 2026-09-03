# AGENTS.md — gstack AI Agent Instructions & Ethos

This project integrates [gstack](https://github.com/garrytan/gstack) (v1.79.0.0) located in `./gstack` and registered in `./.agents/skills/` and `~/.claude/skills/`.

## Ethos

- **Boil the Ocean**: AI makes completeness cheap. Implement complete solutions: comprehensive tests, edge cases, and error paths.
- **Search Before Building**: Know what exists before deciding what to build. Prize first-principles insight and avoid unnecessary dependencies.
- **User Sovereignty**: Models recommend, the user decides. Cross-model agreement is a signal, never permission.
- **Build for Yourself**: Concrete specificity beats abstract generality.

## The Reuse Ladder

Before writing new code, stop at the first rung that holds:
1. A helper, utility, or pattern already in this repository.
2. The standard library.
3. A native platform feature (CSS over JS, database constraints over application code).
4. An already-installed dependency — never add a new one for what a few lines cover.

Bug fixes must target root causes, not symptoms.

## Voice

Direct, concrete, builder-to-builder. Name the file, function, command, and user-visible impact. Short paragraphs; end with what to do. No filler, corporate fluff, or AI boilerplate.

## gstack Skills in this Repository

The full suite of 54 gstack skills is available in `./.agents/skills/` and `./gstack/`:

| Skill | Role & Usage |
|---|---|
| `office-hours` | Product strategy interrogation with 6 forcing questions |
| `plan-ceo-review` | Strategic scope review (4 modes: expand, focus, challenge, cut) |
| `plan-eng-review` | Architecture, data modeling, boundary locking, and guardrails |
| `plan-design-review` | Visual design, micro-animations, typography, and UX review |
| `review` | Automated deep code review, security flags, and regression catch |
| `qa` / `qa-only` | Automated browser QA and iterative bug fixing |
| `cso` | Chief Security Officer audit (OWASP Top 10 + STRIDE threat modeling) |
| `ship` | Safe release workflow, atomic commit, and PR preparation |
| `browse` | Headless Chromium daemon automation via `./gstack/browse/dist/browse.exe` |
| `investigate` | Root-cause analysis and forensic debugging |
| `autoplan` | Automated end-to-end plan generation |
| `retro` | Weekly engineering retrospective and process review |

## Browser Tooling (`browse`)

For browser inspection and web testing, use the local precompiled binary:
- **Executable**: `./gstack/browse/dist/browse.exe`
- **Commands**: `browse goto <url>`, `browse screenshot <path>`, `browse click <sel>`, `browse snapshot`
