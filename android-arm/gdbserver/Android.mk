LOCAL_PATH := $(call my-dir)
include $(CLEAR_VARS)

# Explicitly mark gdbserver as "debug" so that it doesn't
# get included in user or SDK builds. (GPL issues)
#
LOCAL_SRC_FILES := gdbserver
LOCAL_MODULE := gdbserver
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_MULTILIB := 32
include $(BUILD_PREBUILT)
