#
# (Re)builds API documentation
#
# Mark Huang <mlhuang@cs.princeton.edu>
# Copyright (C) 2006 The Trustees of Princeton University
#
# $Id: Makefile,v 1.2 2006/11/03 20:36:05 thierry Exp $
#

all: NMAPI.html end

.NMAPI.xml.valid: Methods.xml

Methods.xml: DocBook.py ../api_calls.py
	PYTHONPATH=..:../../../PLCAPI python $< > $@

#
# Documentation
#

# TODO: figure out where to put this command to strip out the unnecessary bits for PlanetLab Drupal page:
end:
	awk 'BEGIN { print "</DIV" } {n++; if ( n > 29 && $$0 != "></BODY" && $$0 != "></HTML" ) { print $$0 } }' NMAPI.html > out.html

# Validate the XML
.%.xml.valid: %.xml
	xmllint --valid --output $@ $<

# Remove the temporary output file after compilation
.SECONDARY: .%.xml.valid

# Compile it into other formats
FORMATS := dvi html man ps pdf rtf tex texi txt

DOCBOOK2FLAGS := -V biblio-number=1

define docbook2
%.$(1): %.xml .%.xml.valid
	docbook2$(1) --nochunks $$(DOCBOOK2FLAGS) $$<
endef

$(foreach format,$(FORMATS),$(eval $(call docbook2,$(format))))

clean:
	rm -f $(patsubst %,*.%,$(FORMATS)) .*.xml.valid Methods.xml

force:

.PHONY: force clean docclean