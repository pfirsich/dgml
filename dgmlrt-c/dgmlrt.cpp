#include "dgmlrt.h"

#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

#include <bit>
#include <charconv>
#include <new>
#include <span>

#include "dgmlb.h"

// #define EVAL_DEBUG

dgmlrt_string dgmlrt_zstr(const char* str)
{
    if (!str) {
        return {};
    }
    return { str, strlen(str) };
}

void* default_realloc(void* ptr, size_t old_size, size_t new_size, void*)
{
    if (ptr == nullptr) { // malloc
        assert(old_size == 0);
        return malloc(new_size);
    } else {
        assert(new_size == 0); // realloc not used yet
        free(ptr);
        return nullptr;
    }
}

dgmlrt_alloc default_alloc { default_realloc, nullptr };

template <typename T>
T* allocate(dgmlrt_alloc alloc, size_t count = 1)
{
    if (count == 0) {
        return nullptr;
    }
    const auto ptr = (T*)(alloc.realloc(nullptr, 0, sizeof(T) * count, alloc.ctx));
    for (size_t i = 0; i < count; ++i) {
        new (ptr + i) T {};
    }
    return ptr;
}

template <typename T>
void deallocate(dgmlrt_alloc alloc, const T* ptr, size_t count = 1)
{
    if (!ptr) {
        return;
    }
    for (size_t i = 0; i < count; ++i) {
        (ptr + i)->~T();
    }
    alloc.realloc((T*)ptr, sizeof(T) * count, 0, alloc.ctx);
}

struct File {
    const void* base;
    size_t size;

    template <typename T>
    const T* ptr(uint32_t off) const
    {
        assert(off + sizeof(T) <= size);
        return DGMLB_PTR(const T, base, off);
    }

    template <typename T>
    const T* begin(dgmlb_span s) const
    {
        return ptr<T>(s.offset);
    }

    template <typename T>
    const T* end(dgmlb_span s) const
    {
        assert(s.offset + sizeof(T) * s.count <= size);
        return ptr<T>(s.offset) + s.count;
    }

    template <typename T>
    std::span<const T> span(dgmlb_span s) const
    {
        return std::span<const T>(begin<T>(s), end<T>(s));
    }
};

template <typename T>
struct Array {
    T* data;
    size_t size;

    T& operator[](size_t i) { return data[i]; }
    const T& operator[](size_t i) const { return data[i]; }

    void allocate(dgmlrt_alloc alloc, size_t count)
    {
        data = ::allocate<T>(alloc, count);
        size = count;
    }

    void free(dgmlrt_alloc alloc) { ::deallocate(alloc, data, size); }
};

#define EXPORT extern "C"

struct Text {
    Array<dgmlrt_text_fragment> frags;
    Array<bool> frag_is_var;
};

struct EnvVar {
    dgmlrt_string name;
    dgmlrt_env_value value;
    Array<char> string_buf;
};

struct Option {
    Text text;
    Array<dgmlb_byte_code> cond;
    uint32_t dest;
};

struct Choice {
    Array<Option> options;
};

struct Goto {
    uint32_t next_node;
};

struct If {
    Array<dgmlb_byte_code> cond;
    uint32_t true_dest;
    uint32_t false_dest;
};

struct Rand {
    Array<uint32_t> nodes;
};

struct Run {
    Array<dgmlb_byte_code> code;
    uint32_t next_node;
};

struct Say {
    dgmlrt_string speaker_id;
    Text text;
    uint32_t next_node;
};

struct Node {
    enum class Type { Invalid = 0, Choice, Goto, If, Rand, Run, Say };

    dgmlrt_string id = {};
    Array<dgmlrt_string> tags = {};
    Type type = Type::Invalid;
    union {
        Choice choice;
        Goto goto_;
        If if_;
        Rand rand;
        Run run;
        Say say;
    };
};

struct Section {
    dgmlrt_string name = {};
    Array<Node> nodes = {};
    uint32_t entry_node = UINT32_MAX;
};

struct Tree {
    dgmlrt_alloc alloc = {};
    Array<char> strings = {};
    uint32_t strings_base_offset;
    Array<EnvVar> env_vars = {};
    Array<Section> sections = {};
};

struct Vm {
    const Tree* tree = nullptr;
    dgmlrt_alloc alloc;
    Array<dgmlrt_option> options_buf = {};
    Array<dgmlrt_text_fragment> text_frags_buf = {};
    size_t text_frags_offset = 0;
    Array<dgmlrt_string> changed_vars_buf = {};
    size_t changed_vars_offset = 0;
    Array<EnvVar> env_vars = {};
    Array<char> interp_buffer = {};
    size_t interp_buffer_offset = 0;
    Array<dgmlrt_env_value> stack = {};
    size_t stack_size = 0;
    Array<dgmlrt_string> trace_buf = {};
    uint64_t rng_state;
    dgmlrt_rng_func rng_func = nullptr;
    void* rng_func_ctx = nullptr;
    size_t max_steps_per_advance;
    dgmlrt_advance_error error = {};

