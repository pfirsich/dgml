# dgml

dgml (Dialogue Markup Language) is a toolkit for authoring and managing dialogue trees with plain text files and CLI tools.

You author your dialogues in DGML files and compile them (and other files including metadata or localizations) to a single JSON file that can easily be consumed by any engine.

## Features
* Plain text dialogues files: human-readable and work nicely with version control.
* Branching: control flow with `GOTO`, `RAND` for randomized lines.
* Conditional logic: state-aware conversations with `IF` and conditional `CHOICE` options.
* Built-in state management: simple expression language to check and modify variables (e.g. `|quest_accepted = true|`).
* Rich text & variable interpolation: inline styling with markup tags like `[bold]...[/bold]` or parameterized tags `[color:ff0000]...[/color]` (customizable).
* Custom node metadata: e.g. `#mood:happy` or `#sfx:explosion` to attach any metadata to dialogue nodes
* Engine-agnostic JSON output: compile everything to a single JSON file designed for a simple engine runtime for easy integration.
* Alternatively there is a binary output format, which can simply be memory-mapped (see [dgmlb.h](dgmlrt-c/dgmlb.h) and [dgmlb-test.cpp](dgmlrt-c/dgmlb-test.cpp)).
* Stable line ids: assign unique line IDs (`%line_id`) (or have them automatically inserted) for localization and voice overs.
* Metadata and localization (wip)
* CLI toolkit:
  * `dgml lint`: Lint dialogue files (checks for uniqueness and validity of ids, reachability of nodes, valid markup, interpolations and expressions, etc.)
  * `dgml compile`: Compile all metadata, localization and dialogue into a single JSON file
  * `dgml play`: Quickly dialogues outside of the engine
  * `dgml meta`: Manage metadata attached to lines
  * `dgml localize`: wip

## Introduction

Let's start with a simple example (see [examples/quest](examples/quest)):

```javascript
[docking_bay]

IF |quest_completed| @done
IF |quest_accepted| @active

@intro   #scene:dock #mood:cheerful
player: "Hello, weirdo!" %hello_player
alien: "Greetings, {player}. Can I tempt you with a side errand?"

@menu
CHOICE
  "What is this place?"  @about
  |not quest_accepted| "Sure, what do you need?"  @offer
  "I gotta go"  @end

@about  #mood:informative #sfx:majestic
alien: "[bold]Polestar Station[/bold] - half bazaar, half boiler room."
GOTO @menu

@offer  #mood:hopeful
alien: "Fetch my crate of [color:magenta]glow-berries[/color] from Deck 2?"
player: "Will do!"
RUN |quest_accepted = true|
GOTO @menu

@active  #mood:curious
alien: "Any luck with my [color:magenta]berries[/color]?"
CHOICE
  |inventory.glow_berries >= 5| "Here they are."  @turnin
  "Not yet."  @later

@later  #mood:encouraging
alien: "Then follow the fruity scent!"
GOTO @end

@turnin  #mood:elated
alien: "Brilliant! Take these credits."
RUN |quest_completed = true|
RUN |inventory.glow_berries = inventory.glow_berries - 5|
RUN |credits = credits + 50|
GOTO @done

@done   #mood:grateful
alien: "Thanks again. Station life tastes sweeter."
```

This DGML file can be compiled to a JSON file:


```bash
dgml compile --config quest.yaml --output quest.json quest.dgml
```

You can try out the dialogue with `dgml play`:

```bash
$ dgml play -e quest_env.json quest.json
player: Hello, weirdo!
alien: Greetings, Joel. Can I tempt you with a side errand?
1. What is this place? -> @about
2. Sure, what do you need? -> @offer
3. I gotta go -> @end
Answer: 1

alien: Polestar Station - half bazaar, half boiler room.
1. What is this place? -> @about
2. Sure, what do you need? -> @offer
3. I gotta go -> @end
Answer: 2

alien: Fetch my crate of glow-berries from Deck 2?
player: Will do!
# SET quest_accepted = True
1. What is this place? -> @about
X. Sure, what do you need? -> @offer
3. I gotta go -> @end
Answer: 3

$ dgml play -e quest_env.json quest.json
alien: Any luck with my berries?
X. Here they are. -> @turnin
2. Not yet. -> @later
Answer: 2

alien: Then follow the fruity scent!
```


## Authoring Dialogue

Dialogue is authored in DGML files, which can contain any number of "sections" (self-contained dialogue-trees). `dgml lint` can be used to lint these files during editing and `dgml play` can be used to test them outside of the game engine.

For more information see: [Authoring Dialogue](docs/authoring_dialogue.md)

## Engine Integration

All DGML files, metadata, localization information and anything else will be compiled into a single JSON file that pre-processes as much as makes sense to make it as easy as possible to implement a runtime in any language or engine.

For more information see: [Engine Integration](docs/engine_integration.md)

## TODO
* weights on rand: `RAND 3*hello_bert_1 hello_bert_2`
* status statistics for lines
* localization statistics
* `dgml dot` - generate dot files for graphviz
* `dgml localize` (`dgml compile --loc LOCFILE`)
* config: add "sources" (with glob) and "output" and "localizations" file paths
* add procedure calls for RUN. environment: `{"procedures": {"name": "initialize", "args": [string", "bool"]}}`
* dgml compile: add caching for source files (when needed)
* support ICU message format for variable interpolation (for localization)
* `dgml lint --fix add-line-ids`
* `CALL`/`RETURN`? I can't come up with good examples that need this. Either introduce `CALL @dest` that does `GOTO` and pushes a return node ID right after the `CALL` or do `GOTO @dest @return`, which additionally pushes a return node ID. Should `CHOICE` push a return ID? So many options and questions. I first need to know what this is actually needed for.
* JSON Schema in engine_integration.md.

## Sources
* https://wildwinter.medium.com/a-dialogue-pipeline-db0be8d8509c