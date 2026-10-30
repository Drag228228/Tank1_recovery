#
# OrangeFox / TWRP product for OSCAL TANK 1
#

# Inherit from those products. Most specific first.
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/aosp_base.mk)

# Virtual A/B with compression, launched with vendor ramdisk
$(call inherit-product, $(SRC_TARGET_DIR)/product/virtual_ab_ota/launch_with_vendor_ramdisk.mk)

# Inherit some common TWRP stuff.
$(call inherit-product, vendor/twrp/config/common.mk)

# Inherit from device
$(call inherit-product, device/oscal/TANK_1/device.mk)

PRODUCT_DEVICE := TANK_1
PRODUCT_NAME := twrp_TANK_1
PRODUCT_BRAND := OSCAL
PRODUCT_MODEL := TANK 1
PRODUCT_MANUFACTURER := OSCAL
PRODUCT_RELEASE_NAME := TANK 1

PRODUCT_GMS_CLIENTID_BASE := android-oscal

PRODUCT_BUILD_PROP_OVERRIDES += \
    PRIVATE_BUILD_DESC="TANK_1_RU-user 15 AP3A.240905.015.A2 1758106872 release-keys"

BUILD_FINGERPRINT := OSCAL/TANK_1_RU/TANK_1:15/AP3A.240905.015.A2/1758106872:user/release-keys
