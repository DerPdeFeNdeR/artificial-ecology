# Experiments and Evaluation

Artificial Ecology should be evaluated as a scientific instrument as well as a simulation. A surprising behavior is a lead, not a conclusion.

## Experiment record

Each experiment should state:

- question and falsifiable prediction
- initial world and inhabitant conditions
- what capabilities are available
- what concepts are deliberately absent from inhabitant inputs
- what knowledge may already be present in the inhabitant controller or pretrained model
- random seeds and run count
- measurements and observer-only classifications
- stopping rules
- surprising or negative results

## Guarding against accidental hardcoding

Before calling a pattern emergent, inspect whether it was smuggled in through:

- role-specific action sets or rewards
- privileged information
- vocabulary that names the target institution
- fixed cooperation, leadership, or ownership variables
- scripted resource dependencies
- biased reproduction or selection
- LLM prompts that describe the desired social outcome
- assuming a model-generated behavior was invented solely because it was not stated in the prompt

Pretrained language models carry knowledge from outside the simulated world. Treat model behavior as a prior or baseline. To study within-world learning, compare it with scripted controllers, a memory-disabled condition, a communication-disabled condition, unfamiliar material arrangements, and controlled model or prompt variants.

## Useful early comparisons

- communication enabled versus disabled
- reliable memory versus noisy memory
- equal versus unequal starting resources
- stable versus changing resource locations
- narrow versus broad action affordances
- rule-based planner versus LLM-assisted planner under identical engine conditions
- single-seed behavior versus behavior repeated across many seeds
- recorded playback versus engine verification replay

The goal is not to force a particular society. The goal is to learn which environmental, cognitive, and transmission conditions make different patterns more or less likely.

## Analysis discipline

Use event traces to separate:

1. what the world did,
2. what the inhabitant perceived,
3. what the inhabitant believed,
4. what the inhabitant wanted,
5. what it decided,
6. what happened afterward, and
7. what the observer calls the pattern.

Any “why” explanation should identify evidence and uncertainty rather than present an observer’s label as the inhabitant’s own motive.

## Initial acceptance checks

The first milestone should demonstrate that:

- the same seed and recorded decisions reproduce the same state;
- model request completion order does not determine conflict outcomes;
- an inhabitant cannot consume a resource twice;
- hidden world information does not enter an inhabitant’s observation;
- model unavailability produces an explicit recorded infrastructure failure;
- memory or communication changes later behavior in repeatable scenarios.

## Baseline observer run: scripted survival demo

Date: 2026-09-08

The first browser-observer demo used five inhabitants in a 12x8 grid with scripted movement, food, water, and obstacles. No LLM decisions, communication, crafting, reproduction, or cooperation were enabled.

Observed result:

- inhabitants 0–3 died from hunger at tick 100;
- inhabitant 4 reached the food at `(9, 2)`, consumed the remaining supply, reached water at `(10, 6)`, and drank twice;
- inhabitant 4 then died from fatigue at tick 100;
- the remaining food at `(2, 5)` was never reached;
- the scripted controller produced repeated movement loops, boundary failures, and collision failures;
- no inhabitants rested, communicated, or cooperated.

Interpretation: this is a controller and scenario baseline, not evidence about emergent behavior. The engine correctly enforced need accumulation, resource consumption, movement validation, and death. The run exposed the need for better baseline navigation, rest decisions, and complete event-run persistence before evaluating LLM-assisted behavior.

Implementation note: the run exposed duplicate death events for already-dead inhabitants. The engine now skips dead inhabitants during need advancement, and a regression test verifies that each death is emitted once.