    const Section* current_section = nullptr;
    uint32_t current_node = UINT32_MAX;
};

EXPORT dgmlrt_tree* dgmlrt_load_file(const char* path, dgmlrt_alloc alloc)
{
    if (!alloc.realloc) {
        alloc = { default_realloc, nullptr };
    }

    auto file = fopen(path, "rb");
    if (!file) {
        return nullptr;
    }
    fseek(file, 0, SEEK_END);
    const auto size = (size_t)ftell(file);
    fseek(file, 0, SEEK_SET);
    // We use realloc directly here to avoid zero-initialization of the whole buffer
    const auto data = (uint8_t*)alloc.realloc(nullptr, 0, size, alloc.ctx);
    const auto read = fread(data, 1, size, file);
    fclose(file);

    if (read != size) {
        deallocate(alloc, data, size);
        return nullptr;
    }

    auto tree = dgmlrt_load_dgmlb(data, size, alloc);
    alloc.realloc(data, size, 0, alloc.ctx);
    return tree;
}

static dgmlrt_string string(const Tree* tree, dgmlb_stroff off)
{
    if (off == 0) {
        return {};
    }
    const auto str = tree->strings.data + (off - tree->strings_base_offset);
    uint32_t len = 0;
    memcpy(&len, str, sizeof(len)); // avoid unaligned accesses
    return { str + 4, len };
}

static void load_text(File file, Tree* tree, Text& text, dgmlb_span in_text)
{
    auto in_frags = file.span<dgmlb_text_fragment>(in_text);
    text.frags.allocate(tree->alloc, in_frags.size());
    text.frag_is_var.allocate(tree->alloc, in_frags.size());
    for (size_t f = 0; f < in_frags.size(); ++f) {
        text.frags[f].text = string(tree, in_frags[f].str);
        text.frag_is_var[f] = in_frags[f].is_variable;
        if (in_frags[f].markup.count) {
            text.frags[f].num_markup = in_frags[f].markup.count;
            auto markup = allocate<dgmlrt_markup>(tree->alloc, text.frags[f].num_markup);
            auto in_markup = file.span<dgmlb_markup>(in_frags[f].markup);
            for (size_t m = 0; m < text.frags[f].num_markup; ++m) {
                markup[m].name = string(tree, in_markup[m].key);
                markup[m].value = string(tree, in_markup[m].value);
            }
            text.frags[f].markup = markup;
        }
    }
}

static void free(dgmlrt_alloc alloc, Text& text)
{
    for (size_t f = 0; f < text.frags.size; ++f) {
        if (text.frags[f].num_markup) {
            deallocate(alloc, text.frags[f].markup, text.frags[f].num_markup);
        }
    }
    text.frag_is_var.free(alloc);
    text.frags.free(alloc);
}

static bool load(File file, Tree* tree, Choice& choice, const dgmlb_node& node)
{
    if (node.choice_options.count == 0) {
        return true;
    }

    choice.options.allocate(tree->alloc, node.choice_options.count);
    auto options = file.span<dgmlb_option>(node.choice_options);
    for (size_t o = 0; o < node.choice_options.count; ++o) {
        load_text(file, tree, choice.options[o].text, options[o].text);
        if (options[o].cond.count) {
            choice.options[o].cond.allocate(tree->alloc, options[o].cond.count);
            memcpy(choice.options[o].cond.data, file.ptr<dgmlb_byte_code>(options[o].cond.offset),
                options[o].cond.count * sizeof(dgmlb_byte_code));
        }
        choice.options[o].dest = options[o].dest;
    }
    return true;
}

static void free(dgmlrt_alloc alloc, Choice& choice)
{
    for (size_t o = 0; o < choice.options.size; ++o) {
        if (choice.options[o].cond.size) {
            choice.options[o].cond.free(alloc);
        }
        free(alloc, choice.options[o].text);
    }
    choice.options.free(alloc);
}

static void load(File file, Tree* tree, Say& say, const dgmlb_node& node)
{
    say.speaker_id = string(tree, node.say_speaker_id);
    say.next_node = node.next_node;
    load_text(file, tree, say.text, node.text);
}

static void free(dgmlrt_alloc alloc, Say& say)
{
    free(alloc, say.text);
}

