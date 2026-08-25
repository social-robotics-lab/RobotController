#include <time.h>

#include <alsa/asoundlib.h>
#include <dlfcn.h>
#include <jni.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "utils_AlsaPcm.h"

#define ALSA_DEVICE_NAME "default"
#define ALSA_SAMPLE_RATE 24000U
#define ALSA_CHANNELS 1U
#define ALSA_FRAME_SIZE 2
#define ALSA_LATENCY_MICROS 100000U
#define MAX_RECOVERY_ATTEMPTS 3
#define LIBASOUND_GLOBAL_PATH "/usr/lib/libasound.so.2"
#define AUDIO_NATIVE_DIAGNOSTIC_PREFIX "[AUDIO_NATIVE_DIAG]"
#define SLOW_OPERATION_NANOS UINT64_C(40000000)
#define NANOS_PER_SECOND UINT64_C(1000000000)
#define NANOS_PER_MILLISECOND UINT64_C(1000000)

typedef struct AlsaPcmContext {
    snd_pcm_t *pcm;
    snd_pcm_uframes_t buffer_frames;
    snd_pcm_uframes_t period_frames;
} AlsaPcmContext;

static void *g_libasound_global;
static int g_libasound_attempted;
static char g_libasound_error[768];

typedef struct DiagnosticTimestamp {
    struct timespec value;
    int valid;
} DiagnosticTimestamp;

static DiagnosticTimestamp diagnostic_now(void) {
    DiagnosticTimestamp timestamp;
    timestamp.valid = clock_gettime(CLOCK_MONOTONIC, &timestamp.value) == 0;
    if (!timestamp.valid) {
        timestamp.value.tv_sec = (time_t) 0;
        timestamp.value.tv_nsec = 0L;
    }
    return timestamp;
}

static int diagnostic_elapsed_nanos(
        DiagnosticTimestamp start,
        DiagnosticTimestamp end,
        uint64_t *elapsed_nanos) {
    int64_t seconds;
    int64_t nanoseconds;
    if (!start.valid || !end.valid || elapsed_nanos == NULL) {
        return 0;
    }
    seconds = (int64_t) end.value.tv_sec - (int64_t) start.value.tv_sec;
    nanoseconds = (int64_t) end.value.tv_nsec - (int64_t) start.value.tv_nsec;
    if (nanoseconds < 0) {
        seconds--;
        nanoseconds += (int64_t) NANOS_PER_SECOND;
    }
    if (seconds < 0) {
        return 0;
    }
    *elapsed_nanos = ((uint64_t) seconds * NANOS_PER_SECOND)
            + (uint64_t) nanoseconds;
    return 1;
}

static double diagnostic_duration_ms(
        int duration_valid,
        uint64_t duration_nanos) {
    if (!duration_valid) {
        /* Best-effort timing failure is reported without changing audio flow. */
        return -1.0;
    }
    return (double) duration_nanos / (double) NANOS_PER_MILLISECOND;
}

static void log_writei_event(
        const char *event,
        unsigned int call_number,
        snd_pcm_uframes_t requested_frames,
        snd_pcm_sframes_t result,
        int duration_valid,
        uint64_t duration_nanos) {
    (void) fprintf(
            stderr,
            AUDIO_NATIVE_DIAGNOSTIC_PREFIX
            " %s call=%u requested_frames=%llu result=%lld duration_ms=%.3f\n",
            event,
            call_number,
            (unsigned long long) requested_frames,
            (long long) result,
            diagnostic_duration_ms(duration_valid, duration_nanos));
}

static void log_writei_error(
        unsigned int call_number,
        snd_pcm_uframes_t requested_frames,
        snd_pcm_sframes_t result,
        int duration_valid,
        uint64_t duration_nanos) {
    const char *description = snd_strerror((int) result);
    if (description == NULL) {
        description = "unknown ALSA error";
    }
    (void) fprintf(
            stderr,
            AUDIO_NATIVE_DIAGNOSTIC_PREFIX
            " WRITEI_ERROR call=%u requested_frames=%llu result=%lld"
            " error=\"%s\" duration_ms=%.3f\n",
            call_number,
            (unsigned long long) requested_frames,
            (long long) result,
            description,
            diagnostic_duration_ms(duration_valid, duration_nanos));
}

