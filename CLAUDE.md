# CLAUDE.md — gstack Guidelines

This project uses [gstack](https://github.com/garrytan/gstack) for AI-assisted engineering workflows.

## gstack Repository & Skills

- **Local Repository**: `./gstack`
- **Global Skills**: `~/.claude/skills/gstack`
- **Agent Skills**: `./.agents/skills/`
- **Headless Browser CLI**: `./gstack/browse/dist/browse.exe`

### Available Skills
- `/office-hours`: Product strategy and forcing questions
- `/plan-ceo-review`: Vision and product challenge
- `/plan-eng-review`: Architecture and guardrails
- `/plan-design-review`: UX and aesthetics inspection
- `/review`: Deep code review
- `/qa` & `/qa-only`: Automated browser testing & bug fixing
- `/cso`: Security audit (OWASP & STRIDE)
- `/ship`: Release preparation and git sanity checks
- `/browse`: Headless browser interactions (never use plain unstructured browser tools when `/browse` is available)
- `/investigate`: Root cause analysis
- `/autoplan`: Automated full-feature planning
- `/retro`: Engineering retrospective

## Engineering Standards
- **Ethos**: Boil the ocean (write complete tests and error handling), search before building, honor user sovereignty.
- **The Reuse Ladder**: (1) Repo helpers -> (2) Standard library -> (3) Native platform features -> (4) Existing dependencies.
- **Tone**: Direct, concise, technical, no corporate fluff.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
