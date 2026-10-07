# Tokibot
#
#   make test      run the app tests
#   make sim       run the gotchi without hardware (preview: http://localhost:8765/)
#                  other port: make sim PORT=8766
#                  with a pretend gotchi nearby to make friends with: make sim FAKE=Mochi
#                  with a fake battery: make sim BATTERY=sim
#   make mockups   render every mood into docs/mockups.png
#   make figures   redraw the blueprint figures in the website (docs/*.html)
#   make faq       build docs/faq.html from docs/faq.md
#   make social-pics  render the critter pictures for docs/friends.html
#   make bundle    pack the app into output/tokibot-app.tar.gz (update without flashing)
#   make update    send that bundle to a gotchi: make update GOTCHI=http://tokibot-xxxx.local:8765 TOKEN=…
#   make zero2w    build the image for the Raspberry Pi Zero 2 W
#   make zerow     build the image for the Raspberry Pi Zero W
#
# Images end up in output/<target>/images/tokibot-<target>.img.xz

PORT       ?= 8765
FAKE       ?=
GOTCHI     ?= http://192.168.77.1:8765
TOKEN      ?=
BATTERY    ?=
SIM_CONFIG ?= $(HOME)/.tokibot/tokibot.toml
BR_VERSION ?= 2026.02.3
BR_DIR     ?= $(CURDIR)/.buildroot
OUT        ?= $(CURDIR)/output
# Buildroot builds packages side by side (per-package directories in the defconfigs).
BR_JOBS    ?= $(shell nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)
BR_MAKE     = $(MAKE) -C $(BR_DIR) BR2_EXTERNAL=$(CURDIR)/os O=$(OUT)/$@

.PHONY: test test-site sim mockups figures faq social-pics bundle update zero2w zerow clean

test:
	cd app && python3 -m unittest discover -s tests

test-site:
	cd netlify && npm ci --no-audit --no-fund && npm test

# The simulator works on its own copy of the settings, so the settings page does not
# change the template in the repository.
sim:
	@mkdir -p $(dir $(SIM_CONFIG))
	@[ -f $(SIM_CONFIG) ] || cp os/board/tokibot/tokibot.toml $(SIM_CONFIG)
	cd app && python3 -m tokibot --sim --port $(PORT) --config $(SIM_CONFIG) $(if $(FAKE),--fake-peer $(FAKE)) $(if $(BATTERY),--battery $(BATTERY))

mockups:
	cd app && PYTHONPATH=. python3 tools/mockups.py ../docs/mockups.png ../docs/img/moods

figures:
	cd app && python3 tools/blueprints.py ../docs

faq:
	cd app && python3 tools/faq.py ../docs

social-pics:
	cd app && PYTHONPATH=. python3 tools/site_social.py ../docs

bundle:
	@mkdir -p $(OUT)
	cd app && python3 -m tokibot.update . $(OUT)/tokibot-app.tar.gz

update: bundle
	curl -fsS --data-binary @$(OUT)/tokibot-app.tar.gz -H 'X-Tokibot-Token: $(TOKEN)' \
		$(GOTCHI)/update; echo

# Depends on Buildroot's Makefile, not on the folder: the CI cache restores
# $(BR_DIR)/dl (the downloads) before Buildroot itself is there.
$(BR_DIR)/Makefile:
	rm -rf $(BR_DIR).clone
	git clone --depth 1 --branch $(BR_VERSION) https://gitlab.com/buildroot.org/buildroot.git $(BR_DIR).clone
	mkdir -p $(BR_DIR)
	cp -a $(BR_DIR).clone/. $(BR_DIR)/
	rm -rf $(BR_DIR).clone

zero2w zerow: | $(BR_DIR)/Makefile
	$(BR_MAKE) tokibot_$@_defconfig
	$(BR_MAKE) -j$(BR_JOBS)

clean:
	rm -rf $(OUT)
