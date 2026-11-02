
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

#define PA_CONTINUE 0
#define PA_INPUT_OVERFLOW 0x2

typedef struct {
    uint64_t written;
    uint64_t read;
    uint64_t overflows;
    uint32_t frame_bytes;
    size_t size;
    uint8_t data[];
} ExcitonRing;

static uint64_t load(const uint64_t *p) { return __atomic_load_n(p, __ATOMIC_ACQUIRE); }
static void store(uint64_t *p, uint64_t v) { __atomic_store_n(p, v, __ATOMIC_RELEASE); }

EXPORT ExcitonRing *exciton_ring_new(size_t size, uint32_t frame_bytes) {
    if (!size || !frame_bytes) return NULL;
    ExcitonRing *ring = calloc(1, sizeof(ExcitonRing) + size);
    if (!ring) return NULL;
    ring->size = size;
    ring->frame_bytes = frame_bytes;
    return ring;
}

EXPORT void exciton_ring_free(ExcitonRing *ring) { free(ring); }

EXPORT size_t exciton_ring_used(ExcitonRing *ring) { return (size_t)(load(&ring->written) - load(&ring->read)); }

EXPORT size_t exciton_ring_free_space(ExcitonRing *ring) { return ring->size - exciton_ring_used(ring); }

EXPORT uint64_t exciton_ring_overflows(ExcitonRing *ring) { return __atomic_load_n(&ring->overflows, __ATOMIC_RELAXED); }

EXPORT size_t exciton_ring_write(ExcitonRing *ring, const uint8_t *src, size_t n) {
    uint64_t written = ring->written;
    size_t space = ring->size - (size_t)(written - load(&ring->read));
    if (n > space) n = space;
    size_t at = (size_t)(written % ring->size);
    size_t first = n < ring->size - at ? n : ring->size - at;
    memcpy(ring->data + at, src, first);
    memcpy(ring->data, src + first, n - first);
    store(&ring->written, written + n);
    return n;
}

EXPORT size_t exciton_ring_read(ExcitonRing *ring, uint8_t *dst, size_t n) {
    uint64_t read = ring->read;
    size_t used = (size_t)(load(&ring->written) - read);
    if (n > used) n = used;
    size_t at = (size_t)(read % ring->size);
    size_t first = n < ring->size - at ? n : ring->size - at;
    memcpy(dst, ring->data + at, first);
    memcpy(dst + first, ring->data, n - first);
    store(&ring->read, read + n);
    return n;
}

EXPORT int exciton_audio_input(const void *input, void *output, unsigned long frames, const void *time_info,
                               unsigned long status, void *user_data) {
    (void)output;
    (void)time_info;
    (void)status;
    ExcitonRing *ring = user_data;
    if (!input) return PA_CONTINUE;
    size_t bytes = (size_t)frames * ring->frame_bytes;
    if (exciton_ring_write(ring, input, bytes) < bytes) __atomic_add_fetch(&ring->overflows, 1, __ATOMIC_RELAXED);
    return PA_CONTINUE;
}

EXPORT int exciton_audio_output(const void *input, void *output, unsigned long frames, const void *time_info,
                                unsigned long status, void *user_data) {
    (void)input;
    (void)time_info;
    (void)status;
    ExcitonRing *ring = user_data;
    if (!output) return PA_CONTINUE;
    size_t bytes = (size_t)frames * ring->frame_bytes;
    size_t got = exciton_ring_read(ring, output, bytes);
    if (got < bytes) memset((uint8_t *)output + got, 0, bytes - got);
    return PA_CONTINUE;
}
