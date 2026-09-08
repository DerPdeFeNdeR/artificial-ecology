# Project Charter

## Purpose

Artificial Ecology is an open-ended environment in which autonomous inhabitants attempt to persist in a dangerous, changing world. The project studies which survival strategies, technologies, relationships, cultures, and social structures can arise when inhabitants receive capabilities and consequences rather than predefined social roles.

## Design goal

Provide enough reality for inhabitants to have meaningful problems, enough freedom for them to find different solutions, and enough observability for humans to understand how those solutions arose.

## Core principles

1. Inhabitants are not assigned roles such as hunter, doctor, engineer, leader, or miner.
2. Government, professions, economies, religions, traditions, alliances, and hierarchies are hypotheses about emergent behavior—not default mechanics.
3. The simulation engine is authoritative. An inhabitant or language model may request an action, but only the engine can make a legal state change.
4. Wants, beliefs, memories, plans, perceptions, and world truth are distinct data.
5. Inhabitants have imperfect information, fallible memory, incorrect beliefs, and the ability to revise beliefs.
6. Genetics transmit physical and behavioral tendencies; culture and knowledge are learned and socially transmitted.
7. Failure, exploitation, cooperation, isolation, injury, death, and extinction are valid outcomes.
8. Every important result should be reconstructable from deterministic events, snapshots, and inhabitant records.
9. Emergence is analyzed after the fact. Inhabitants should not be told the observer’s concepts or the behavior the experiment is seeking.
10. A pretrained model brings knowledge from outside the simulated world. Experiments must distinguish model priors from knowledge acquired through perception, memory, communication, and experience inside the world.

## Initial scope

The first useful world is small: a deterministic 2D environment with roughly 5–20 inhabitants, hunger, thirst, sleep, movement, perception, memory, communication, inspection, and replay. It should be interesting enough to expose architectural mistakes before adding richer ecology or social mechanics.

The first milestone should use five inhabitants and a narrow set of material actions: movement, eating, drinking, resting, and speech. It should include scripted decision controllers before LLM decisions so engine behavior can be tested independently.

## Non-goals for the first iteration

- A polished game interface
- A general-purpose human society simulator
- Prewritten professions, factions, governments, or quests
- An LLM that directly mutates world state
- Claims that a single run demonstrates a general law of emergence
