#ifndef TOMAGI_H
#define TOMAGI_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

#define TOMAGI_VERSION_MAJOR 1u
#define TOMAGI_VERSION_MINOR 0u
#define TOMAGI_HEADER_SIZE 128u
#define TOMAGI_CELL_SIZE 48u
#define TOMAGI_STATE_SIZE 64u

#define TOMAGI_RHO_BITS 20u
#define TOMAGI_THETA_BITS 18u
#define TOMAGI_TIME_BITS 14u
#define TOMAGI_PHI_BITS 12u
#define TOMAGI_RHO_STATES (1u << TOMAGI_RHO_BITS)
#define TOMAGI_THETA_STATES (1u << TOMAGI_THETA_BITS)
#define TOMAGI_TIME_STATES (1u << TOMAGI_TIME_BITS)
#define TOMAGI_PHI_STATES (1u << TOMAGI_PHI_BITS)

#define TOMAGI_STATUS_HALT (1u << 0)
#define TOMAGI_STATUS_ZERO (1u << 1)
#define TOMAGI_STATUS_WRAP (1u << 2)
#define TOMAGI_STATUS_EMIT (1u << 3)
#define TOMAGI_STATUS_CONE (1u << 4)
#define TOMAGI_STATUS_SPHERE (1u << 5)
#define TOMAGI_STATUS_REKEY_MISS (1u << 6)
#define TOMAGI_STATUS_PHI_WRAP (1u << 7)

#define TOMAGI_PROGRAM_FLAG_SEEDED_PROFILE (1u << 0)
#define TOMAGI_PROGRAM_FLAG_EMIT_BYTES (1u << 1)

#define TOMAGI_FLAG_REKEY (1u << 31)
#define TOMAGI_FLAG_EMIT_HALT (1u << 0)
#define TOMAGI_FLAG_EMIT_COUNT_SHIFT 8u
#define TOMAGI_FLAG_EMIT_COUNT_MASK (0x7u << TOMAGI_FLAG_EMIT_COUNT_SHIFT)
#define TOMAGI_FLAG_EMIT_BIG_ENDIAN (1u << 11)
#define TOMAGI_FLAG_PHI_FLIP_ORIENTATION (1u << 4)
#define TOMAGI_FLAG_PHI_BRANCH_HALF (1u << 5)
#define TOMAGI_FLAG_KLEIN_SOURCE_HALF_TURN (1u << 0)
#define TOMAGI_FLAG_KLEIN_FLIP_SHEET (1u << 1)
#define TOMAGI_FLAG_HINGE_FLIP_ORIENTATION (1u << 0)
#define TOMAGI_FLAG_HINGE_FLIP_SHEET (1u << 1)

typedef enum TomagiOpcode {
    TOMAGI_OP_NOP = 0,
    TOMAGI_OP_SET = 1,
    TOMAGI_OP_JIT1 = 2,
    TOMAGI_OP_KIN2 = 3,
    TOMAGI_OP_PHI = 4,
    TOMAGI_OP_TIME = 5,
    TOMAGI_OP_SDF0 = 6,
    TOMAGI_OP_CONE = 7,
    TOMAGI_OP_SPHERE = 8,
    TOMAGI_OP_KLEIN = 9,
    TOMAGI_OP_RADIX = 10,
    TOMAGI_OP_HINGE = 11,
    TOMAGI_OP_LSYS = 12,
    TOMAGI_OP_PROJECT = 13,
    TOMAGI_OP_EMIT = 14,
    TOMAGI_OP_HALT = 15
} TomagiOpcode;

typedef struct TomagiState {
    int32_t rho;
    int32_t theta;
    int32_t tick;
    int32_t phi;
    int32_t vrho;
    int32_t vtheta;
    int32_t vtick;
    int32_t vphi;
    uint32_t orientation;
    uint32_t sheet;
    uint32_t branch;
    uint32_t cell;
    uint32_t lineage;
    uint32_t output;
    int32_t residual;
    uint32_t status;
} TomagiState;

typedef struct TomagiCell {
    uint32_t key_hi;
    uint32_t key_lo;
    uint32_t opcode;
    uint32_t flags;
    int32_t arg0;
    int32_t arg1;
    int32_t arg2;
    int32_t arg3;
    uint32_t next0;
    uint32_t next1;
    uint32_t payload;
    uint32_t aux;
} TomagiCell;

typedef struct TomagiProgram {
    uint32_t flags;
    uint32_t cell_count;
    uint32_t entry;
    uint32_t seed;
    uint32_t default_ticks;
    TomagiState initial_state;
    TomagiCell *cells;
} TomagiProgram;

uint32_t tomagi_mix32(uint32_t x);
void tomagi_pack_key_contiguous(const TomagiState *state, uint32_t *hi, uint32_t *lo);
void tomagi_unpack_key_contiguous(uint32_t hi, uint32_t lo,
                                  uint32_t *rho, uint32_t *theta,
                                  uint32_t *tick, uint32_t *phi);
int tomagi_find_key(const TomagiProgram *program, uint32_t hi, uint32_t lo, uint32_t *index_out);
int tomagi_step(const TomagiProgram *program, TomagiState *state);
int tomagi_run(const TomagiProgram *program, TomagiState *state, uint32_t ticks);
int tomagi_load_file(const char *path, TomagiProgram *program, char *error, size_t error_size);
void tomagi_free_program(TomagiProgram *program);
void tomagi_print_state_json(FILE *stream, const TomagiState *state);
const char *tomagi_opcode_name(uint32_t opcode);

#ifdef __cplusplus
}
#endif

#endif
