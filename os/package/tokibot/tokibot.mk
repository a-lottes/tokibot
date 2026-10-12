################################################################################
#
# tokibot
#
################################################################################

TOKIBOT_VERSION = 0.5.2
TOKIBOT_SITE = $(BR2_EXTERNAL_TOKIBOT_PATH)/../app
TOKIBOT_SITE_METHOD = local
TOKIBOT_LICENSE = MIT
TOKIBOT_DEPENDENCIES = python3

TOKIBOT_PYLIB = $(TARGET_DIR)/usr/lib/python$(PYTHON3_VERSION_MAJOR)/site-packages

define TOKIBOT_INSTALL_TARGET_CMDS
	rm -rf $(TOKIBOT_PYLIB)/tokibot
	cp -r $(@D)/tokibot $(TOKIBOT_PYLIB)/tokibot
	find $(TOKIBOT_PYLIB)/tokibot -name '__pycache__' -prune -exec rm -rf {} +
	$(INSTALL) -D -m 0755 $(TOKIBOT_PKGDIR)/tokibot-run $(TARGET_DIR)/usr/bin/tokibot-run
endef

define TOKIBOT_INSTALL_INIT_SYSV
	$(INSTALL) -D -m 0755 $(TOKIBOT_PKGDIR)/S90tokibot \
		$(TARGET_DIR)/etc/init.d/S90tokibot
endef

$(eval $(generic-package))
