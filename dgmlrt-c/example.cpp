#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string_view>

#include "dgmlrt.h"

static const char* RESET = "\033[0m";
static const char* BOLD = "\033[1m";
static const char* FAINT = "\033[2m";
static const char* MAGENTA = "\033[35m";

void render_text(const dgmlrt_text_fragment* frags, size_t num)
{
    for (size_t f = 0; f < num; ++f) {
        for (size_t m = 0; m < frags[f].num_markup; ++m) {
            if (strcmp(frags[f].markup[m].name.data, "bold") == 0) {
                fputs(BOLD, stdout);
            } else if (strcmp(frags[f].markup[m].name.data, "color") == 0) {
                if (strcmp(frags[f].markup[m].value.data, "magenta") == 0) {
                    fputs(MAGENTA, stdout);
                }
            }
        }
        fputs(frags[f].text.data, stdout);
        fputs(RESET, stdout);
    }
    fputs("\n", stdout);
}

int get_answer(const dgmlrt_option* options, size_t num_options)
{
    char buf[64];
    while (true) {
        fputs("Answer: ", stdout);
        fflush(stdout);

        if (!fgets(buf, sizeof(buf), stdin)) {
            puts("\nNo input. Aborting.");
            continue;
        }

        const auto num = strtol(buf, nullptr, 10);
        if (num == 0) {
            puts("Invalid input.");
            continue;
        }
        if (num < 1 || (size_t)num > num_options) {
            puts("Out of range.");
            continue;
        }
        if (!options[num - 1].enabled) {
            puts("Not a valid option.");
            continue;
        }
        return (int)num - 1;
    }
}

void read_env(dgmlrt_vm* vm, const char* path)
{
    auto file = fopen(path, "r");
    if (!file) {
        return; // do nothing
    }

    char buffer[256];
    // unsafe - happy path only
    while (fgets(buffer, sizeof(buffer), file)) {
        char name[128];
        char value[128];
        sscanf(buffer, "%s %s\n", name, value);
        const auto value_sv = std::string_view(value);

        auto vm_value = dgmlrt_vm_get_env_value(vm, dgmlrt_zstr(name));
        assert(vm_value.type != DGMLRT_ENV_VALUE_UNSET);
        switch (vm_value.type) {
        case DGMLRT_ENV_VALUE_BOOL:
            assert(value_sv == "true" || value_sv == "false");
            vm_value.b = value_sv == "true";
            break;
        case DGMLRT_ENV_VALUE_INT:
            vm_value.i = strtol(value, nullptr, 10);
            break;
        case DGMLRT_ENV_VALUE_FLOAT:
            vm_value.f = strtof(value, nullptr);
            break;
        case DGMLRT_ENV_VALUE_STRING:
            vm_value.s = { value_sv.data(), value_sv.size() };
            break;
        default:
            break;
        }
        dgmlrt_vm_set_env_value(vm, dgmlrt_zstr(name), vm_value);
    }

    fclose(file);
}

void save_env(dgmlrt_vm* vm, const char* path)
{
    auto file = fopen(path, "w");
    assert(file);

    dgmlrt_env_var vars[128];
    const auto n = dgmlrt_get_env_vars(vm, vars, std::size(vars));
    for (size_t i = 0; i < n; ++i) {
        switch (vars[i].value.type) {
        case DGMLRT_ENV_VALUE_BOOL:
            fprintf(file, "%s %s\n", vars[i].name.data, vars[i].value.b ? "true" : "false");
            break;
        case DGMLRT_ENV_VALUE_INT:
            fprintf(file, "%s %lu\n", vars[i].name.data, vars[i].value.i);
            break;
        case DGMLRT_ENV_VALUE_FLOAT:
            fprintf(file, "%s %f\n", vars[i].name.data, vars[i].value.f);
            break;
        case DGMLRT_ENV_VALUE_STRING:
            fprintf(file, "%s %s\n", vars[i].name.data, vars[i].value.s.data);
            break;
        default:
            break;
        }
    }

    fclose(file);
}

int main(int, char**)
{
    auto tree = dgmlrt_load_file("../examples/quest/quest.dgmlb", {});

    auto vm = dgmlrt_vm_create(tree, {}, {});

    dgmlrt_vm_enter(vm, "docking_bay", nullptr);

    read_env(vm, "env.txt");

    auto state = dgmlrt_vm_advance(vm, -1);
    while (true) {
        if (state.type == DGMLRT_RESULT_TYPE_SAY) {
            printf("%s: ", state.say.speaker_id.data);
            render_text(state.say.text_fragments, state.say.num_text_fragments);
            state = dgmlrt_vm_advance(vm, -1);
        } else if (state.type == DGMLRT_RESULT_TYPE_CHOICE) {
            for (size_t o = 0; o < state.choice.num_options; ++o) {
                if (state.choice.options[o].enabled) {
                    printf("%s%lu. ", RESET, o + 1);
                } else {
                    printf("%s%sX. ", RESET, FAINT);
                }
                render_text(state.choice.options[o].text_fragments,
                    state.choice.options[o].num_text_fragments);
            }

            const auto option_index = get_answer(state.choice.options, state.choice.num_options);
            state = dgmlrt_vm_advance(vm, option_index);
        } else if (state.type == DGMLRT_RESULT_TYPE_END) {
            puts("<< END >>");
            break;
        } else {
            printf("Error: %s\n", state.error.message);
            break;
        }
    }

    save_env(vm, "env.txt");

    dgmlrt_vm_free(vm);
    dgmlrt_free(tree);
}