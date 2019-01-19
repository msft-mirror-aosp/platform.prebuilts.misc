LOCAL_PATH := $(call my-dir)
include $(CLEAR_VARS)

# Explicitly mark gdbserver as "debug" so that it doesn't
# get included in user or SDK builds. (GPL issues)
#
LOCAL_SRC_FILES := gdbserver64
LOCAL_MODULE := gdbserver
LOCAL_MODULE_STEM := gdbserver64
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_MULTILIB := 64
include $(BUILD_PREBUILT)