EXPORT dgmlrt_tree* dgmlrt_load_dgmlb(const uint8_t* data, size_t size, dgmlrt_alloc alloc)
{
    if (!alloc.realloc) {
        alloc = { default_realloc, nullptr };
    }

    // This is adequately aligned, since data is sufficiently aligned (at least 4)
    assert((uintptr_t)data % 4 == 0);
    const auto& header = *(const dgmlb_file_header*)data;

    if (header.file_size > size) {
        fprintf(stderr, "File truncated\n");
        return nullptr;
    }

    if (memcmp(header.magic, "\0DGMLB01", 8)) {
        fprintf(stderr, "Wrong magic\n");
        return nullptr;
    }

    File file { data, size };

    auto tree = allocate<Tree>(alloc);
    tree->alloc = alloc;

    tree->strings.allocate(alloc, header.strings.count);
    memcpy(tree->strings.data, file.ptr<char>(header.strings.offset), header.strings.count);
    tree->strings_base_offset = header.strings.offset;

    tree->env_vars.allocate(alloc, header.env_variables.count);
    auto env_vars = file.span<dgmlb_env_var>(header.env_variables);
    for (size_t i = 0; i < header.env_variables.count; ++i) {
        tree->env_vars[i].name = string(tree, env_vars[i].name);
        tree->env_vars[i].value.type = (dgmlrt_env_value_type)env_vars[i].type;
        switch (env_vars[i].type) {
        case DGMLB_VAR_TYPE_BOOL:
            tree->env_vars[i].value.b = env_vars[i].default_value != 0;
            break;
        case DGMLB_VAR_TYPE_INT:
            tree->env_vars[i].value.i = (int64_t)std::bit_cast<int32_t>(env_vars[i].default_value);
            break;
        case DGMLB_VAR_TYPE_FLOAT:
            tree->env_vars[i].value.f = std::bit_cast<float>(env_vars[i].default_value);
            break;
        case DGMLB_VAR_TYPE_STRING:
            tree->env_vars[i].value.s = string(tree, env_vars[i].default_value);
            break;
        }
    }

    tree->sections.allocate(alloc, header.sections.count);
    auto sections = file.span<dgmlb_section>(header.sections);
    for (size_t s = 0; s < header.sections.count; ++s) {
        tree->sections[s].name = string(tree, sections[s].name);
        tree->sections[s].entry_node = sections[s].entry_node;
        tree->sections[s].nodes.allocate(alloc, sections[s].nodes.count);
        auto nodes = file.span<dgmlb_node>(sections[s].nodes);
        for (size_t n = 0; n < tree->sections[s].nodes.size; ++n) {
            auto& node = tree->sections[s].nodes[n];
            node.id = string(tree, nodes[n].id);
            node.tags.allocate(alloc, nodes[n].tags.count);
            auto tags = file.span<dgmlb_stroff>(nodes[n].tags);
            for (size_t t = 0; t < node.tags.size; ++t) {
                node.tags[t] = string(tree, tags[t]);
            }
            node.type = (Node::Type)nodes[n].type;
            switch (node.type) {
            case Node::Type::Choice:
                load(file, tree, node.choice, nodes[n]);
                break;
            case Node::Type::Goto:
                node.goto_.next_node = nodes[n].next_node;
                break;
            case Node::Type::If:
                node.if_.cond.allocate(alloc, nodes[n].code.count);
                memcpy(node.if_.cond.data, file.ptr<dgmlb_byte_code>(nodes[n].code.offset),
                    node.if_.cond.size * sizeof(dgmlb_byte_code));
                node.if_.true_dest = nodes[n].if_true_dest;
                node.if_.false_dest = nodes[n].if_false_dest;
                break;
            case Node::Type::Rand:
                node.rand.nodes.allocate(alloc, nodes[n].rand_nodes.count);
                memcpy(node.rand.nodes.data, file.ptr<uint32_t>(nodes[n].rand_nodes.offset),
                    node.rand.nodes.size * sizeof(uint32_t));
                break;
            case Node::Type::Run:
                node.run.code.allocate(alloc, nodes[n].code.count);
                memcpy(node.run.code.data, file.ptr<dgmlb_byte_code>(nodes[n].code.offset),
                    node.run.code.size * sizeof(dgmlb_byte_code));
                node.run.next_node = nodes[n].next_node;
                break;
            case Node::Type::Say:
                load(file, tree, node.say, nodes[n]);
                break;
            default:
                fprintf(stderr, "Invalid node type: %u\n", nodes[n].type);
                dgmlrt_free((dgmlrt_tree*)tree);
                return nullptr;
            }
        }
    }

    return (dgmlrt_tree*)tree;
}

EXPORT void dgmlrt_free(dgmlrt_tree* otree)
{
    auto tree = (Tree*)otree;
    for (size_t s = 0; s < tree->sections.size; ++s) {
        for (size_t n = 0; n < tree->sections[s].nodes.size; ++n) {
            auto& node = tree->sections[s].nodes[n];

            switch (node.type) {
            case Node::Type::Choice:
                free(tree->alloc, node.choice);
                break;
            // nothing to do for goto
            case Node::Type::If:
                node.if_.cond.free(tree->alloc);
                break;
            case Node::Type::Rand:
                node.rand.nodes.free(tree->alloc);
                break;
            case Node::Type::Run:
                node.run.code.free(tree->alloc);
                break;
            case Node::Type::Say:
                free(tree->alloc, node.say);
                break;
            default:
                // Likely uninitialized because of error in earlier node, nothing to do
                break;
            }

            node.tags.free(tree->alloc);
        }
        tree->sections[s].nodes.free(tree->alloc);
    }
    tree->sections.free(tree->alloc);
    tree->env_vars.free(tree->alloc);
    tree->strings.free(tree->alloc);
    deallocate(tree->alloc, tree);
}

