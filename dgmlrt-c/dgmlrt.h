#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    const char* data;
    size_t len;
} dgmlrt_string;

#define DGMLRT_LITERAL(s) ((dgmlrt_string) { s, sizeof(s) - 1 })
dgmlrt_string dgmlrt_zstr(const char* str); // calls strlen for length

// like malloc, this needs to return memory that is sufficiently aligned for any kind of variable
typedef void* (*dgmlrt_realloc)(void* ptr, size_t old_size, size_t new_size, void* ctx);

typedef struct {
    dgmlrt_realloc realloc;
    void* ctx;
} dgmlrt_alloc;

typedef struct dgmlrt_tree dgmlrt_tree;

dgmlrt_tree* dgmlrt_load_file(const char* path, dgmlrt_alloc alloc);
// data must be aligned to a multiple 4 bytes
dgmlrt_tree* dgmlrt_load_dgmlb(const uint8_t* data, size_t size, dgmlrt_alloc alloc);
void dgmlrt_free(dgmlrt_tree* tree);

typedef struct dgmlrt_vm dgmlrt_vm;

typedef uint64_t (*dgmlrt_rng_func)(void* ctx);

typedef struct {
    size_t interp_buf_capacity; // default: 1024, buffer used for string interpolation
    size_t env_var_string_capacity; // default: 128
    size_t bytecode_stack_size; // default: 64
    size_t max_steps_per_advance; // default: 128
    dgmlrt_rng_func rng_func; // default is SplitMix64
    void* rng_func_ctx;
    uint64_t rng_seed; // only used if func is not given, default is timestamp
} dgmlrt_vm_create_params;

dgmlrt_vm* dgmlrt_vm_create(
    const dgmlrt_tree* tree, dgmlrt_alloc alloc, dgmlrt_vm_create_params params);
void dgmlrt_vm_free(dgmlrt_vm* vm);

// false in failure (invalid section or node_id)
bool dgmlrt_vm_enter(dgmlrt_vm* vm, const char* section, const char* node_id);

typedef struct {
    dgmlrt_string name;
    dgmlrt_string value;
} dgmlrt_markup;

typedef struct {
    const dgmlrt_markup* markup;
    size_t num_markup;
    dgmlrt_string text;
} dgmlrt_text_fragment;

typedef struct {
    dgmlrt_string speaker_id;
    const dgmlrt_text_fragment* text_fragments;
    size_t num_text_fragments;
} dgmlrt_result_say;

typedef struct {
    const dgmlrt_text_fragment* text_fragments;
    size_t num_text_fragments;
    bool enabled;
} dgmlrt_option;

typedef struct {
    const dgmlrt_option* options;
    size_t num_options;
} dgmlrt_result_choice;

typedef enum {
    DGMLRT_ERROR_NONE = 0,
    DGMLRT_ERROR_INVALID_OPTION, // retry with adequate option_index parameter
    DGMLRT_ERROR_MAX_ITERATIONS, // don't retry
    DGMLRT_ERROR_INTERP_FAIL, // don't retry, interp buffer too small
    DGMLRT_ERROR_EVAL_FAIL, // don't retry, bytecode evaluation error (e.g. div by zero)
} dgmlrt_advance_error_code;

typedef struct {
    dgmlrt_advance_error_code code;
    const char* message;
} dgmlrt_advance_error;

typedef enum {
    DGMLRT_RESULT_TYPE_END = 0,
    DGMLRT_RESULT_TYPE_SAY,
    DGMLRT_RESULT_TYPE_CHOICE,
    DGMLRT_RESULT_TYPE_ERROR,
} dgmlrt_result_type;

// Every pointer (including those in dgmlrt_string) is only valid until the next call to advance
typedef struct {
    dgmlrt_string node_id;
    const dgmlrt_string* tags;
    size_t num_tags;
    const dgmlrt_string* changed_vars;
    size_t num_changed_vars;
    const dgmlrt_string* visited_node_ids;
    size_t num_visited_node_ids;
    dgmlrt_result_type type;
    union {
        dgmlrt_result_say say;
        dgmlrt_result_choice choice;
        dgmlrt_advance_error error;
    };
} dgmlrt_advance_result;

// Pass a negative option_index if the last result was not CHOICE
dgmlrt_advance_result dgmlrt_vm_advance(dgmlrt_vm* vm, int option_index);

typedef enum {
    DGMLRT_ENV_VALUE_UNSET = 0,
    DGMLRT_ENV_VALUE_BOOL,
    DGMLRT_ENV_VALUE_INT,
    DGMLRT_ENV_VALUE_FLOAT,
    DGMLRT_ENV_VALUE_STRING,
} dgmlrt_env_value_type;

typedef struct {
    dgmlrt_env_value_type type;
    union {
        bool b;
        int64_t i;
        float f;
        dgmlrt_string s;
    };
} dgmlrt_env_value;

typedef struct {
    dgmlrt_string name;
    dgmlrt_env_value value;
} dgmlrt_env_var;

size_t dgmlrt_get_env_vars(const dgmlrt_vm* vm, dgmlrt_env_var* vars, size_t max_num_vars);
dgmlrt_env_value dgmlrt_vm_get_env_value(const dgmlrt_vm* vm, dgmlrt_string name);
// returns true if the var could be set, false if the var does not exist or type doesn't match
bool dgmlrt_vm_set_env_value(dgmlrt_vm* vm, dgmlrt_string name, dgmlrt_env_value value);

#ifdef __cplusplus
}
#endif