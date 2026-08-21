#include <alsa/asoundlib.h>
#include <dlfcn.h>
#include <jni.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "AlsaPcmProbe.h"

#define MAX_RECOVERY_ATTEMPTS 3
#define LIBASOUND_GLOBAL_PATH "/usr/lib/libasound.so.2"

typedef struct ProbePcmContext {
    snd_pcm_t *pcm;
    int frame_size;
    snd_pcm_uframes_t buffer_frames;
    snd_pcm_uframes_t period_frames;
    struct ProbePcmContext *next;
} ProbePcmContext;

/*
 * The Java wrapper serializes all calls. This registry lets close remove and
 * free a context while a repeated close of the same opaque value remains a
 * harmless no-op. The standalone probe creates only one context.
 */
static ProbePcmContext *open_contexts;
static void *g_libasound_global;

static jlong context_to_handle(ProbePcmContext *context) {
    return (jlong) (intptr_t) context;
}

static ProbePcmContext *handle_to_pointer(jlong handle) {
    return (ProbePcmContext *) (intptr_t) handle;
}

static void throw_by_name(JNIEnv *environment, const char *class_name, const char *message) {
    jclass exception_class = (*environment)->FindClass(environment, class_name);
    if (exception_class != NULL) {
        (*environment)->ThrowNew(environment, exception_class, message);
    }
}

static void throw_illegal_argument(JNIEnv *environment, const char *message) {
    throw_by_name(environment, "java/lang/IllegalArgumentException", message);
}

static void throw_out_of_memory(JNIEnv *environment, const char *message) {
    throw_by_name(environment, "java/lang/OutOfMemoryError", message);
}

static int ensure_libasound_global(JNIEnv *environment) {
    void *handle;
    const char *loader_error;
    char message[768];

    if (g_libasound_global != NULL) {
        return 0;
    }

    (void) dlerror();
    handle = dlopen(LIBASOUND_GLOBAL_PATH, RTLD_NOW | RTLD_GLOBAL);
    if (handle == NULL) {
        loader_error = dlerror();
        if (loader_error == NULL) {
            loader_error = "unknown dynamic loader error";
        }
        (void) snprintf(
                message,
                sizeof(message),
                "dlopen(%s, RTLD_NOW|RTLD_GLOBAL) failed: %s",
                LIBASOUND_GLOBAL_PATH,
                loader_error);
        throw_by_name(environment, "java/io/IOException", message);
        return -1;
    }

    /* Keep global ALSA symbols available to external PCM plugins for process lifetime. */
    g_libasound_global = handle;
    return 0;
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
    throw_by_name(environment, "java/io/IOException", message);
}

static void throw_handle_error(JNIEnv *environment) {
    throw_by_name(
            environment,
            "java/io/IOException",
            "Native PCM handle is null, closed, or invalid.");
}

static void register_context(ProbePcmContext *context) {
    context->next = open_contexts;
    open_contexts = context;
}

static ProbePcmContext *find_context(jlong handle) {
    ProbePcmContext *candidate;
    ProbePcmContext *requested;
    if (handle == (jlong) 0) {
        return NULL;
    }
    requested = handle_to_pointer(handle);
    for (candidate = open_contexts; candidate != NULL; candidate = candidate->next) {
        if (candidate == requested) {
            return candidate;
        }
    }
    return NULL;
}

static ProbePcmContext *remove_context(jlong handle) {
    ProbePcmContext **link = &open_contexts;
    ProbePcmContext *requested;
    if (handle == (jlong) 0) {
        return NULL;
    }
    requested = handle_to_pointer(handle);
    while (*link != NULL) {
        if (*link == requested) {
            ProbePcmContext *removed = *link;
            *link = removed->next;
            removed->next = NULL;
            return removed;
        }
        link = &(*link)->next;
    }
    return NULL;
}

