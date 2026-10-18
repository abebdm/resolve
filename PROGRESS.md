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
- Step 3: `resolve.agents.text` (renderer, `parse_answer`, `TextAgent`), `tools/play_cli.py`;
  tests in `tests/agents/test_text_agent.py`, `tests/tooling/test_play_cli.py`.

- Step 4: `tools/fuzz.py` (`fuzz_run`, `fuzz_game`, `state_problems`, `invalid_answers`, CLI
  with games/second); broken test tasks in `tests/engine_support.py`; `tests/fuzz/test_fuzz.py`.
  Determinism lint now scans `resolve.agents`.

- Step 5: docs: decisions.md (4 entries), howto.md (scenario test, fuzz, play CLI),
  CLAUDE.md status (M0 complete), roadmap ticks + an M1 item for the builder's turn/step.

## In progress

- Step 6: test-reviewer, then address findings, delete PROGRESS.md, open the PR.

## Test review (round 1): Adequate with gaps. Plan per finding

- W1 non-legendary commander in scenario: DISAGREE (903.3/903.5 deck legality deferred to M7 like
  new_game; fixtures' Daybreaker isn't legendary either). Document in builder docstring + test.
- W2 401.3 -> 401.2 in text-agent test docstring. FIX.
- M1 log leak check in state_problems + negative test. M2 oracle from the rules (hand: owner or
  known_to; graveyard always named; counts and order of hand/graveyard/public zones). M3 fuzz_run
  over a 3-player Scenario with hands and known_to. M4 scenario 3-player known_to test.
- M5 replay divergence negative tests (ScriptError, ended differently) + from_log on another seed.
- M6 pre-answer pickle round-trip negative test (NaN task) + test that no state dataclass has a
  compare=False field.
- M7 run_script with a game that ends before the script (unused); rename misnamed test.
- M8 failed add leaves state equal. M9 commander in another player's hand refused (test); second
  commander: DISAGREE (deck legality, M7; StartGame raises the 613.7m gap) but test it.
- M10 subprocess replay with two PYTHONHASHSEEDs. M11 fuzz CLI formats + seed-based deck rotation
  so the reproduce command is right. M12 hot-seat prompt shows chooser's view; final view only
  with one human seat. M13 Choose step enforces player/kind. M14 chi-square uniformity tests.
- Hollow: probes with wrong id/player must carry a valid value (agent's own); negative test by
  monkeypatching validate_answer. Controller test: match messages. check_answer test: scripted
  agent (fuzz_run takes any Agent). play_cli --agent-seed boundary off by one.

## Review round 1 status

- All findings addressed (see plan above); docs updated. Next: re-run the reviewer, then PR.

## Decisions not yet in the docs

- (all recorded in docs/decisions.md)

## Open questions for the user

- (none yet)
