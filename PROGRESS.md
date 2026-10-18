# PROGRESS — finish M0 (scenario builder, agents, play CLI, fuzz harness)

**Task** (user prompt, this session): finish M0: `tests/scenario.py`, the random and scripted
agents, `tools/play_cli.py` and the fuzz harness (docs/roadmap.md M0, design.md §3, §12, §14).
Follow CLAUDE.md fully; run the test-reviewer before the PR. Branch:
`claude/m0-scenario-builder-agents-9g8dfn` (from main; the engine-core PR #9 is merged).

## Plan

1. `resolve.agents`: `Agent` protocol, `play` driver (`resolve.agents.driver`), `RandomAgent`
   (`random_agent.py`, own `Rng`), `ScriptedAgent` + `Step`/`Choose` (`scripted.py`, also
   `ScriptedAgent.from_log` for replays). Tests in `tests/agents/`.
2. `tests/scenario.py`: `Scenario` builder (players, config, seed, life, cards in any zone,
   library top-first, commanders, known_to, starting player; `build(*tasks)`), plus
   `run_script`. Tests in `tests/scenario_tests/`? -> `tests/engine/test_scenario_builder.py`.
3. `resolve.agents.text`: renderer (`render_view`, `render_request`) and `TextAgent` (CLI agent
   with injectable streams). `tools/play_cli.py`. Tests in `tests/tooling/`.
4. `tools/fuzz.py`: harness (`fuzz_game`), CLI with games/second. `tests/fuzz/test_fuzz.py`.
5. Docs: decisions.md, howto.md (scenario test, fuzz, play CLI), CLAUDE.md status, roadmap ticks,
   design.md untouched unless needed. Determinism lint scans `agents` too.
6. test-reviewer, address findings, delete PROGRESS.md, open PR.

## Done

- Step 1: agents (`src/resolve/agents/{base,driver,random_agent,scripted}.py`), tests in
  `tests/agents/`.
- Step 2: `tests/scenario.py` (`Scenario`, `names`, `run_script`), tests in
  `tests/engine/test_scenario_builder.py`.

## In progress

- Step 3: text renderer + TextAgent + tools/play_cli.py.

## Decisions not yet in the docs

- Harness lives in `tools/fuzz.py` (tests import it as `tools.fuzz`, like `tools.coverage`).
- Renderer and CLI agent live in `resolve.agents.text`; `tools/play_cli.py` is a thin main.
- Replays are a `ScriptedAgent` built from the log's `AnswerRecord`s.
- CLI and fuzz tool default to empty decks, since no card is implemented (no fake cards in tools).

## Open questions for the user

- (none yet)