static void log_recover(
        unsigned int attempt,
        int input_error,
        int result,
        int duration_valid,
        uint64_t duration_nanos) {
    (void) fprintf(
            stderr,
            AUDIO_NATIVE_DIAGNOSTIC_PREFIX
            " RECOVER attempt=%u input_error=%d result=%d duration_ms=%.3f\n",
            attempt,
            input_error,
            result,
            diagnostic_duration_ms(duration_valid, duration_nanos));
}

static void log_write_summary(
        jint bytes,
        snd_pcm_uframes_t frames,
        DiagnosticTimestamp invocation_start,
        unsigned int writei_calls,
        unsigned int recover_calls,
        unsigned int partial_writes,
        unsigned int writei_errors) {
    DiagnosticTimestamp invocation_end = diagnostic_now();
    uint64_t duration_nanos = 0U;
    int duration_valid = diagnostic_elapsed_nanos(
            invocation_start, invocation_end, &duration_nanos);
    if ((!duration_valid || duration_nanos < SLOW_OPERATION_NANOS)
            && writei_errors == 0U
            && recover_calls == 0U) {
        return;
    }
    (void) fprintf(
            stderr,
            AUDIO_NATIVE_DIAGNOSTIC_PREFIX
            " WRITE_SUMMARY bytes=%d frames=%llu total_ms=%.3f"
            " writei_calls=%u recover_calls=%u partial_writes=%u\n",
            (int) bytes,
            (unsigned long long) frames,
            diagnostic_duration_ms(duration_valid, duration_nanos),
            writei_calls,
            recover_calls,
            partial_writes);
}

static void throw_by_name(
        JNIEnv *environment, const char *class_name, const char *message) {
    jclass exception_class;
    if ((*environment)->ExceptionCheck(environment)) {
        return;
    }
    exception_class = (*environment)->FindClass(environment, class_name);
    if (exception_class != NULL) {
        (*environment)->ThrowNew(environment, exception_class, message);
    }
}

static void throw_illegal_argument(JNIEnv *environment, const char *message) {
    throw_by_name(environment, "java/lang/IllegalArgumentException", message);
}

static void throw_illegal_state(JNIEnv *environment, const char *message) {
    throw_by_name(environment, "java/lang/IllegalStateException", message);
}

static void throw_out_of_memory(JNIEnv *environment, const char *message) {
    throw_by_name(environment, "java/lang/OutOfMemoryError", message);
}

static void throw_io_message(JNIEnv *environment, const char *message) {
    throw_by_name(environment, "java/io/IOException", message);
}

static void throw_io_error(
        JNIEnv *environment, const char *operation, int error_code) {
    char message[512];
    const char *description = snd_strerror(error_code);
    if (description == NULL) {
        description = "unknown ALSA error";
    }
    (void) snprintf(
            message,
            sizeof(message),
            "%s failed: %d: %s",
            operation,
            error_code,
            description);
    throw_io_message(environment, message);
}

/*
 * AlsaPcm.open serializes every nativeOpen call with one Java monitor, so this
 * process-wide bootstrap does not need a second native locking dependency.
 */
static int ensure_libasound_global(JNIEnv *environment) {
    const char *loader_error;
    if (g_libasound_global != NULL) {
        return 0;
    }
    if (g_libasound_attempted) {
        throw_io_message(
                environment,
                g_libasound_error[0] != '\0'
                        ? g_libasound_error
                        : "Process-wide ALSA bootstrap failed.");
        return -1;
    }

    g_libasound_attempted = 1;
    (void) dlerror();
    g_libasound_global = dlopen(
            LIBASOUND_GLOBAL_PATH, RTLD_NOW | RTLD_GLOBAL);
    if (g_libasound_global != NULL) {
        return 0;
    }
    loader_error = dlerror();
    if (loader_error == NULL) {
        loader_error = "unknown dynamic loader error";
    }
    (void) snprintf(
            g_libasound_error,
            sizeof(g_libasound_error),
            "dlopen(%s, RTLD_NOW|RTLD_GLOBAL) failed: %s",
            LIBASOUND_GLOBAL_PATH,
            loader_error);
    throw_io_message(environment, g_libasound_error);
    return -1;
}

