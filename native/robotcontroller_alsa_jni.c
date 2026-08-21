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

typedef struct AlsaPcmContext {
    snd_pcm_t *pcm;
    snd_pcm_uframes_t buffer_frames;
    snd_pcm_uframes_t period_frames;
} AlsaPcmContext;

static void *g_libasound_global;
static int g_libasound_attempted;
static char g_libasound_error[768];

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
    AlsaPcmContext *context = context_from_handle(environment, handle);
    jsize array_length;
    jbyte *bytes;
    snd_pcm_uframes_t remaining_frames;
    snd_pcm_uframes_t frame_offset = 0U;
    int recovery_attempts = 0;
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
    remaining_frames = (snd_pcm_uframes_t) (length / ALSA_FRAME_SIZE);

    while (remaining_frames > 0U) {
        snd_pcm_sframes_t written = snd_pcm_writei(
                context->pcm,
                bytes + offset
                        + (frame_offset * (snd_pcm_uframes_t) ALSA_FRAME_SIZE),
                remaining_frames);
        if (written < 0) {
            int recovery_result;
            if (recovery_attempts >= MAX_RECOVERY_ATTEMPTS) {
                (*environment)->ReleaseByteArrayElements(
                        environment, data, bytes, JNI_ABORT);
                throw_io_error(
                        environment,
                        "snd_pcm_writei recovery limit",
                        (int) written);
                return;
            }
            recovery_attempts++;
            recovery_result = snd_pcm_recover(
                    context->pcm, (int) written, 1);
            if (recovery_result < 0) {
                (*environment)->ReleaseByteArrayElements(
                        environment, data, bytes, JNI_ABORT);
                throw_io_error(environment, "snd_pcm_recover", recovery_result);
                return;
            }
            continue;
        }
        if (written == 0 || (snd_pcm_uframes_t) written > remaining_frames) {
            (*environment)->ReleaseByteArrayElements(
                    environment, data, bytes, JNI_ABORT);
            throw_io_message(
                    environment,
                    "snd_pcm_writei returned an invalid frame count.");
            return;
        }
        frame_offset += (snd_pcm_uframes_t) written;
        remaining_frames -= (snd_pcm_uframes_t) written;
    }

    (*environment)->ReleaseByteArrayElements(
            environment, data, bytes, JNI_ABORT);
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
