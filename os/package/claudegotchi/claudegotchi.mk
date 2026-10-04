################################################################################
#
# claudegotchi
#
################################################################################

CLAUDEGOTCHI_VERSION = 0.1.0
CLAUDEGOTCHI_SITE = $(BR2_EXTERNAL_CLAUDEGOTCHI_PATH)/../app
CLAUDEGOTCHI_SITE_METHOD = local
CLAUDEGOTCHI_LICENSE = MIT
CLAUDEGOTCHI_DEPENDENCIES = python3

CLAUDEGOTCHI_PYLIB = $(TARGET_DIR)/usr/lib/python$(PYTHON3_VERSION_MAJOR)/site-packages

define CLAUDEGOTCHI_INSTALL_TARGET_CMDS
	rm -rf $(CLAUDEGOTCHI_PYLIB)/claudegotchi
	cp -r $(@D)/claudegotchi $(CLAUDEGOTCHI_PYLIB)/claudegotchi
	find $(CLAUDEGOTCHI_PYLIB)/claudegotchi -name '__pycache__' -prune -exec rm -rf {} +
endef

define CLAUDEGOTCHI_INSTALL_INIT_SYSV
	$(INSTALL) -D -m 0755 $(CLAUDEGOTCHI_PKGDIR)/S90claudegotchi \
		$(TARGET_DIR)/etc/init.d/S90claudegotchi
endef

$(eval $(generic-package))
