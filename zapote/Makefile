.PHONY: setup build check qualify-buck engineering

HARNESS_DIR := ../harness-lab

setup:
	@echo "Zapote setup ready; active implementation remains $(HARNESS_DIR)"
	@echo "Shared Temper sources are available through project.toml"

build check qualify-buck engineering:
	$(MAKE) -C $(HARNESS_DIR) $@