static jlong context_to_handle(AlsaPcmContext *context) {
    return (jlong) (intptr_t) context;
}

static AlsaPcmContext *context_from_handle(
        JNIEnv *environment, jlong handle) {
    AlsaPcmContext *context;
    if (handle == (jlong) 0) {
        throw_illegal_state(
                environment, "Native ALSA PCM handle is invalid or closed.");
        return NULL;
    }
    context = (AlsaPcmContext *) (intptr_t) handle;
    if (context->pcm == NULL) {
        throw_illegal_state(
                environment, "Native ALSA PCM handle is invalid or closed.");
        return NULL;
    }
    return context;
}

static void release_open_context(AlsaPcmContext *context) {
    if (context == NULL) {
        return;
    }
    if (context->pcm != NULL) {
        (void) snd_pcm_close(context->pcm);
        context->pcm = NULL;
    }
    free(context);
}

JNIEXPORT jlong JNICALL Java_utils_AlsaPcm_nativeOpen(
        JNIEnv *environment, jclass pcm_class) {
    AlsaPcmContext *context;
    int result;
    (void) pcm_class;

    if (sizeof(intptr_t) > sizeof(jlong)) {
        throw_io_message(
                environment,
                "Native pointer cannot be represented by a Java long handle.");
        return (jlong) 0;
    }
    if (ensure_libasound_global(environment) != 0) {
        return (jlong) 0;
    }

    context = (AlsaPcmContext *) calloc(1U, sizeof(*context));
    if (context == NULL) {
        throw_out_of_memory(
                environment, "Unable to allocate native ALSA PCM context.");
        return (jlong) 0;
    }

    result = snd_pcm_open(
            &context->pcm,
            ALSA_DEVICE_NAME,
            SND_PCM_STREAM_PLAYBACK,
            0);
    if (result < 0) {
        free(context);
        throw_io_error(environment, "snd_pcm_open(default)", result);
        return (jlong) 0;
    }

    result = snd_pcm_set_params(
            context->pcm,
            SND_PCM_FORMAT_S16_LE,
            SND_PCM_ACCESS_RW_INTERLEAVED,
            ALSA_CHANNELS,
            ALSA_SAMPLE_RATE,
            1,
            ALSA_LATENCY_MICROS);
    if (result < 0) {
        release_open_context(context);
        throw_io_error(environment, "snd_pcm_set_params", result);
        return (jlong) 0;
    }

    result = snd_pcm_get_params(
            context->pcm,
            &context->buffer_frames,
            &context->period_frames);
    if (result < 0) {
        release_open_context(context);
        throw_io_error(environment, "snd_pcm_get_params", result);
        return (jlong) 0;
    }

    return context_to_handle(context);
}

