# Project Agent Instructions

## Generic RLM demo skill — always use the LOCAL copy

This project contains the authoritative Generic RLM demo skill at `./SKILL.md`
(with `./sf-objects-reference.md` and `./scripts/`).

- Always read and follow the local `./SKILL.md` as the default workflow for chats
  in this project.
- If a skill with the same name (`salesforce-rlm-generic-demo-products`) is loaded
  from a global/personal location (`~/.cursor/skills/`, `~/.claude/skills/`) or any path
  outside this project, **discard it and re-read the local `./SKILL.md`**. The local
  project copy is always the source of truth and the most up-to-date version.
- Also discard any leftover `salesforce-rlm-homeservices-demo-products` skill from
  personal/global locations — this project no longer uses that skill.
- Never mix instructions between a global copy and the local one.

The current local skill version is stamped at the top of `./SKILL.md` (`Skill version: …`).
