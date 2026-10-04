# Claudegotchi
#
#   make test      Tests der App
#   make sim       Gotchi ohne Hardware starten (Vorschau: http://localhost:8765/)
#                  anderer Port: make sim PORT=8766
#   make zero2w    Image für den Raspberry Pi Zero 2 W bauen
#   make zerow     Image für den Raspberry Pi Zero W bauen
#
# Die Images landen in output/<ziel>/images/claudegotchi-<ziel>.img.xz

PORT       ?= 8765
BR_VERSION ?= 2026.02.3
BR_DIR     ?= $(CURDIR)/.buildroot
OUT        ?= $(CURDIR)/output
BR_MAKE     = $(MAKE) -C $(BR_DIR) BR2_EXTERNAL=$(CURDIR)/os O=$(OUT)/$@

.PHONY: test sim zero2w zerow clean

test:
	cd app && python3 -m unittest discover -s tests

sim:
	cd app && python3 -m claudegotchi --sim --port $(PORT) --config ../os/board/claudegotchi/claudegotchi.toml

$(BR_DIR):
	git clone --depth 1 --branch $(BR_VERSION) https://gitlab.com/buildroot.org/buildroot.git $(BR_DIR)

zero2w zerow: | $(BR_DIR)
	$(BR_MAKE) claudegotchi_$@_defconfig
	$(BR_MAKE)

clean:
	rm -rf $(OUT)