JNIEXPORT void JNICALL Java_utils_AlsaPcm_nativeWrite(
        JNIEnv *environment,
        jclass pcm_class,
        jlong handle,
        jbyteArray data,
        jint offset,
        jint length) {
    DiagnosticTimestamp invocation_start = diagnostic_now();
    AlsaPcmContext *context = context_from_handle(environment, handle);
    jsize array_length;
    jbyte *bytes;
    snd_pcm_uframes_t remaining_frames;
    snd_pcm_uframes_t total_frames;
    snd_pcm_uframes_t frame_offset = 0U;
    int recovery_attempts = 0;
    unsigned int writei_calls = 0U;
    unsigned int recover_calls = 0U;
    unsigned int partial_writes = 0U;
    unsigned int writei_errors = 0U;
    (void) pcm_class;

    if (context == NULL) {
        return;
    }
    if (data == NULL) {
        throw_illegal_argument(environment, "PCM data must not be null.");
        return;
    }
    array_length = (*environment)->GetArrayLength(environment, data);
    if (offset < 0 || length <= 0 || length > array_length
            || offset > array_length - length) {
        throw_illegal_argument(
                environment, "PCM write range is outside the byte array or empty.");
        return;
    }
    if ((length % ALSA_FRAME_SIZE) != 0) {
        throw_illegal_argument(
                environment,
                "PCM write length must be aligned to a 2-byte mono frame.");
        return;
    }

    bytes = (*environment)->GetByteArrayElements(environment, data, NULL);
    if (bytes == NULL) {
        return;
    }
    total_frames = (snd_pcm_uframes_t) (length / ALSA_FRAME_SIZE);
    remaining_frames = total_frames;

    while (remaining_frames > 0U) {
        snd_pcm_uframes_t requested_frames = remaining_frames;
        DiagnosticTimestamp write_start = diagnostic_now();
        DiagnosticTimestamp write_end;
        uint64_t write_duration_nanos = 0U;
        int write_duration_valid;
        snd_pcm_sframes_t written;
        writei_calls++;
        written = snd_pcm_writei(
                context->pcm,
                bytes + offset
                        + (frame_offset * (snd_pcm_uframes_t) ALSA_FRAME_SIZE),
                requested_frames);
        write_end = diagnostic_now();
        write_duration_valid = diagnostic_elapsed_nanos(
                write_start, write_end, &write_duration_nanos);
        if (written < 0) {
            int recovery_result;
            DiagnosticTimestamp recover_start;
            DiagnosticTimestamp recover_end;
            uint64_t recover_duration_nanos = 0U;
            int recover_duration_valid;
            writei_errors++;
            if (recovery_attempts >= MAX_RECOVERY_ATTEMPTS) {
                log_writei_error(
                        writei_calls,
                        requested_frames,
                        written,
                        write_duration_valid,
                        write_duration_nanos);
                (*environment)->ReleaseByteArrayElements(
                        environment, data, bytes, JNI_ABORT);
                log_write_summary(
                        length,
                        total_frames,
                        invocation_start,
                        writei_calls,
                        recover_calls,
                        partial_writes,
                        writei_errors);
                throw_io_error(
                        environment,
                        "snd_pcm_writei recovery limit",
                        (int) written);
                return;
            }
            recovery_attempts++;
            recover_calls++;
            recover_start = diagnostic_now();
            recovery_result = snd_pcm_recover(
                    context->pcm, (int) written, 1);
            recover_end = diagnostic_now();
            recover_duration_valid = diagnostic_elapsed_nanos(
                    recover_start, recover_end, &recover_duration_nanos);
            /* Do not put diagnostic I/O between the ALSA error and recovery. */
            log_writei_error(
                    writei_calls,
                    requested_frames,
                    written,
                    write_duration_valid,
                    write_duration_nanos);
            log_recover(
                    recover_calls,
                    (int) written,
                    recovery_result,
                    recover_duration_valid,
                    recover_duration_nanos);
            if (recovery_result < 0) {
                (*environment)->ReleaseByteArrayElements(
                        environment, data, bytes, JNI_ABORT);
                log_write_summary(
                        length,
                        total_frames,
                        invocation_start,
                        writei_calls,
                        recover_calls,
                        partial_writes,
                        writei_errors);
                throw_io_error(environment, "snd_pcm_recover", recovery_result);
                return;
            }
            continue;
        }
        if (written == 0) {
            log_writei_event(
                    "WRITEI_ZERO",
                    writei_calls,
                    requested_frames,
                    written,
                    write_duration_valid,
                    write_duration_nanos);
            (*environment)->ReleaseByteArrayElements(
                    environment, data, bytes, JNI_ABORT);
            log_write_summary(
                    length,
                    total_frames,
                    invocation_start,
                    writei_calls,
                    recover_calls,
                    partial_writes,
                    writei_errors);
            throw_io_message(
                    environment,
                    "snd_pcm_writei returned an invalid frame count.");
            return;
        }
        if ((snd_pcm_uframes_t) written > remaining_frames) {
            (*environment)->ReleaseByteArrayElements(
                    environment, data, bytes, JNI_ABORT);
            log_write_summary(
                    length,
                    total_frames,
                    invocation_start,
                    writei_calls,
                    recover_calls,
                    partial_writes,
                    writei_errors);
            throw_io_message(
                    environment,
                    "snd_pcm_writei returned an invalid frame count.");
            return;
        }
        if ((snd_pcm_uframes_t) written < requested_frames) {
            partial_writes++;
            log_writei_event(
                    "WRITEI_PARTIAL",
                    writei_calls,
                    requested_frames,
                    written,
                    write_duration_valid,
                    write_duration_nanos);
        }
        if (write_duration_valid
                && write_duration_nanos >= SLOW_OPERATION_NANOS) {
            log_writei_event(
                    "WRITEI_SLOW",
                    writei_calls,
                    requested_frames,
                    written,
                    write_duration_valid,
                    write_duration_nanos);
        }
        frame_offset += (snd_pcm_uframes_t) written;
        remaining_frames -= (snd_pcm_uframes_t) written;
    }

    (*environment)->ReleaseByteArrayElements(
            environment, data, bytes, JNI_ABORT);
    log_write_summary(
            length,
            total_frames,
            invocation_start,
            writei_calls,
            recover_calls,
            partial_writes,
            writei_errors);
}

