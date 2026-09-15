#include "tomagi.h"

#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>

static const unsigned char TOMAGI_MAGIC[8] = {'T','O','M','A','G','I','1','\0'};

static uint32_t read_le32(const unsigned char *p) {
    return ((uint32_t)p[0]) |
           ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static int32_t i32_from_u32(uint32_t x) {
    if (x <= 0x7fffffffu) {
        return (int32_t)x;
    }
    return -1 - (int32_t)(0xffffffffu - x);
}

static int32_t wrap32_i64(int64_t x) {
    return i32_from_u32((uint32_t)(uint64_t)x);
}

static int32_t i32_add(int32_t a, int32_t b) {
    return wrap32_i64((int64_t)a + (int64_t)b);
}

static int32_t norm_i64(int64_t x, int32_t modulus) {
    int64_t r = x % (int64_t)modulus;
    if (r < 0) r += modulus;
    return (int32_t)r;
}

static int32_t norm_i32(int32_t x, int32_t modulus) {
    return norm_i64((int64_t)x, modulus);
}

static int64_t floor_div_i64(int64_t x, int32_t positive_divisor) {
    int64_t q = x / (int64_t)positive_divisor;
    int64_t r = x % (int64_t)positive_divisor;
    if (r < 0) --q;
    return q;
}

static int32_t cyclic_delta_i32(int32_t value, int32_t center, int32_t modulus) {
    int32_t d = norm_i64((int64_t)value - (int64_t)center, modulus);
    if (d >= modulus / 2) d -= modulus;
    return d;
}

static int64_t abs_i32_wide(int32_t value) {
    return value < 0 ? -(int64_t)value : (int64_t)value;
}

static uint32_t rotl32(uint32_t x, uint32_t r) {
    r &= 31u;
    return (x << r) | (x >> ((32u - r) & 31u));
}

static uint32_t popcount32(uint32_t x) {
    x = x - ((x >> 1) & 0x55555555u);
    x = (x & 0x33333333u) + ((x >> 2) & 0x33333333u);
    x = (x + (x >> 4)) & 0x0f0f0f0fu;
    x = x + (x >> 8);
    x = x + (x >> 16);
    return x & 0x3fu;
}

uint32_t tomagi_mix32(uint32_t x) {
    x ^= x >> 16;
    x *= 0x7feb352du;
    x ^= x >> 15;
    x *= 0x846ca68bu;
    x ^= x >> 16;
    return x;
}

void tomagi_pack_key_contiguous(const TomagiState *state, uint32_t *hi, uint32_t *lo) {
    uint32_t rho = (uint32_t)norm_i32(state->rho, (int32_t)TOMAGI_RHO_STATES);
    uint32_t theta = (uint32_t)norm_i32(state->theta, (int32_t)TOMAGI_THETA_STATES);
    uint32_t tick = (uint32_t)norm_i32(state->tick, (int32_t)TOMAGI_TIME_STATES);
    uint32_t phi = (uint32_t)norm_i32(state->phi, (int32_t)TOMAGI_PHI_STATES);
    *hi = (rho << 12) | (theta >> 6);
    *lo = ((theta & 0x3fu) << 26) | (tick << 12) | phi;
}

void tomagi_unpack_key_contiguous(uint32_t hi, uint32_t lo,
                                  uint32_t *rho, uint32_t *theta,
                                  uint32_t *tick, uint32_t *phi) {
    *rho = (hi >> 12) & ((1u << TOMAGI_RHO_BITS) - 1u);
    *theta = ((hi & 0xfffu) << 6) | ((lo >> 26) & 0x3fu);
    *tick = (lo >> 12) & ((1u << TOMAGI_TIME_BITS) - 1u);
    *phi = lo & ((1u << TOMAGI_PHI_BITS) - 1u);
}

static int compare_key(uint32_t a_hi, uint32_t a_lo, uint32_t b_hi, uint32_t b_lo) {
    if (a_hi < b_hi) return -1;
    if (a_hi > b_hi) return 1;
    if (a_lo < b_lo) return -1;
    if (a_lo > b_lo) return 1;
    return 0;
}

int tomagi_find_key(const TomagiProgram *program, uint32_t hi, uint32_t lo, uint32_t *index_out) {
    uint32_t left = 0u;
    uint32_t right = program->cell_count;
    while (left < right) {
        uint32_t mid = left + (right - left) / 2u;
        const TomagiCell *cell = &program->cells[mid];
        int cmp = compare_key(cell->key_hi, cell->key_lo, hi, lo);
        if (cmp < 0) left = mid + 1u;
        else right = mid;
    }
    if (left < program->cell_count &&
        compare_key(program->cells[left].key_hi, program->cells[left].key_lo, hi, lo) == 0) {
        *index_out = left;
        return 1;
    }
    return 0;
}

static void normalize_periodic(TomagiState *s) {
    s->theta = norm_i32(s->theta, (int32_t)TOMAGI_THETA_STATES);
    s->tick = norm_i32(s->tick, (int32_t)TOMAGI_TIME_STATES);
    s->phi = norm_i32(s->phi, (int32_t)TOMAGI_PHI_STATES);
    s->orientation &= 1u;
    s->branch &= 1u;
}

static int set_field(TomagiState *s, uint32_t index, int32_t value, int add) {
#define SET_S(name) do { s->name = add ? i32_add(s->name, value) : value; } while (0)
#define SET_U(name) do { s->name = add ? (s->name + (uint32_t)value) : (uint32_t)value; } while (0)
    switch (index) {
        case 0: SET_S(rho); break;
        case 1: SET_S(theta); break;
        case 2: SET_S(tick); break;
        case 3: SET_S(phi); break;
        case 4: SET_S(vrho); break;
        case 5: SET_S(vtheta); break;
        case 6: SET_S(vtick); break;
        case 7: SET_S(vphi); break;
        case 8: SET_U(orientation); break;
        case 9: SET_U(sheet); break;
        case 10: SET_U(branch); break;
        case 11: SET_U(cell); break;
        case 12: SET_U(lineage); break;
        case 13: SET_U(output); break;
        case 14: SET_S(residual); break;
        case 15: SET_U(status); break;
        default: return 0;
    }
#undef SET_S
#undef SET_U
    return 1;
}

static void apply_klein(TomagiState *s, uint32_t flags) {
    int64_t wraps = floor_div_i64((int64_t)s->rho, (int32_t)TOMAGI_RHO_STATES);
    s->rho = (int32_t)((int64_t)s->rho - wraps * (int64_t)TOMAGI_RHO_STATES);
    uint32_t odd = (uint32_t)wraps & 1u;
    if (odd) {
        if (flags & TOMAGI_FLAG_KLEIN_SOURCE_HALF_TURN) {
            s->theta = norm_i64((int64_t)s->theta + (int64_t)(TOMAGI_THETA_STATES / 2u),
                                (int32_t)TOMAGI_THETA_STATES);
        } else {
            s->theta = norm_i64((int64_t)(TOMAGI_THETA_STATES / 2u) - (int64_t)s->theta,
                                (int32_t)TOMAGI_THETA_STATES);
        }
        s->phi = norm_i64(-(int64_t)s->phi, (int32_t)TOMAGI_PHI_STATES);
        s->orientation ^= 1u;
        if (flags & TOMAGI_FLAG_KLEIN_FLIP_SHEET) s->sheet ^= 1u;
        s->status |= TOMAGI_STATUS_WRAP;
    } else {
        s->status &= ~TOMAGI_STATUS_WRAP;
    }
    s->branch = odd;
    normalize_periodic(s);
}

static int32_t cone_residual(const TomagiState *s, const TomagiCell *c) {
    int32_t rho = norm_i32(s->rho, (int32_t)TOMAGI_RHO_STATES);
    int32_t theta = norm_i32(s->theta, (int32_t)TOMAGI_THETA_STATES);
    int32_t center = norm_i32(c->arg2, (int32_t)TOMAGI_THETA_STATES);
    int64_t half = abs_i32_wide(c->arg3);
    int64_t a = (int64_t)c->arg0 - (int64_t)rho;
    int64_t b = (int64_t)rho - (int64_t)c->arg1;
    int64_t radial = a > b ? a : b;
    int32_t delta32 = cyclic_delta_i32(theta, center, (int32_t)TOMAGI_THETA_STATES);
    int64_t delta = delta32 < 0 ? -(int64_t)delta32 : (int64_t)delta32;
    int64_t angular = delta - half;
    return wrap32_i64(radial > angular ? radial : angular);
}

static int32_t sphere_residual(const TomagiState *s, const TomagiCell *c) {
    int32_t rho = norm_i32(s->rho, (int32_t)TOMAGI_RHO_STATES);
    int32_t phi = norm_i32(s->phi, (int32_t)TOMAGI_PHI_STATES);
    int64_t radial = (int64_t)rho - (int64_t)c->arg0;
    if (radial < 0) radial = -radial;
    radial -= abs_i32_wide(c->arg1);
    if (c->arg3 < 0) return wrap32_i64(radial);
    int32_t delta32 = cyclic_delta_i32(phi, norm_i32(c->arg2, (int32_t)TOMAGI_PHI_STATES),
                                       (int32_t)TOMAGI_PHI_STATES);
    int64_t delta = delta32 < 0 ? -(int64_t)delta32 : (int64_t)delta32;
    int64_t angular = delta - abs_i32_wide(c->arg3);
    return wrap32_i64(radial > angular ? radial : angular);
}

int tomagi_step(const TomagiProgram *program, TomagiState *s) {
    if (s->status & TOMAGI_STATUS_HALT) return 1;
    if (s->cell >= program->cell_count) return 0;

    uint32_t cell_index = s->cell;
    const TomagiCell *c = &program->cells[cell_index];
    uint32_t key_hi, key_lo;
    tomagi_pack_key_contiguous(s, &key_hi, &key_lo);

    switch (c->opcode) {
        case TOMAGI_OP_NOP:
            break;
        case TOMAGI_OP_SET:
            if (!set_field(s, c->flags & 0xfu, c->arg0, 0)) return 0;
            break;
        case TOMAGI_OP_JIT1: {
            uint32_t h = tomagi_mix32(program->seed ^ key_hi ^ rotl32(key_lo, 13u) ^
                                      (uint32_t)s->tick ^ c->aux);
            uint32_t bit = popcount32(h) & 1u;
            s->branch = bit;
            int32_t delta = bit ? c->arg0 : wrap32_i64(-(int64_t)c->arg0);
            if (!set_field(s, c->flags & 0xfu, delta, 1)) return 0;
            break;
        }
        case TOMAGI_OP_KIN2:
            s->vrho = i32_add(s->vrho, c->arg0);
            s->vtheta = i32_add(s->vtheta, c->arg1);
            s->vtick = i32_add(s->vtick, c->arg2);
            s->vphi = i32_add(s->vphi, c->arg3);
            s->rho = i32_add(s->rho, s->vrho);
            s->theta = i32_add(s->theta, s->vtheta);
            s->tick = i32_add(s->tick, s->vtick);
            s->phi = i32_add(s->phi, s->vphi);
            break;
        case TOMAGI_OP_PHI: {
            int64_t raw = (int64_t)s->phi + (int64_t)c->arg0;
            int64_t wraps = floor_div_i64(raw, (int32_t)TOMAGI_PHI_STATES);
            s->phi = (int32_t)(raw - wraps * (int64_t)TOMAGI_PHI_STATES);
            if (((uint32_t)wraps & 1u) && (c->flags & TOMAGI_FLAG_PHI_FLIP_ORIENTATION))
                s->orientation ^= 1u;
            if (wraps) s->status |= TOMAGI_STATUS_PHI_WRAP;
            else s->status &= ~TOMAGI_STATUS_PHI_WRAP;
            s->branch = (c->flags & TOMAGI_FLAG_PHI_BRANCH_HALF)
                ? (((uint32_t)s->phi >> (TOMAGI_PHI_BITS - 1u)) & 1u)
                : ((uint32_t)wraps & 1u);
            break;
        }
        case TOMAGI_OP_TIME: {
            int64_t raw = (int64_t)s->tick + (int64_t)c->arg0;
            int64_t wraps = floor_div_i64(raw, (int32_t)TOMAGI_TIME_STATES);
            s->tick = (int32_t)(raw - wraps * (int64_t)TOMAGI_TIME_STATES);
            s->branch = (uint32_t)wraps & 1u;
            if (wraps) s->lineage = tomagi_mix32(s->lineage ^ (uint32_t)wraps ^ c->aux);
            break;
        }
        case TOMAGI_OP_SDF0:
            s->residual = 0;
            s->status |= TOMAGI_STATUS_ZERO;
            s->branch = 1u;
            break;
        case TOMAGI_OP_CONE: {
            s->residual = cone_residual(s, c);
            uint32_t inside = s->residual <= 0 ? 1u : 0u;
            s->branch = inside;
            if (inside) s->status |= TOMAGI_STATUS_CONE;
            else s->status &= ~TOMAGI_STATUS_CONE;
            break;
        }
        case TOMAGI_OP_SPHERE: {
            s->residual = sphere_residual(s, c);
            uint32_t inside = s->residual <= 0 ? 1u : 0u;
            s->branch = inside;
            if (inside) s->status |= TOMAGI_STATUS_SPHERE;
            else s->status &= ~TOMAGI_STATUS_SPHERE;
            break;
        }
        case TOMAGI_OP_KLEIN:
            apply_klein(s, c->flags);
            break;
        case TOMAGI_OP_RADIX: {
            if (c->arg0 < 0 || c->arg0 >= 64) return 0;
            uint32_t bit_index = (uint32_t)c->arg0;
            s->branch = bit_index < 32u
                ? ((key_lo >> bit_index) & 1u)
                : ((key_hi >> (bit_index - 32u)) & 1u);
            break;
        }
        case TOMAGI_OP_HINGE:
            if (s->branch & 1u) {
                s->rho = i32_add(s->rho, c->arg0);
                s->theta = i32_add(s->theta, c->arg1);
                s->tick = i32_add(s->tick, c->arg2);
                s->phi = i32_add(s->phi, c->arg3);
                if (c->flags & TOMAGI_FLAG_HINGE_FLIP_ORIENTATION) s->orientation ^= 1u;
                if (c->flags & TOMAGI_FLAG_HINGE_FLIP_SHEET) s->sheet ^= 1u;
                normalize_periodic(s);
            }
            break;
        case TOMAGI_OP_LSYS: {
            int32_t shift = c->arg1;
            if (shift < 0) shift = 0;
            if (shift > 30) shift = 30;
            int32_t divisor = (int32_t)(1u << (uint32_t)shift);
            int32_t chirality = (s->orientation & 1u) ? -1 : 1;
            int32_t turn_sign = (s->branch & 1u) ? 1 : -1;
            s->phi = norm_i64((int64_t)s->phi + (int64_t)chirality *
                              (int64_t)turn_sign * (int64_t)c->arg0,
                              (int32_t)TOMAGI_PHI_STATES);
            s->vrho /= divisor;
            s->vtheta /= divisor;
            s->vtick /= divisor;
            s->vphi /= divisor;
            break;
        }
        case TOMAGI_OP_PROJECT:
            s->output = c->payload;
            break;
        case TOMAGI_OP_EMIT:
            s->output = c->payload;
            s->status |= TOMAGI_STATUS_EMIT;
            if (c->flags & TOMAGI_FLAG_EMIT_HALT) s->status |= TOMAGI_STATUS_HALT;
            break;
        case TOMAGI_OP_HALT:
            s->status |= TOMAGI_STATUS_HALT;
            break;
        default:
            return 0;
    }

    normalize_periodic(s);
    s->lineage = tomagi_mix32(s->lineage ^ c->payload ^ c->aux ^ key_hi ^
                              rotl32(key_lo, 7u) ^ s->branch ^ cell_index);

    if (!(s->status & TOMAGI_STATUS_HALT)) {
        if (c->flags & TOMAGI_FLAG_REKEY) {
            uint32_t new_hi, new_lo, found;
            tomagi_pack_key_contiguous(s, &new_hi, &new_lo);
            if (tomagi_find_key(program, new_hi, new_lo, &found)) {
                s->status &= ~TOMAGI_STATUS_REKEY_MISS;
                s->cell = found;
            } else {
                s->status |= TOMAGI_STATUS_REKEY_MISS;
                s->cell = (s->branch & 1u) ? c->next1 : c->next0;
            }
        } else {
            s->cell = (s->branch & 1u) ? c->next1 : c->next0;
        }
    }
    return 1;
}

int tomagi_run(const TomagiProgram *program, TomagiState *state, uint32_t ticks) {
    uint32_t i;
    for (i = 0; i < ticks && !(state->status & TOMAGI_STATUS_HALT); ++i) {
        if (!tomagi_step(program, state)) return 0;
    }
    return 1;
}

static void set_error(char *error, size_t error_size, const char *message) {
    if (error && error_size) {
        snprintf(error, error_size, "%s", message);
    }
}

int tomagi_load_file(const char *path, TomagiProgram *p, char *error, size_t error_size) {
    FILE *f = NULL;
    unsigned char *data = NULL;
    long size_long;
    size_t size;
    uint32_t i;
    memset(p, 0, sizeof(*p));

    f = fopen(path, "rb");
    if (!f) {
        set_error(error, error_size, strerror(errno));
        return 0;
    }
    if (fseek(f, 0, SEEK_END) != 0 || (size_long = ftell(f)) < 0 || fseek(f, 0, SEEK_SET) != 0) {
        set_error(error, error_size, "cannot determine file size");
        fclose(f);
        return 0;
    }
    size = (size_t)size_long;
    data = (unsigned char *)malloc(size ? size : 1u);
    if (!data) {
        set_error(error, error_size, "out of memory");
        fclose(f);
        return 0;
    }
    if (fread(data, 1, size, f) != size) {
        set_error(error, error_size, "cannot read file");
        free(data);
        fclose(f);
        return 0;
    }
    fclose(f);

    if (size < TOMAGI_HEADER_SIZE || memcmp(data, TOMAGI_MAGIC, 8) != 0) {
        set_error(error, error_size, "not a TOMAGI 1.0 program");
        free(data);
        return 0;
    }
    uint32_t version = read_le32(data + 8);
    p->flags = read_le32(data + 12);
    p->cell_count = read_le32(data + 16);
    p->entry = read_le32(data + 20);
    p->seed = read_le32(data + 24);
    p->default_ticks = read_le32(data + 28);
    uint32_t cell_size = read_le32(data + 32);
    uint32_t state_size = read_le32(data + 36);
    for (i = 0; i < 6u; ++i) {
        if (read_le32(data + 40u + 4u * i) != 0u) {
            set_error(error, error_size, "reserved TOMAGI header words must be zero");
            free(data);
            return 0;
        }
    }
    if (version != 0x00010000u || cell_size != TOMAGI_CELL_SIZE || state_size != TOMAGI_STATE_SIZE) {
        set_error(error, error_size, "unsupported TOMAGI record version or size");
        free(data);
        return 0;
    }
    if (size != (size_t)TOMAGI_HEADER_SIZE + (size_t)p->cell_count * TOMAGI_CELL_SIZE) {
        set_error(error, error_size, "file length does not match cell count");
        free(data);
        return 0;
    }
    if (!p->cell_count || p->entry >= p->cell_count) {
        set_error(error, error_size, "invalid entry or empty cell table");
        free(data);
        return 0;
    }

    const unsigned char *s = data + 64;
    p->initial_state.rho = i32_from_u32(read_le32(s + 0));
    p->initial_state.theta = i32_from_u32(read_le32(s + 4));
    p->initial_state.tick = i32_from_u32(read_le32(s + 8));
    p->initial_state.phi = i32_from_u32(read_le32(s + 12));
    p->initial_state.vrho = i32_from_u32(read_le32(s + 16));
    p->initial_state.vtheta = i32_from_u32(read_le32(s + 20));
    p->initial_state.vtick = i32_from_u32(read_le32(s + 24));
    p->initial_state.vphi = i32_from_u32(read_le32(s + 28));
    p->initial_state.orientation = read_le32(s + 32);
    p->initial_state.sheet = read_le32(s + 36);
    p->initial_state.branch = read_le32(s + 40);
    p->initial_state.cell = read_le32(s + 44);
    p->initial_state.lineage = read_le32(s + 48);
    p->initial_state.output = read_le32(s + 52);
    p->initial_state.residual = i32_from_u32(read_le32(s + 56));
    p->initial_state.status = read_le32(s + 60);

    p->cells = (TomagiCell *)calloc(p->cell_count, sizeof(TomagiCell));
    if (!p->cells) {
        set_error(error, error_size, "out of memory");
        free(data);
        return 0;
    }
    const unsigned char *cdata = data + TOMAGI_HEADER_SIZE;
    for (i = 0; i < p->cell_count; ++i) {
        const unsigned char *c = cdata + (size_t)i * TOMAGI_CELL_SIZE;
        TomagiCell *dst = &p->cells[i];
        dst->key_hi = read_le32(c + 0);
        dst->key_lo = read_le32(c + 4);
        dst->opcode = read_le32(c + 8);
        dst->flags = read_le32(c + 12);
        dst->arg0 = i32_from_u32(read_le32(c + 16));
        dst->arg1 = i32_from_u32(read_le32(c + 20));
        dst->arg2 = i32_from_u32(read_le32(c + 24));
        dst->arg3 = i32_from_u32(read_le32(c + 28));
        dst->next0 = read_le32(c + 32);
        dst->next1 = read_le32(c + 36);
        dst->payload = read_le32(c + 40);
        dst->aux = read_le32(c + 44);
        if (dst->opcode > TOMAGI_OP_HALT || dst->next0 >= p->cell_count || dst->next1 >= p->cell_count) {
            set_error(error, error_size, "invalid cell opcode or successor");
            free(data);
            tomagi_free_program(p);
            return 0;
        }
        if (i > 0 && compare_key(p->cells[i-1].key_hi, p->cells[i-1].key_lo,
                                 dst->key_hi, dst->key_lo) >= 0) {
            set_error(error, error_size, "cell keys are not strictly sorted");
            free(data);
            tomagi_free_program(p);
            return 0;
        }
    }
    free(data);
    return 1;
}

void tomagi_free_program(TomagiProgram *p) {
    free(p->cells);
    memset(p, 0, sizeof(*p));
}

const char *tomagi_opcode_name(uint32_t opcode) {
    static const char *names[] = {
        "NOP", "SET", "JIT1", "KIN2", "PHI", "TIME", "SDF0", "CONE",
        "SPHERE", "KLEIN", "RADIX", "HINGE", "LSYS", "PROJECT", "EMIT", "HALT"
    };
    return opcode < 16u ? names[opcode] : "UNKNOWN";
}

void tomagi_print_state_json(FILE *stream, const TomagiState *s) {
    fprintf(stream,
        "{\n"
        "  \"rho\": %" PRId32 ",\n"
        "  \"theta\": %" PRId32 ",\n"
        "  \"tick\": %" PRId32 ",\n"
        "  \"phi\": %" PRId32 ",\n"
        "  \"vrho\": %" PRId32 ",\n"
        "  \"vtheta\": %" PRId32 ",\n"
        "  \"vtick\": %" PRId32 ",\n"
        "  \"vphi\": %" PRId32 ",\n"
        "  \"orientation\": %" PRIu32 ",\n"
        "  \"sheet\": %" PRIu32 ",\n"
        "  \"branch\": %" PRIu32 ",\n"
        "  \"cell\": %" PRIu32 ",\n"
        "  \"lineage\": %" PRIu32 ",\n"
        "  \"output\": %" PRIu32 ",\n"
        "  \"residual\": %" PRId32 ",\n"
        "  \"status\": %" PRIu32 "\n"
        "}\n",
        s->rho, s->theta, s->tick, s->phi,
        s->vrho, s->vtheta, s->vtick, s->vphi,
        s->orientation, s->sheet, s->branch, s->cell,
        s->lineage, s->output, s->residual, s->status);
}