JNIEXPORT jlong JNICALL Java_AlsaPcmProbe_openPcm(
        JNIEnv *environment,
        jclass probe_class,
        jstring pcm_name,
        jint sample_rate,
        jint channels,
        jint latency_micros) {
    const char *pcm_name_bytes;
    char open_operation[320];
    ProbePcmContext *context;
    int result;
    (void) probe_class;

    if (pcm_name == NULL) {
        throw_illegal_argument(environment, "PCM name must not be null.");
        return (jlong) 0;
    }
    if (sample_rate <= 0 || channels <= 0 || latency_micros <= 0) {
        throw_illegal_argument(
                environment,
                "Sample rate, channels, and latency must all be positive.");
        return (jlong) 0;
    }
    if (channels > INT32_MAX / 2) {
        throw_illegal_argument(environment, "PCM frame size overflows a signed integer.");
        return (jlong) 0;
    }
    if (sizeof(intptr_t) > sizeof(jlong)) {
        throw_by_name(
                environment,
                "java/io/IOException",
                "Native pointer cannot be represented by a Java long handle.");
        return (jlong) 0;
    }
    if (ensure_libasound_global(environment) != 0) {
        return (jlong) 0;
    }

    context = (ProbePcmContext *) calloc(1U, sizeof(*context));
    if (context == NULL) {
        throw_out_of_memory(environment, "Unable to allocate native PCM context.");
        return (jlong) 0;
    }
    context->frame_size = channels * 2;

    pcm_name_bytes = (*environment)->GetStringUTFChars(environment, pcm_name, NULL);
    if (pcm_name_bytes == NULL) {
        free(context);
        return (jlong) 0;
    }

    result = snd_pcm_open(
            &context->pcm,
            pcm_name_bytes,
            SND_PCM_STREAM_PLAYBACK,
            0);
    (void) snprintf(
            open_operation,
            sizeof(open_operation),
            "snd_pcm_open(%s)",
            pcm_name_bytes);
    (*environment)->ReleaseStringUTFChars(environment, pcm_name, pcm_name_bytes);
    if (result < 0) {
        free(context);
        throw_io_error(environment, open_operation, result);
        return (jlong) 0;
    }

    result = snd_pcm_set_params(
            context->pcm,
            SND_PCM_FORMAT_S16_LE,
            SND_PCM_ACCESS_RW_INTERLEAVED,
            (unsigned int) channels,
            (unsigned int) sample_rate,
            1,
            (unsigned int) latency_micros);
    if (result < 0) {
        (void) snd_pcm_close(context->pcm);
        free(context);
        throw_io_error(environment, "snd_pcm_set_params", result);
        return (jlong) 0;
    }

    result = snd_pcm_get_params(
            context->pcm,
            &context->buffer_frames,
            &context->period_frames);
    if (result < 0) {
        (void) snd_pcm_close(context->pcm);
        free(context);
        throw_io_error(environment, "snd_pcm_get_params", result);
        return (jlong) 0;
    }

    register_context(context);
    return context_to_handle(context);
}