static uint64_t splitmix64(void* ctx)
{
    auto& s = *(uint64_t*)ctx;
    uint64_t z = (s += 0x9e3779b97f4a7c15ull);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ull;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebull;
    return z ^ (z >> 31);
}

template <typename T>
T max(T a, T b)
{
    return a > b ? a : b;
}

EXPORT dgmlrt_vm* dgmlrt_vm_create(
    const dgmlrt_tree* otree, dgmlrt_alloc alloc, dgmlrt_vm_create_params params)
{
    auto tree = (const Tree*)otree;

    if (!alloc.realloc) {
        alloc = tree->alloc;
    }

    auto vm = allocate<Vm>(alloc);
    vm->tree = (Tree*)otree;
    vm->alloc = alloc;
    vm->env_vars.allocate(alloc, vm->tree->env_vars.size);
    vm->changed_vars_buf.allocate(alloc, vm->tree->env_vars.size);
    const auto interp_buffer_cap = params.interp_buf_capacity ? params.interp_buf_capacity : 1024;
    vm->interp_buffer.allocate(alloc, interp_buffer_cap);
    const auto stack_size = params.bytecode_stack_size ? params.bytecode_stack_size : 64;
    vm->stack.allocate(alloc, stack_size);
    vm->max_steps_per_advance = params.max_steps_per_advance ? params.max_steps_per_advance : 128;

    for (size_t v = 0; v < vm->env_vars.size; ++v) {
        vm->env_vars[v] = vm->tree->env_vars[v];
        vm->env_vars[v].string_buf.allocate(
            alloc, params.env_var_string_capacity ? params.env_var_string_capacity : 128);
    }

    size_t max_num_options = 0;
    size_t max_text_frags = 0;
    for (size_t s = 0; s < vm->tree->sections.size; ++s) {
        for (size_t n = 0; n < vm->tree->sections[s].nodes.size; ++n) {
            const auto& node = vm->tree->sections[s].nodes[n];
            if (node.type == Node::Type::Say) {
                max_text_frags = max(max_text_frags, node.say.text.frags.size);
            } else if (node.type == Node::Type::Choice) {
                size_t num_frags = 0;
                for (size_t o = 0; o < node.choice.options.size; ++o) {
                    num_frags += node.choice.options[o].text.frags.size;
                }
                max_num_options = max(max_num_options, node.choice.options.size);
                max_text_frags = max(max_text_frags, num_frags);
            }
        }
    }
    vm->options_buf.allocate(alloc, max_num_options);
    vm->trace_buf.allocate(alloc, vm->max_steps_per_advance);
    vm->text_frags_buf.allocate(alloc, max_text_frags);

    if (params.rng_func) {
        vm->rng_func = params.rng_func;
        vm->rng_func_ctx = params.rng_func_ctx;
    } else {
        vm->rng_state = params.rng_seed ? params.rng_seed : (uint64_t)time(nullptr);
        vm->rng_func = splitmix64;
        vm->rng_func_ctx = &vm->rng_state;
    }

    return (dgmlrt_vm*)vm;
}

EXPORT void dgmlrt_vm_free(dgmlrt_vm* ovm)
{
    auto vm = (Vm*)ovm;
    vm->trace_buf.free(vm->alloc);
    vm->options_buf.free(vm->alloc);
    vm->text_frags_buf.free(vm->alloc);
    for (size_t v = 0; v < vm->env_vars.size; ++v) {
        vm->env_vars[v].string_buf.free(vm->alloc);
    }
    vm->stack.free(vm->alloc);
    vm->interp_buffer.free(vm->alloc);
    vm->changed_vars_buf.free(vm->alloc);
    vm->env_vars.free(vm->alloc);
    deallocate(vm->alloc, vm);
}

static bool operator==(const dgmlrt_string& a, const dgmlrt_string& b)
{
    return a.len == b.len && strncmp(a.data, b.data, a.len) == 0;
}

static bool operator!=(const dgmlrt_string& a, const dgmlrt_string& b)
{
    return !(a == b);
}

EXPORT bool dgmlrt_vm_enter(dgmlrt_vm* ovm, const char* section, const char* node_id)
{
    auto vm = (Vm*)ovm;
    const Section* sec = nullptr;
    const auto section_str = dgmlrt_zstr(section);
    for (size_t s = 0; s < vm->tree->sections.size; ++s) {
        if (section_str == vm->tree->sections[s].name) {
            sec = &vm->tree->sections[s];
            break;
        }
    }

    if (!sec) {
        return false;
    }

    uint32_t node_idx = UINT32_MAX;
    const auto node_id_str = dgmlrt_zstr(node_id);
    if (node_id) {
        for (uint32_t n = 0; n < sec->nodes.size; ++n) {
            if (node_id_str == sec->nodes[n].id) {
                node_idx = n;
                break;
            }
        }
        if (node_idx == UINT32_MAX) {
            return false;
        }
    } else {
        node_idx = sec->entry_node;
    }

    vm->current_section = sec;
    vm->current_node = node_idx;
    return true;
}

