# Engine Integration

If you want, you can just translate the code in [runtime.py](../dgml/runtime.py) and [play.py](../dgml/play.py).

At the very least you should have a look and I recommend copying the general design of the Python runtime for the runtime of your choice, if possible.

Essentially the task of writing an engine integration consists of consuming the compiled JSON and traversing the dialogue graph.

A schema of the output JSON can be found at the end of this document.

## General Design

You need to represent the output JSON somehow (which is easy in Python). In the Python runtime this data is represented by `DialogueTree`.

Then you need an execution environment, which allows you to reference a `DialogueTree` and actually traverses the dialogue tree. In the Python runtime this is done by the `Vm` class.

The `Vm` class keeps track of the current node and variable environment, which is initialized by the environment schema, that is also contained in the compiled JSON.

A `Vm` really only has two methods:

* `enter`, which enters a dialogue tree by section name and sets a few variables, including the current node.
* `advance`, which advances the tree but only returns information for `SAY` and `CHOICE` nodes, as these are the only ones that should lead to visible/interactible effects in the game. All nodes other than these two are henceforth called "internal nodes".

It is then only a matter of checking the type of the current node, returning the relevant information, if it is a `SAY` or `CHOICE` node or executing all other nodes and repeating.

In the "Nodes" section of the schema description, I will explain all the steps a runtime needs to execute for every node type.

## Schema Description

For example of all of these, please look at [quest.json](../examples/quest/quest.json).

### Top-Level Object

Keys:

* `build_id` (string): An MD5 hash of all source files.
* `speaker_ids` (array of strings): A list of all valid speaker IDs (taken from the config or lists all speaker IDs used).
* `sources` (array of Source): see below.
* `environment` (object): copied from the config. See below.
* `sections` (dictionary of Section): see below, keyed by the section's name.

### Source

* `path` (str): A path to the DGML file.
* `hash` (str): An MD5 hash of the contents.

### Environment

* `variables` (array of Variable): see below.
* `markup` (array of Markup): see below.

### Variable

* `name` (string): name of the variable.
* `type` (string): `bool`, `int`, `float` or `string`.
* `default` (any, optional): default value of the variable. May be a boolean, integer, float or string.

### Markup

* `name` (string): Name of the markup tag.
* `parameter` (string, optional): A regular expression for the parameter of the markup tag.

### Section

* `source_file` (string): The path to the source file the section was defined in.
* `nodes` (ditionary of Nodes): see below, keyed by the node's ID.
* `start_node` (string): The node ID of the first node of a section.

### Node

Every node has the following keys:

* `type` (string): The node type. One of `rand`, `goto`, `if`, `say`, `choice`, `run`.
* `tags` (array of string): The node's tags.

Depending on the type additional keys are present.

### Rand

* `nodes` (array of strings): An array of nodes IDs

When execution reaches a node of this type, select a node ID from `nodes` randomly and jump there.

### Goto

* `dest` (string): The node ID of the destination node.

When execution reaches a node of this type, jump to the specified node ID.

### Run

* `code` (object of type Expression): see below. Currently must be an expression of type `assign`.
* `next` (string): The node ID of the next node.

When execution reaches a node of this type, execute the given code and jump to the `next` node.

### If

* `cond` (object of type Code): see below. This expression must evaluate to a value of type `bool`.
* `true_dest` (string): The node ID of the node to jump to when the condition evaluates to true.
* `false_dest` (string): The node ID of the node to jump to when the condition evaluates to false.

When execution reaches a node of this type, evaluate the expression and jump to either `true_dest` or `false_dest`.

### Say

This node represents a line of dialogue.

* `speaker_id` (string): The speaker id.
* `line` (object of type Line): see below.
* `next` (string): The node ID of the next node.

When execution reaches a node of this type, jump to the `next` node. Then perform variable substitution in `line` and return `speaker_id` and the interpolated `line` to the caller.

### Choice

* `options` (array of Option): see below.

When execution reaches a node of this type iterate over all options, evaluate `cond`, if present and interpolate `line`. Then return a list of options and the result of their conditions to the caller.

If the VM is advanced with input (a selected option) when the current node is a choice node, jump to the `dest` node of the selected option.

### Option

* `cond` (object of type Expression, optional): see below.
* `line` (object of type Line): see below.
* `dest` (string): The node ID of the node to be jumped to when the given option is selected.

### Line

* `line_id` (string): The line ID.
* `text` (array of TextFragment): see below.

### TextFragment

* `tags` (dictionary): A dictionary with tag names as keys and tag parameters as values. If the tag does not have a parameter, the value will be `null`.
* `text` (string, optional): The text to be displayed.
* `variable` (string. optional): The variable name of the variable to be interpolated.

Exactly one of `text` or `variable` are present.

### Expression

The expression represents an abstract syntax tree node.

* `type` (string): The type of the AST node (see below).

Depending on the type multiple other keys may be present. The possible types of nodes are:

* `unary_not`: `rhs` is another Expression that evaluates to a boolean.
* `binary_add`: `lhs` and `rhs` are both Expressions that evaluate to a number type (`int` or `float`). If both types are `int` the result is `int`, otherwise the result is `float`.
* `binary_sub`: see `binary_add`.
* `binary_mul`: see `binary_add`.
* `binary_div`: see `binary_add`.
* `binary_or`: `lhs` and `rhs` are both Expressions that evaluate to a boolean.
* `binary_and`: see `binary_or`.
* `binary_lt`: `lhs` and `rhs` are both Expressions that evaluate to a number type.
* `binary_le`: see `binary_lt`.
* `binary_gt`: see `binary_lt`.see `binary_lt`.
* `binary_ge`: see `binary_lt`.see `binary_lt`.
* `binary_eq`: `lhs` and `rhs` are both Expression that evaluate to the same type or are both number types.
* `binary_ne`: see `binary_eq`.
* `variable`: `name` (string) is the name of the variable.
* `literal_bool`: `value` (bool) is a boolean value.
* `literal_int`: `value` (int) is a integer value.
* `literal_float`: `value` (float) is a float value.
* `literal_string`: `value` (string) is a string.
* `assign`: `name` (string) is the name of the variable and `value` is an Expression.


# JSON Schema

**TODO**