JNIEXPORT jint JNICALL Java_AlsaPcmProbe_writePcm(
        JNIEnv *environment,
        jclass probe_class,
        jlong handle,
        jbyteArray data,
        jint offset,
        jint length) {
    ProbePcmContext *context = find_context(handle);
    jsize array_length;
    jbyte *bytes;
    snd_pcm_uframes_t remaining_frames;
    snd_pcm_uframes_t frame_offset = 0U;
    int recovery_attempts = 0;
    (void) probe_class;

    if (context == NULL) {
        throw_handle_error(environment);
        return (jint) -1;
    }
    if (data == NULL) {
        throw_illegal_argument(environment, "PCM data must not be null.");
        return (jint) -1;
    }
    array_length = (*environment)->GetArrayLength(environment, data);
    if (offset < 0 || length <= 0 || offset > array_length - length) {
        throw_illegal_argument(environment, "PCM write range is outside the byte array.");
        return (jint) -1;
    }
    if (offset % context->frame_size != 0 || length % context->frame_size != 0) {
        throw_illegal_argument(environment, "PCM write range is not frame-aligned.");
        return (jint) -1;
    }

    bytes = (*environment)->GetByteArrayElements(environment, data, NULL);
    if (bytes == NULL) {
        return (jint) -1;
    }
    remaining_frames = (snd_pcm_uframes_t) (length / context->frame_size);

    while (remaining_frames > 0U) {
        snd_pcm_sframes_t written = snd_pcm_writei(
                context->pcm,
                bytes + offset + (frame_offset * (snd_pcm_uframes_t) context->frame_size),
                remaining_frames);
        if (written < 0) {
            int recovery_result;
            if (recovery_attempts >= MAX_RECOVERY_ATTEMPTS) {
                (*environment)->ReleaseByteArrayElements(
                        environment, data, bytes, JNI_ABORT);
                throw_io_error(environment, "snd_pcm_writei recovery limit", (int) written);
                return (jint) -1;
            }
            recovery_attempts++;
            recovery_result = snd_pcm_recover(context->pcm, (int) written, 1);
            if (recovery_result < 0) {
                (*environment)->ReleaseByteArrayElements(
                        environment, data, bytes, JNI_ABORT);
                throw_io_error(environment, "snd_pcm_recover", recovery_result);
                return (jint) -1;
            }
            continue;
        }
        if (written == 0 || (snd_pcm_uframes_t) written > remaining_frames) {
            (*environment)->ReleaseByteArrayElements(
                    environment, data, bytes, JNI_ABORT);
            throw_by_name(
                    environment,
                    "java/io/IOException",
                    "snd_pcm_writei returned an invalid frame count.");
            return (jint) -1;
        }
        frame_offset += (snd_pcm_uframes_t) written;
        remaining_frames -= (snd_pcm_uframes_t) written;
    }

    (*environment)->ReleaseByteArrayElements(environment, data, bytes, JNI_ABORT);
    return length;
}

JNIEXPORT jlong JNICALL Java_AlsaPcmProbe_getBufferFrames(
        JNIEnv *environment, jclass probe_class, jlong handle) {
    ProbePcmContext *context = find_context(handle);
    (void) probe_class;
    if (context == NULL) {
        throw_handle_error(environment);
        return (jlong) -1;
    }
    return (jlong) context->buffer_frames;
}

JNIEXPORT jlong JNICALL Java_AlsaPcmProbe_getPeriodFrames(
        JNIEnv *environment, jclass probe_class, jlong handle) {
    ProbePcmContext *context = find_context(handle);
    (void) probe_class;
    if (context == NULL) {
        throw_handle_error(environment);
        return (jlong) -1;
    }
    return (jlong) context->period_frames;
}

JNIEXPORT void JNICALL Java_AlsaPcmProbe_drainPcm(
        JNIEnv *environment, jclass probe_class, jlong handle) {
    ProbePcmContext *context = find_context(handle);
    int result;
    (void) probe_class;
    if (context == NULL) {
        throw_handle_error(environment);
        return;
    }
    result = snd_pcm_drain(context->pcm);
    if (result < 0) {
        throw_io_error(environment, "snd_pcm_drain", result);
    }
}

JNIEXPORT void JNICALL Java_AlsaPcmProbe_dropPcm(
        JNIEnv *environment, jclass probe_class, jlong handle) {
    ProbePcmContext *context = find_context(handle);
    int result;
    (void) probe_class;
    if (context == NULL) {
        return;
    }
    result = snd_pcm_drop(context->pcm);
    if (result < 0) {
        throw_io_error(environment, "snd_pcm_drop", result);
    }
}

JNIEXPORT void JNICALL Java_AlsaPcmProbe_closePcm(
        JNIEnv *environment, jclass probe_class, jlong handle) {
    ProbePcmContext *context = remove_context(handle);
    int result;
    (void) probe_class;
    if (context == NULL) {
        return;
    }
    result = snd_pcm_close(context->pcm);
    context->pcm = NULL;
    free(context);
    if (result < 0) {
        throw_io_error(environment, "snd_pcm_close", result);
    }
}