static dgmlrt_env_value env_value(bool b)
{
    return { .type = DGMLRT_ENV_VALUE_BOOL, .b = b };
}

static dgmlrt_env_value env_value(int64_t i)
{
    return { .type = DGMLRT_ENV_VALUE_INT, .i = i };
}

static dgmlrt_env_value env_value(float f)
{
    return { .type = DGMLRT_ENV_VALUE_FLOAT, .f = f };
}

static dgmlrt_env_value env_value(dgmlrt_string s)
{
    return { .type = DGMLRT_ENV_VALUE_STRING, .s = s };
}

static void push(Vm* vm, dgmlrt_env_value v)
{
    if (vm->stack_size >= vm->stack.size) {
        vm->error = { DGMLRT_ERROR_EVAL_FAIL, "Stack overflow" };
        return;
    }
    vm->stack[vm->stack_size++] = v;
}

static dgmlrt_env_value pop(Vm* vm)
{
    if (vm->stack_size == 0) {
        return { .type = DGMLRT_ENV_VALUE_UNSET };
    }
    const auto v = vm->stack[vm->stack_size - 1];
    vm->stack_size--;
    return v;
}

static bool is_num_type(const dgmlrt_env_value_type& t)
{
    return t == DGMLRT_ENV_VALUE_INT || t == DGMLRT_ENV_VALUE_FLOAT;
}

template <bool AllowString, typename Func>
void binop(Vm* vm, Func&& func)
{
    const auto rhs = pop(vm);
    const auto lhs = pop(vm);
    if (lhs.type == DGMLRT_ENV_VALUE_UNSET || rhs.type == DGMLRT_ENV_VALUE_UNSET) {
        vm->error = { DGMLRT_ERROR_EVAL_FAIL, "Missing operands for binary operator" };
        return;
    }
    const auto size_before = vm->stack_size;

    // The types have been checked by dgml compile, so this should be true
    const auto both_num = is_num_type(lhs.type) && is_num_type(rhs.type);
    if (lhs.type != rhs.type && !both_num) {
        vm->error = { DGMLRT_ERROR_EVAL_FAIL, "Invalid binary operand types" };
        return;
    }

    if (lhs.type == DGMLRT_ENV_VALUE_INT && rhs.type == DGMLRT_ENV_VALUE_INT) {
        push(vm, env_value(func(lhs.i, rhs.i)));
    } else if (lhs.type == DGMLRT_ENV_VALUE_INT && rhs.type == DGMLRT_ENV_VALUE_FLOAT) {
        push(vm, env_value(func((float)lhs.i, rhs.f)));
    } else if (lhs.type == DGMLRT_ENV_VALUE_FLOAT && rhs.type == DGMLRT_ENV_VALUE_INT) {
        push(vm, env_value(func(lhs.f, (float)rhs.i)));
    } else if (lhs.type == DGMLRT_ENV_VALUE_FLOAT && rhs.type == DGMLRT_ENV_VALUE_FLOAT) {
        push(vm, env_value(func(lhs.f, rhs.f)));
    } else if (lhs.type == DGMLRT_ENV_VALUE_BOOL && rhs.type == DGMLRT_ENV_VALUE_BOOL) {
        push(vm, env_value((bool)func(lhs.b, rhs.b)));
    }

    if constexpr (AllowString) {
        if (lhs.type == DGMLRT_ENV_VALUE_STRING && rhs.type == DGMLRT_ENV_VALUE_STRING) {
            push(vm, env_value(func(lhs.s, rhs.s)));
        }
    }

    if (vm->stack_size == size_before) {
        // nothing was pushed
        vm->error = { DGMLRT_ERROR_EVAL_FAIL, "Invalid binary operand types" };
        return;
    }
}

#ifdef EVAL_DEBUG
static void dump_op(Vm* vm, dgmlb_byte_code code)
{
    switch (code.op) {
    case DGMLB_OP_INVALID:
        printf("INVALID\n");
        break;

    case DGMLB_OP_PUSH_BOOL:
        printf("PUSH_BOOL(%s)\n", code.param ? "true" : "false");
        break;
    case DGMLB_OP_PUSH_INT:
        printf("PUSH_INT(%d)\n", std::bit_cast<int32_t>(code.param));
        break;
    case DGMLB_OP_PUSH_FLOAT:
        printf("PUSH_FLOAT(%f)\n", std::bit_cast<float>(code.param));
        break;
    case DGMLB_OP_PUSH_STRING:
        printf("PUSH_STRING(%s)\n", string(vm->tree, code.param).data);
        break;

    case DGMLB_OP_GET_VAR:
        printf("GET_VAR(%s)\n", string(vm->tree, code.param).data);
        break;
    case DGMLB_OP_SET_VAR:
        printf("SET_VAR(%s)\n", string(vm->tree, code.param).data);
        break;

    case DGMLB_OP_NOT:
        printf("NOT\n");
        break;

    case DGMLB_OP_ADD:
        printf("ADD\n");
        break;
    case DGMLB_OP_SUB:
        printf("SUB\n");
        break;
    case DGMLB_OP_MUL:
        printf("MUL\n");
        break;
    case DGMLB_OP_DIV:
        printf("DIV\n");
        break;
    case DGMLB_OP_OR:
        printf("OR\n");
        break;
    case DGMLB_OP_AND:
        printf("AND\n");
        break;
    case DGMLB_OP_LT:
        printf("LT\n");
        break;
    case DGMLB_OP_LE:
        printf("LE\n");
        break;
    case DGMLB_OP_GT:
        printf("GT\n");
        break;
    case DGMLB_OP_GE:
        printf("GE\n");
        break;
    case DGMLB_OP_EQ:
        printf("EQ\n");
        break;
    case DGMLB_OP_NE:
        printf("NE\n");
        break;
    }
}

