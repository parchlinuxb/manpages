SASS ?= sass

all: sass-output

.PHONY: sass-watcher
sass-watcher:
	@mkdir -p sass-output
	$(SASS) --watch sass/archlinux.scss:sass-output/archlinux.css sass/navbar.scss:sass-output/navbar.css

.PHONY: sass-output
sass-output: archlinux.css navbar.css base.css generic.css

%.css:
	@mkdir -p sass-output
	$(SASS) -t compressed sass/$(subst .css,.scss,$@) sass-output/$@

.PHONY:
clean:
	rm -rf sass-output
