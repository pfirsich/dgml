#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Everything is little-endian and all structs are 4-byte aligned.
// Any offset of zero means "invalid" or "empty" (because the file header is at zero).

typedef uint32_t dgmlb_off;
typedef dgmlb_off dgmlb_stroff; // points to a dgmlb_string

// This is a general type for offset + count
// Fields of this type will include a comment about the type of the elements this span points to.
typedef struct {
    dgmlb_off offset;
    uint32_t count; // not bytes, but elements (may be bytes)!
} dgmlb_span;

typedef struct {
    uint32_t length; // does not include null
    char data[1]; // includes null
} dgmlb_string;

typedef struct {
    char magic[8]; // 0x00 D G M L B 0 1
    uint32_t file_size;
    dgmlb_span strings; // packed dgmlb_strings. mind unaligned access to `length`!
    dgmlb_span sections; // dgmlb_section
    dgmlb_span speaker_ids; // dgmlb_stroff
    dgmlb_span env_variables; // dgmlb_env_var
    dgmlb_span env_markup; // dgmlb_markup, value is regex
} dgmlb_file_header;
//_Static_assert(sizeof(dgmlb_file_header) == 11 * 4);

typedef enum {
    DGMLB_VAR_TYPE_INVALID = 0,
    DGMLB_VAR_TYPE_BOOL,
    DGMLB_VAR_TYPE_INT,
    DGMLB_VAR_TYPE_FLOAT,
    DGMLB_VAR_TYPE_STRING,
} dgmlb_var_type;

typedef struct {
    dgmlb_stroff name;
    uint32_t type; // dgmlb_var_type
    uint32_t default_value; // 0/1 for bool, bit-casted for int and float, offset for string
} dgmlb_env_var;
//_Static_assert(sizeof(dgmlb_env_var) == 3 * 4);

typedef struct {
    dgmlb_stroff name;
    dgmlb_span nodes; // dgmlb_node
    uint32_t entry_node; // index into nodes
} dgmlb_section;
//_Static_assert(sizeof(dgmlb_section) == 4 * 4);

typedef uint32_t dgmlb_node_type;
enum {
    DGMLB_NODE_TYPE_INVALID = 0,
    DGMLB_NODE_TYPE_CHOICE,
    DGMLB_NODE_TYPE_GOTO,
    DGMLB_NODE_TYPE_IF,
    DGMLB_NODE_TYPE_RAND,
    DGMLB_NODE_TYPE_RUN,
    DGMLB_NODE_TYPE_SAY,
};

typedef struct {
    dgmlb_stroff id;
    dgmlb_stroff say_speaker_id;
    dgmlb_span tags; // dgmlb_stroff
    dgmlb_span code; // dgmlb_byte_code (if/run)
    dgmlb_span choice_options; // dgmlb_option
    dgmlb_span rand_nodes; // uint32_t of node indices
    dgmlb_span text; // dgmlb_text_fragment (say)
    uint32_t section_idx;
    // node indices are 0xFFFFFFFF if empty
    uint32_t next_node; // node index (goto/run/say)
    uint32_t if_true_dest; // node index (if)
    uint32_t if_false_dest; // node index (if)
    dgmlb_node_type type;
} dgmlb_node;
//_Static_assert(sizeof(dgmlb_node) == 17 * 4);

typedef struct {
    dgmlb_span cond; // dgmlb_byte_code
    dgmlb_stroff line_id; // string
    dgmlb_span text; // dgmlb_text_fragment
    uint32_t dest;
} dgmlb_option;
//_Static_assert(sizeof(dgmlb_option) == 6 * 4);

typedef struct {
    dgmlb_stroff str; // string (text or variable)
    dgmlb_span markup; // dgmlb_markup
    uint32_t is_variable; // 0 is text, 1 is variable
} dgmlb_text_fragment;
//_Static_assert(sizeof(dgmlb_text_fragment) == 4 * 4);

typedef struct {
    dgmlb_stroff key;
    dgmlb_stroff value;
} dgmlb_markup;
//_Static_assert(sizeof(dgmlb_markup) == 2 * 4);

typedef uint32_t dgmlb_byte_code_op;
enum {
    DGMLB_OP_INVALID = 0,

    DGMLB_OP_PUSH_BOOL, // param1=0/1
    DGMLB_OP_PUSH_INT, // param1=value (i32 bit-cast to u32)
    DGMLB_OP_PUSH_FLOAT, // param1=value (32 bit IEEE-754 bit-cast to u32)
    DGMLB_OP_PUSH_STRING, // param1=dgmlb_stroff

    DGMLB_OP_GET_VAR, // push value -- param1=dgmlb_stroff (var name)
    DGMLB_OP_SET_VAR, // pop value -- param1=dgmlb_stroff (var name)

    DGMLB_OP_NOT, // pop value, push negated value

    // the following binary operators will pop the right hand side operand, then the left hand side
    // operand and push the result of the operation.
    // i.e. push lhs first, then rhs.
    DGMLB_OP_ADD,
    DGMLB_OP_SUB,
    DGMLB_OP_MUL,
    DGMLB_OP_DIV,
    DGMLB_OP_OR,
    DGMLB_OP_AND,
    DGMLB_OP_LT,
    DGMLB_OP_LE,
    DGMLB_OP_GT,
    DGMLB_OP_GE,
    DGMLB_OP_EQ,
    DGMLB_OP_NE,
};

typedef struct {
    dgmlb_byte_code_op op; // dgmlb_byte_code_op
    uint32_t param;
} dgmlb_byte_code;
//_Static_assert(sizeof(dgmlb_byte_code) == 2 * 4);

#define DGMLB_PTR(T, base, off) ((T*)((const uint8_t*)(base) + (off)))
#define DGMLB_SPAN_BEGIN(T, base, sp) DGMLB_PTR(T, (base), (sp).offset)
#define DGMLB_SPAN_END(T, base, sp) (DGMLB_SPAN_BEGIN(T, (base), (sp)) + (sp).count)

#ifdef __cplusplus
}
#endif