static void dump_stack(Vm* vm)
{
    printf("stack (%lu): {", vm->stack_size);
    for (size_t i = 0; i < vm->stack_size; ++i) {
        if (i > 0) {
            printf(", ");
        }
        switch (vm->stack[i].type) {
        case DGMLRT_ENV_VALUE_UNSET:
            printf("empty");
            break;
        case DGMLRT_ENV_VALUE_BOOL:
            printf(vm->stack[i].b ? "(bool) true" : "(bool) false");
            break;
        case DGMLRT_ENV_VALUE_INT:
            printf("(int) %ld", vm->stack[i].i);
            break;
        case DGMLRT_ENV_VALUE_FLOAT:
            printf("(float) %f", vm->stack[i].f);
            break;
        case DGMLRT_ENV_VALUE_STRING:
            printf("(str) '%s'", vm->stack[i].s.data);
            break;
        }
    }
    printf("}\n");
}
#endif

static dgmlrt_env_value* eval(Vm* vm, dgmlb_byte_code* code, size_t size)
{
    vm->stack_size = 0; // clear stack

    for (size_t c = 0; c < size; ++c) {
#ifdef EVAL_DEBUG
        dump_stack(vm);
        dump_op(vm, code[c]);
#endif
        switch (code[c].op) {
        case DGMLB_OP_PUSH_BOOL:
            push(vm, env_value(code[c].param == 1));
            break;
        case DGMLB_OP_PUSH_INT:
            push(vm, env_value((int64_t)std::bit_cast<int32_t>(code[c].param)));
            break;
        case DGMLB_OP_PUSH_FLOAT:
            push(vm, env_value(std::bit_cast<float>(code[c].param)));
            break;
        case DGMLB_OP_PUSH_STRING:
            push(vm, env_value(string(vm->tree, code[c].param)));
            break;

        case DGMLB_OP_GET_VAR: {
            const auto name = string(vm->tree, code[c].param);
            push(vm, dgmlrt_vm_get_env_value((dgmlrt_vm*)vm, name));
            break;
        }
        case DGMLB_OP_SET_VAR: {
            const auto name = string(vm->tree, code[c].param);
            bool changed_var_found = false;
            for (size_t v = 0; v < vm->changed_vars_offset; ++v) {
                if (vm->changed_vars_buf[v] == name) {
                    changed_var_found = true;
                    break;
                }
            }
            if (!changed_var_found) {
                vm->changed_vars_buf[vm->changed_vars_offset++] = name;
            }
            dgmlrt_vm_set_env_value((dgmlrt_vm*)vm, name, pop(vm));
            break;
        }

        case DGMLB_OP_NOT: {
            const auto top = pop(vm);
            if (top.type != DGMLRT_ENV_VALUE_BOOL) {
                vm->error = { DGMLRT_ERROR_EVAL_FAIL, "operand of NOT must be of type bool" };
                return nullptr;
            }
            push(vm, env_value(!top.b));
            break;
        }

        case DGMLB_OP_ADD:
            binop<false>(vm, [](auto a, auto b) { return a + b; });
            break;
        case DGMLB_OP_SUB:
            binop<false>(vm, [](auto a, auto b) { return a - b; });
            break;
        case DGMLB_OP_MUL:
            binop<false>(vm, [](auto a, auto b) { return a * b; });
            break;
        case DGMLB_OP_DIV:
            if (vm->stack_size >= 2 && vm->stack[vm->stack_size - 1].type == DGMLRT_ENV_VALUE_INT
                && vm->stack[vm->stack_size - 2].type == DGMLRT_ENV_VALUE_INT
                && vm->stack[vm->stack_size - 1].i == 0) {
                vm->error = { DGMLRT_ERROR_EVAL_FAIL, "division by zero" };
                return nullptr;
            }
            binop<false>(vm, [](auto a, auto b) { return a / b; });
            break;
        case DGMLB_OP_OR:
            binop<false>(vm, [](auto a, auto b) { return (bool)a || (bool)b; });
            break;
        case DGMLB_OP_AND:
            binop<false>(vm, [](auto a, auto b) { return (bool)a && (bool)b; });
            break;
        case DGMLB_OP_LT:
            binop<false>(vm, [](auto a, auto b) { return a < b; });
            break;
        case DGMLB_OP_LE:
            binop<false>(vm, [](auto a, auto b) { return a <= b; });
            break;
        case DGMLB_OP_GT:
            binop<false>(vm, [](auto a, auto b) { return a > b; });
            break;
        case DGMLB_OP_GE:
            binop<false>(vm, [](auto a, auto b) { return a >= b; });
            break;
        case DGMLB_OP_EQ:
            binop<true>(vm, [](auto a, auto b) { return a == b; });
            break;
        case DGMLB_OP_NE:
            binop<true>(vm, [](auto a, auto b) { return a != b; });
            break;
        default:
            vm->error = { DGMLRT_ERROR_EVAL_FAIL, "Invalid byte code" };
        }

        if (vm->error.code) {
            return nullptr;
        }
    }
#ifdef EVAL_DEBUG
    printf("before return\n");
    dump_stack(vm);
#endif

    return vm->stack_size > 0 ? &vm->stack[vm->stack_size - 1] : nullptr;
}

