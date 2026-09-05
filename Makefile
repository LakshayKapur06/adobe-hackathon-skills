# Convenience wrapper. The build gate is scripts/check.py; make is optional.
PYTHON ?= python

.PHONY: check list test
check:
	$(PYTHON) scripts/check.py

list:
	$(PYTHON) scripts/check.py --list

test:
	$(PYTHON) -m unittest discover -s tests -p "test_*.py"