JNIEXPORT jlong JNICALL Java_utils_AlsaPcm_nativeGetBufferFrames(
        JNIEnv *environment, jclass pcm_class, jlong handle) {
    AlsaPcmContext *context = context_from_handle(environment, handle);
    (void) pcm_class;
    if (context == NULL) {
        return (jlong) -1;
    }
    return (jlong) context->buffer_frames;
}

JNIEXPORT jlong JNICALL Java_utils_AlsaPcm_nativeGetPeriodFrames(
        JNIEnv *environment, jclass pcm_class, jlong handle) {
    AlsaPcmContext *context = context_from_handle(environment, handle);
    (void) pcm_class;
    if (context == NULL) {
        return (jlong) -1;
    }
    return (jlong) context->period_frames;
}

JNIEXPORT void JNICALL Java_utils_AlsaPcm_nativeDrain(
        JNIEnv *environment, jclass pcm_class, jlong handle) {
    AlsaPcmContext *context = context_from_handle(environment, handle);
    int result;
    (void) pcm_class;
    if (context == NULL) {
        return;
    }
    result = snd_pcm_drain(context->pcm);
    if (result < 0) {
        throw_io_error(environment, "snd_pcm_drain", result);
    }
}

JNIEXPORT void JNICALL Java_utils_AlsaPcm_nativeDrop(
        JNIEnv *environment, jclass pcm_class, jlong handle) {
    AlsaPcmContext *context = context_from_handle(environment, handle);
    int result;
    (void) pcm_class;
    if (context == NULL) {
        return;
    }
    result = snd_pcm_drop(context->pcm);
    if (result < 0) {
        throw_io_error(environment, "snd_pcm_drop", result);
    }
}

JNIEXPORT void JNICALL Java_utils_AlsaPcm_nativeClose(
        JNIEnv *environment, jclass pcm_class, jlong handle) {
    AlsaPcmContext *context;
    snd_pcm_t *pcm;
    int result;
    (void) pcm_class;

    if (handle == (jlong) 0) {
        return;
    }
    context = (AlsaPcmContext *) (intptr_t) handle;

    pcm = context->pcm;
    context->pcm = NULL;
    if (pcm == NULL) {
        free(context);
        throw_illegal_state(
                environment, "Native ALSA PCM context has no open handle.");
        return;
    }
    result = snd_pcm_close(pcm);
    free(context);
    if (result < 0) {
        throw_io_error(environment, "snd_pcm_close", result);
    }
}