template <typename T>
static dgmlrt_string interp(Vm* vm, const T& v)
{
    const auto begin = vm->interp_buffer.data + vm->interp_buffer_offset;
    // -1 to leave room for NUL
    const auto end = vm->interp_buffer.data + vm->interp_buffer.size - 1;
    const auto res = std::to_chars(begin, end, v);
    if (res.ec != std::errc {}) {
        return {};
    }
    assert(res.ptr > begin && res.ptr < end);
    *res.ptr = '\0';
    const auto len = (size_t)(res.ptr - begin);
    vm->interp_buffer_offset += len + 1 /*NUL*/;
    return { begin, len };
}

template <size_t N>
constexpr dgmlrt_string literal(const char (&arr)[N])
{
    return { arr, N - 1 };
}

struct InterpolateTextResult {
    const dgmlrt_text_fragment* frags;
    size_t num_frags;
};

static InterpolateTextResult interpolate_text(Vm* vm, const Text& text)
{
    auto frags = vm->text_frags_buf.data + vm->text_frags_offset;
    assert(vm->text_frags_offset + text.frags.size <= vm->text_frags_buf.size);
    for (size_t f = 0; f < text.frags.size; ++f) {
        frags[f] = { .markup = text.frags[f].markup, .num_markup = text.frags[f].num_markup };
        if (text.frag_is_var[f]) {
            const auto val = dgmlrt_vm_get_env_value((dgmlrt_vm*)vm, text.frags[f].text);
            switch (val.type) {
            case DGMLRT_ENV_VALUE_UNSET:
                frags[f].text = {}; // empty string
                break;
            case DGMLRT_ENV_VALUE_BOOL:
                frags[f].text = val.b ? literal("true") : literal("false");
                break;
            case DGMLRT_ENV_VALUE_INT:
                frags[f].text = interp(vm, val.i);
                if (!frags[f].text.data) {
                    return {};
                }
                break;
            case DGMLRT_ENV_VALUE_FLOAT:
                frags[f].text = interp(vm, val.f);
                if (!frags[f].text.data) {
                    return {};
                }
                break;
            case DGMLRT_ENV_VALUE_STRING:
                frags[f].text = val.s;
                break;
            }
        } else {
            frags[f].text = text.frags[f].text;
        }
    }
    vm->text_frags_offset += text.frags.size;
    return { frags, text.frags.size };
}

