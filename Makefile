# Claudegotchi
#
#   make test      run the app tests
#   make sim       run the gotchi without hardware (preview: http://localhost:8765/)
#                  other port: make sim PORT=8766
#   make mockups   render every mood into docs/mockups.png
#   make zero2w    build the image for the Raspberry Pi Zero 2 W
#   make zerow     build the image for the Raspberry Pi Zero W
#
# Images end up in output/<target>/images/claudegotchi-<target>.img.xz

PORT       ?= 8765
BR_VERSION ?= 2026.02.3
BR_DIR     ?= $(CURDIR)/.buildroot
OUT        ?= $(CURDIR)/output
BR_MAKE     = $(MAKE) -C $(BR_DIR) BR2_EXTERNAL=$(CURDIR)/os O=$(OUT)/$@

.PHONY: test sim mockups zero2w zerow clean

test:
	cd app && python3 -m unittest discover -s tests

sim:
	cd app && python3 -m claudegotchi --sim --port $(PORT) --config ../os/board/claudegotchi/claudegotchi.toml

mockups:
	cd app && PYTHONPATH=. python3 tools/mockups.py ../docs/mockups.png

$(BR_DIR):
	git clone --depth 1 --branch $(BR_VERSION) https://gitlab.com/buildroot.org/buildroot.git $(BR_DIR)

zero2w zerow: | $(BR_DIR)
	$(BR_MAKE) claudegotchi_$@_defconfig
	$(BR_MAKE)

clean:
	rm -rf $(OUT)
