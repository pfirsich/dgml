# Authoring Dialogue

Make sure to look at the example in the [README](../README.md).

Dialogue is separated into sections via `[section_name]`. These section names are used to address closed dialogue graphs in the runtime.

You may organize different conversations (i.e. sections) however you like across files. All DGML tools support multiple input files (where it makes sense).

Every line in a DGML file represents a node in the dialogue graph.
If the node itself does not include a jump to another node, execution advances to the node on the next line.

The following types of nodes are supported:
 
* Say: `speaker_id: "text"` - Let a character say something. A destination node may be specified optionally.
* Choice: The following lines are text options and a destination node with an optional condition (see example in the README).
* If: `IF |condition| @true_dest @false_dest` - A conditional goto. `@false_dest` is optional.
* Run: `RUN |code|` - Execute some code in the VM.
* Goto: `GOTO @node_id` - Go to another node.

Any nodes may also be annotated with a `@node_id` and any number of `#tags` in the preceding line. The end of every dialogue line may carry a `%line_id` (see [Localization](#Localization)). The node id is for branching and the line id is for dialogue line metadata. The tags may be used for anything you want, for example to play sound effects or select character portraits (like in the example in the README) or anything else you might need.

Speakers are referenced with their id, so the actual names of characters, which might need to be localized are independent of the dialogue itself. This also helps with catching typos in speaker names as we can specify a list of valid speaker ids.

See also: [Markup Grammar](../dgml/dgml.lark)

## Workflow

While editing it is recommended to use `dgml lint --watch` to catch any problems with the DGML files.

Additionally there is syntax highlighting for sublime text in [DGML.sublime-syntax](../editors/sublime-text/DGML.sublime-syntax).

## Config Files

Almost always you will want to use a YAML config file to specify a list of variables in the VM execution environment (and their types and initial values), any valid markup and valid speaker ids. `dgml lint` and `dgml compile` both take `--config`/`-c` arguments. For an example see [quest.yaml](../examples/quest/quest.yaml).

## Code

`CHOICE` conditions, `IF` nodes and `RUN` nodes may include code. The code is parsed by dgml and included in the compiled JSON as an abstract syntax tree, so it can be easily executed. `dgml compile` and `dgml lint` ensure proper typing, i.e. conditions are of type bool and (currently) `RUN` nodes only contain assignments. It also ensures that all operators have compatible operands.

Values can have the following types: `bool`, `int`, `float` and `string` and may either be literals, variables or expressions.

The following operators are supported:

* Arithmetic: `+`, `-`, `*`, `/` - operands must be number types. If both operands are integers, the result is an integer as well, otherwise it will be a float.
* Unary Logical: `not` - operand and result are bool.
* Binary Logical: `or`, `and` - operands must be booleans. The result is a boolean as well.
* Ordered Comparison: `<=`, `<`, `>`, `>=` - operands must be number types. The result is a boolean.
* Comparison: `==`, `!=` - operands can be of any type, but must match.

I am considering allowing procedure calls in `RUN` and allowing function calls in expressions.

See also: [Expression Grammar](../dgml/expressions.lark)

## Advanced Workflows

### Metadata

It is often useful to attach metadata to dialogue lines for collaboration and tracking progress without cluttering the DGML files.

Below I will list some metadata that I considered to better illustrate what this is useful for.

#### Line Status
* Placeholder: e.g. programmer-written
* Draft: first draft
* Edited: 
* Rework: needs to be reworked
* Final: don't change anymore

#### Comments
* Developer Comment: Bugs or feature requests related to certain lines
* Context Comment: How the line is going to be used
* Voice Comment: Comments for voice recording (i.e. how to read the lines, what the character might know that has not been said out loud yet, etc.)
* Localization Comment: How to translate this line properly

### Localization

This is not implemented yet, because I have no obligations for this tool and I haven't actually needed it myself yet.

Eventually you will be able to create a JSON localization file (essentially a map from line id to string):
```
dgml localize extract *.dgml -o loc/de-de.json
```

The localization file will also contain a translation status (`DRAFT`, `TRANSLATED`, `EDITED`, `REWORK`, `FINAL`).

For easier editing by translators, you will be able to export and import CSV files:

```
dgml localize export loc/de-de.json game_de-de.csv
# line_id;speaker_id;text;localization comment;translated text;status
dgml localize import loc/de-de.json game_de-de.csv
```