EXPORT dgmlrt_advance_result dgmlrt_vm_advance(dgmlrt_vm* ovm, int option_index)
{
    auto vm = (Vm*)ovm;
    assert(vm->current_section); // Must have called vm_enter before

    if (option_index >= 0) {
        const auto node = vm->current_section->nodes[vm->current_node];
        if (node.type != Node::Type::Choice || (size_t)option_index >= node.choice.options.size) {
            return {
                .type = DGMLRT_RESULT_TYPE_ERROR,
                .error = { DGMLRT_ERROR_INVALID_OPTION, "Invalid option" },
            };
        }
        // I don't care if the option is disabled. It's your dialog!
        vm->current_node = node.choice.options[(size_t)option_index].dest;
    }

    vm->interp_buffer_offset = 0;
    vm->text_frags_offset = 0;

    dgmlrt_advance_result res = {
        .visited_node_ids = vm->trace_buf.data,
        .num_visited_node_ids = 0,
    };

    auto error = [&](dgmlrt_advance_error err) {
        vm->error = err;
        res.type = DGMLRT_RESULT_TYPE_ERROR;
        res.error = vm->error;
        return res;
    };

    while (vm->current_node < vm->current_section->nodes.size) {
        const auto node = vm->current_section->nodes[vm->current_node];
        vm->trace_buf[res.num_visited_node_ids++] = node.id;
        res.node_id = node.id;
        res.tags = node.tags.data;
        res.num_tags = node.tags.size;

        switch (node.type) {
        // Interactive nodes
        case Node::Type::Say: {
            vm->current_node = node.say.next_node;
            const auto [frags, num_frags] = interpolate_text(vm, node.say.text);
            if (!frags) {
                return error({ DGMLRT_ERROR_INTERP_FAIL, "Interpolation failed" });
            }
            res.type = DGMLRT_RESULT_TYPE_SAY;
            res.say = {
                .speaker_id = node.say.speaker_id,
                .text_fragments = frags,
                .num_text_fragments = num_frags,
            };
            return res;
        }
        case Node::Type::Choice:
            assert(node.choice.options.size <= vm->options_buf.size);
            for (size_t o = 0; o < node.choice.options.size; ++o) {
                auto& opt = node.choice.options[o];
                const auto cond = eval(vm, opt.cond.data, opt.cond.size);
                if (vm->error.code) {
                    return error(vm->error);
                }
                if (opt.cond.size > 0 && (!cond || cond->type != DGMLRT_ENV_VALUE_BOOL)) {
                    return error({ DGMLRT_ERROR_EVAL_FAIL, "Condition type must be bool" });
                }
                const auto [frags, num_frags] = interpolate_text(vm, opt.text);
                if (!frags) {
                    return error({ DGMLRT_ERROR_INTERP_FAIL, "Interpolation failed" });
                }
                vm->options_buf[o] = {
                    .text_fragments = frags,
                    .num_text_fragments = num_frags,
                    .enabled = opt.cond.size == 0 || cond->b,
                };
            }

            res.type = DGMLRT_RESULT_TYPE_CHOICE;
            res.choice = {
                .options = vm->options_buf.data,
                .num_options = node.choice.options.size,
            };
            return res;
        // Internal nodes
        case Node::Type::Goto:
            vm->current_node = node.goto_.next_node;
            break;
        case Node::Type::If: {
            const auto res = eval(vm, node.if_.cond.data, node.if_.cond.size);
            if (vm->error.code) {
                return error(vm->error);
            }
            if (!res || res->type != DGMLRT_ENV_VALUE_BOOL) {
                return error({ DGMLRT_ERROR_EVAL_FAIL, "Condition type must be bool" });
            }
            if (res->b) {
                vm->current_node = node.if_.true_dest;
            } else {
                vm->current_node = node.if_.false_dest;
            }
            break;
        }
        case Node::Type::Rand: {
            assert(node.rand.nodes.size > 0);
            const auto idx = vm->rng_func(vm->rng_func_ctx) % node.rand.nodes.size;
            vm->current_node = node.rand.nodes[idx];
            break;
        }
        case Node::Type::Run:
            eval(vm, node.run.code.data, node.run.code.size);
            if (vm->error.code) {
                return error(vm->error);
            }
            vm->current_node = node.run.next_node;
            break;
        default:
            abort(); // should be unreachable, because we checked type during load
        }

        if (res.num_visited_node_ids >= vm->max_steps_per_advance) {
            return error({ DGMLRT_ERROR_MAX_ITERATIONS, "Exceeded max iterations" });
        }
    }

    res.type = DGMLRT_RESULT_TYPE_END;
    return res;
}

EXPORT size_t dgmlrt_get_env_vars(const dgmlrt_vm* ovm, dgmlrt_env_var* vars, size_t max_num_vars)
{
    auto vm = (Vm*)ovm;
    const auto n = max_num_vars < vm->env_vars.size ? max_num_vars : vm->env_vars.size;
    for (size_t v = 0; v < n; ++v) {
        vars[v].name = vm->env_vars[v].name;
        vars[v].value = vm->env_vars[v].value;
    }
    return n;
}

EXPORT dgmlrt_env_value dgmlrt_vm_get_env_value(const dgmlrt_vm* ovm, dgmlrt_string name)
{
    auto vm = (Vm*)ovm;
    for (size_t v = 0; v < vm->env_vars.size; ++v) {
        if (vm->env_vars[v].name == name) {
            return vm->env_vars[v].value;
        }
    }
    return { .type = DGMLRT_ENV_VALUE_UNSET };
}

static bool set_env_value(EnvVar& dst, const dgmlrt_env_value& src)
{
    assert(src.type == dst.value.type);
    if (src.type == DGMLRT_ENV_VALUE_STRING) {
        if (src.s.len >= dst.string_buf.size) {
            return false;
        }
        memcpy(dst.string_buf.data, src.s.data, src.s.len);
        dst.string_buf.data[src.s.len] = '\0';
        dst.value.s = { dst.string_buf.data, src.s.len };
    } else {
        dst.value = src;
    }
    return true;
}

EXPORT bool dgmlrt_vm_set_env_value(dgmlrt_vm* ovm, dgmlrt_string name, dgmlrt_env_value value)
{
    auto vm = (Vm*)ovm;
    for (size_t v = 0; v < vm->env_vars.size; ++v) {
        if (vm->env_vars[v].name == name) {
            if (vm->env_vars[v].value.type == value.type) {
                return set_env_value(vm->env_vars[v], value);
            } else {
                return false;
            }
        }
    }
    return false;
}