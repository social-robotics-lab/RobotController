# Build only the RobotController ALSA JNI adapter on the validated Edison host.
# Invoke from the repository root with: make -C native JAVA_HOME=... ALSA_INCLUDE_DIR=...
# Required: JAVA_HOME (Java 8 JDK) and ALSA_INCLUDE_DIR (alsa-lib headers).

JAVA_HOME ?=
ALSA_INCLUDE_DIR ?=
CC ?= gcc

BUILD_DIR ?= build
GENERATED_DIR ?= generated
JAVA_CLASSES_DIR := $(BUILD_DIR)/classes

JAVAC := $(JAVA_HOME)/bin/javac
JAVAH := $(JAVA_HOME)/bin/javah
JAVA_SOURCE := ../src/utils/AlsaPcm.java
JAVA_CLASS := $(JAVA_CLASSES_DIR)/utils/AlsaPcm.class
JNI_HEADER := $(GENERATED_DIR)/utils_AlsaPcm.h
NATIVE_SOURCE := robotcontroller_alsa_jni.c
TARGET := $(BUILD_DIR)/librobotcontroller_alsa.so

LIBASOUND_SO ?= /usr/lib/libasound.so.2

CPPFLAGS += -D_POSIX_C_SOURCE=200809L
CFLAGS += -std=c99 -fPIC -Wall -Wextra
LDLIBS += $(LIBASOUND_SO) -ldl

.PHONY: all check-variables

all: $(TARGET)

check-variables:
	@test -n "$(JAVA_HOME)" || { echo "JAVA_HOME is required" >&2; exit 2; }
	@test -n "$(ALSA_INCLUDE_DIR)" || { echo "ALSA_INCLUDE_DIR is required" >&2; exit 2; }
	@test -x "$(JAVAC)" || { echo "javac not found: $(JAVAC)" >&2; exit 2; }
	@test -x "$(JAVAH)" || { echo "javah not found: $(JAVAH)" >&2; exit 2; }
	@test -f "$(LIBASOUND_SO)" || { echo "libasound not found: $(LIBASOUND_SO)" >&2; exit 2; }

$(JAVA_CLASS): $(JAVA_SOURCE) | check-variables
	@mkdir -p "$(JAVA_CLASSES_DIR)"
	"$(JAVAC)" -encoding UTF-8 -source 8 -target 8 \
		-d "$(JAVA_CLASSES_DIR)" "$(JAVA_SOURCE)"

$(JNI_HEADER): $(JAVA_CLASS) | check-variables
	@mkdir -p "$(GENERATED_DIR)"
	"$(JAVAH)" -classpath "$(JAVA_CLASSES_DIR)" \
		-d "$(GENERATED_DIR)" utils.AlsaPcm

$(TARGET): $(NATIVE_SOURCE) $(JNI_HEADER) | check-variables
	@mkdir -p "$(BUILD_DIR)"
	$(CC) $(CPPFLAGS) $(CFLAGS) -shared \
		-I"$(JAVA_HOME)/include" \
		-I"$(JAVA_HOME)/include/linux" \
		-I"$(ALSA_INCLUDE_DIR)" \
		-I"$(GENERATED_DIR)" \
		-o "$@" "$(NATIVE_SOURCE)" $(LDLIBS)
