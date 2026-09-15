#include "tomagi.h"

#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void usage(const char *name) {
    fprintf(stderr, "usage: %s PROGRAM.tmg [ticks] [--trace] [--trace-json]\n", name);
}

static void print_trace_record_json(
    FILE *stream,
    uint32_t step,
    uint32_t before,
    const TomagiCell *cell,
    const TomagiState *state
) {
    uint32_t key_hi, key_lo;
    tomagi_pack_key_contiguous(state, &key_hi, &key_lo);
    fprintf(stream,
        "{"
        "\"step\":%" PRIu32 ","
        "\"cell_before\":%" PRIu32 ","
        "\"opcode\":%" PRIu32 ","
        "\"branch\":%" PRIu32 ","
        "\"cell_after\":%" PRIu32 ","
        "\"key_hi\":%" PRIu32 ","
        "\"key_lo\":%" PRIu32 ","
        "\"rho\":%" PRId32 ","
        "\"theta\":%" PRId32 ","
        "\"tick\":%" PRId32 ","
        "\"phi\":%" PRId32 ","
        "\"orientation\":%" PRIu32 ","
        "\"sheet\":%" PRIu32 ","
        "\"residual\":%" PRId32 ","
        "\"output\":%" PRIu32 ","
        "\"lineage\":%" PRIu32 ","
        "\"status\":%" PRIu32
        "}",
        step, before, cell->opcode, state->branch, state->cell,
        key_hi, key_lo, state->rho, state->theta, state->tick, state->phi,
        state->orientation, state->sheet, state->residual, state->output,
        state->lineage, state->status
    );
}

int main(int argc, char **argv) {
    TomagiProgram program;
    TomagiState state;
    char error[256];
    uint32_t ticks;
    int trace = 0;
    int trace_json = 0;
    int ticks_seen = 0;
    uint32_t i;
    int argi;

    if (argc < 2 || argc > 5) {
        usage(argv[0]);
        return 2;
    }
    if (!tomagi_load_file(argv[1], &program, error, sizeof(error))) {
        fprintf(stderr, "tomagi: %s\n", error);
        return 1;
    }
    ticks = program.default_ticks;
    for (argi = 2; argi < argc; ++argi) {
        if (strcmp(argv[argi], "--trace") == 0) {
            trace = 1;
        } else if (strcmp(argv[argi], "--trace-json") == 0) {
            trace_json = 1;
        } else if (!ticks_seen) {
            char *end = NULL;
            errno = 0;
            unsigned long value = strtoul(argv[argi], &end, 0);
            if (errno || !end || *end || value > 0xfffffffful) {
                fprintf(stderr, "tomagi: invalid tick count\n");
                tomagi_free_program(&program);
                return 2;
            }
            ticks = (uint32_t)value;
            ticks_seen = 1;
        } else {
            usage(argv[0]);
            tomagi_free_program(&program);
            return 2;
        }
    }

    state = program.initial_state;
    state.cell = program.entry;
    if (trace_json) {
        fputs("{\n  \"trace\": [", stdout);
    }
    for (i = 0; i < ticks && !(state.status & TOMAGI_STATUS_HALT); ++i) {
        uint32_t before = state.cell;
        const TomagiCell *cell = &program.cells[before];
        if (!tomagi_step(&program, &state)) {
            fprintf(stderr, "tomagi: execution error at step %u cell %u\n", i, before);
            tomagi_free_program(&program);
            return 1;
        }
        if (trace) {
            fprintf(stderr, "step=%u cell=%u op=%s branch=%u next=%u output=%u lineage=%u status=%u\n",
                    i, before, tomagi_opcode_name(cell->opcode), state.branch,
                    state.cell, state.output, state.lineage, state.status);
        }
        if (trace_json) {
            if (i) fputc(',', stdout);
            fputs("\n    ", stdout);
            print_trace_record_json(stdout, i, before, cell, &state);
        }
    }
    if (trace_json) {
        fputs("\n  ],\n  \"state\": ", stdout);
        tomagi_print_state_json(stdout, &state);
        fputs("}\n", stdout);
    } else {
        tomagi_print_state_json(stdout, &state);
    }
    tomagi_free_program(&program);
    return 0;
}
