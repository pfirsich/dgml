// This is an example of how to read dgmlb files.

#include <bit>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <span>
#include <string>

#include "dgmlb.h"

struct File {
    const void* base;
    size_t size;

    template <typename T>
    const T* ptr(uint32_t off) const
    {
        assert(off < size);
        return DGMLB_PTR(const T, base, off);
    }

    const char* str(dgmlb_stroff off) const { return ptr<dgmlb_string>(off)->data; }

    template <typename T>
    const T* begin(dgmlb_span s) const
    {
        return ptr<T>(s.offset);
    }

    template <typename T>
    const T* end(dgmlb_span s) const
    {
        return ptr<T>(s.offset) + s.count;
    }

    template <typename T>
    std::span<const T> span(dgmlb_span s) const
    {
        return std::span<const T>(begin<T>(s), end<T>(s));
    }
};

const char* join(File file, dgmlb_span strings)
{
    static std::string out;
    out.clear();
    bool first = true;
    for (const auto& s : file.span<dgmlb_stroff>(strings)) {
        if (!first) {
            out.append(", ");
        }
        first = false;
        out.append(file.str(s));
    }
    return out.c_str();
}

const char* text(File file, dgmlb_span text)
{
    static std::string out;
    out.clear();
    out.append("\"");
    for (const auto& frag : file.span<dgmlb_text_fragment>(text)) {
        if (frag.is_variable) {
            out.append("${");
            out.append(file.str(frag.str));
            out.append("}");
        } else {
            out.append(file.str(frag.str));
        }
    }
    out.append("\"");
    return out.c_str();
}

const char* op(File file, dgmlb_byte_code code)
{
    static char buf[256];
    switch (code.op) {
    case DGMLB_OP_PUSH_BOOL:
        sprintf(buf, "PUSH_BOOL(%u)", code.param);
        return buf;
    case DGMLB_OP_PUSH_INT:
        sprintf(buf, "PUSH_INT(%d)", std::bit_cast<int32_t>(code.param));
        return buf;
    case DGMLB_OP_PUSH_FLOAT:
        sprintf(buf, "PUSH_FLOAT(%f)", std::bit_cast<float>(code.param));
        return buf;
    case DGMLB_OP_PUSH_STRING:
        sprintf(buf, "PUSH_STRING(%s)", file.str(code.param));
        return buf;
    case DGMLB_OP_GET_VAR:
        sprintf(buf, "GET_VAR(%s)", file.str(code.param));
        return buf;
    case DGMLB_OP_SET_VAR:
        sprintf(buf, "SET_VAR(%s)", file.str(code.param));
        return buf;
    case DGMLB_OP_NOT:
        return "NOT";
    case DGMLB_OP_ADD:
        return "ADD";
    case DGMLB_OP_SUB:
        return "SUB";
    case DGMLB_OP_MUL:
        return "MUL";
    case DGMLB_OP_DIV:
        return "DIV";
    case DGMLB_OP_OR:
        return "OR";
    case DGMLB_OP_AND:
        return "AND";
    case DGMLB_OP_LT:
        return "LT";
    case DGMLB_OP_LE:
        return "LE";
    case DGMLB_OP_GT:
        return "GT";
    case DGMLB_OP_GE:
        return "GE";
    case DGMLB_OP_EQ:
        return "EQ";
    case DGMLB_OP_NE:
        return "NE";
    default:
        return "INVALID";
    }
}

const char* code(File file, dgmlb_span code)
{
    static std::string out;
    out.clear();
    out.append("{");
    bool first = true;
    for (const auto& bc : file.span<dgmlb_byte_code>(code)) {
        if (!first) {
            out.append(", ");
        }
        first = false;
        out.append(op(file, bc));
    }
    out.append("}");
    return out.c_str();
}

int main(int, char**)
{
    auto file = fopen("../examples/quest/quest.dgmlb", "rb");
    char magic[8] = {};
    fread(magic, 1, 8, file);
    if (memcmp(magic, "\0DGMLB01", 8)) {
        fprintf(stderr, "wrong magic");
        return 1;
    }
    uint32_t file_size = 0;
    fread(&file_size, 1, sizeof(file_size), file);
    fseek(file, 0, SEEK_SET);
    const auto data = new uint8_t[file_size];
    fread(data, 1, file_size, file);
    fclose(file);

    File dgmlb { data, file_size };

    const auto& header = *(const dgmlb_file_header*)data;
    printf("speakers:\n");
    for (const auto& speaker : dgmlb.span<dgmlb_stroff>(header.speaker_ids)) {
        printf("%s\n", dgmlb.str(speaker));
    }
    printf("\n");

    printf("vars:\n");
    for (const auto& var : dgmlb.span<dgmlb_env_var>(header.env_variables)) {
        switch (var.type) {
        case DGMLB_VAR_TYPE_BOOL:
            printf("%s: %s\n", dgmlb.str(var.name), var.default_value ? "true" : "false");
            break;
        case DGMLB_VAR_TYPE_INT:
            printf("%s: %d\n", dgmlb.str(var.name), std::bit_cast<int32_t>(var.default_value));
            break;
        case DGMLB_VAR_TYPE_FLOAT:
            printf("%s: %f\n", dgmlb.str(var.name), std::bit_cast<float>(var.default_value));
            break;
        case DGMLB_VAR_TYPE_STRING:
            printf("%s: %s\n", dgmlb.str(var.name), dgmlb.str(var.default_value));
            break;
        default:
            printf("Invalid var type\n");
            break;
        }
    }
    printf("\n");

    printf("markup:\n");
    for (const auto& var : dgmlb.span<dgmlb_markup>(header.env_markup)) {
        printf("%s: %s\n", dgmlb.str(var.key), dgmlb.str(var.value));
    }
    printf("\n");

    printf("sections:\n");
    for (const auto& section : dgmlb.span<dgmlb_section>(header.sections)) {
        printf("%s\n", dgmlb.str(section.name));
        for (const auto& node : dgmlb.span<dgmlb_node>(section.nodes)) {
            printf("node (%d) '%s'\n", node.type, dgmlb.str(node.id));
            if (node.tags.count) {
                printf("  tags: %s\n", join(dgmlb, node.tags));
            }
            switch (node.type) {
            case DGMLB_NODE_TYPE_CHOICE:
                printf("  options\n");
                for (const auto& opt : dgmlb.span<dgmlb_option>(node.choice_options)) {
                    printf("  %s -> %u\n", text(dgmlb, opt.text), opt.dest);
                }
                break;
            case DGMLB_NODE_TYPE_GOTO:
                printf("  goto %u\n", node.next_node);
                break;
            case DGMLB_NODE_TYPE_IF:
                printf("  if %s: %u else %u\n", code(dgmlb, node.code), node.if_true_dest,
                    node.if_false_dest);
                break;
            case DGMLB_NODE_TYPE_RAND:
                break;
            case DGMLB_NODE_TYPE_RUN:
                printf("  run %s -> %u\n", code(dgmlb, node.code), node.next_node);
                break;
            case DGMLB_NODE_TYPE_SAY:
                printf("  say %s: %s -> %u\n", dgmlb.str(node.say_speaker_id),
                    text(dgmlb, node.text), node.next_node);
                break;
            }
        }
    }
    printf("\n");

    return 0;
}