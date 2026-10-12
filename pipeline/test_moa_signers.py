"""Checks for reading the agency signer out of a 287(g) agreement's text."""
from moa_signers import parse, contact, clean_name

SIG = """By signing this MOA, each party represents it is fully authorized to enter into this MOA.

For the LEA:                                             For ICE:

Date:_ _2. _ /_z_/                                        2/10/26
Signature: - <                                           Signature:    u=_( ~
Name· Markus S. Solomon                                  Name: Charles Wall
Title: Chief of Police                                   Title: Deputy Director
"""
APP = """
APPENDIX A
POINTS OF CONTACT
   For the LEA:        Markus S. Solomon
                       Chief of Police
                       256-332-3567
"""
PAD = "\n" * 200


def test_signer_named_when_surname_repeats():
    assert parse(PAD + SIG + APP) == ("Markus S. Solomon", "Chief of Police", "named")


def test_signer_needs_second_mention():
    assert parse(PAD + SIG)[2] == "surname not found a second time in the agreement"


def test_ice_column_never_read():
    t = SIG.replace('Name· Markus S. Solomon', 'Name· ~e" 001l..')
    assert parse(PAD + t + APP)[0] == ""         # the ICE name on the same line is not taken instead


def test_ice_title_rejected():
    t = SIG.replace("Title: Chief of Police    ", "Title: Deputy Director    ")
    assert parse(PAD + t + APP)[0] == ""


def test_ice_official_rejected():
    t = SIG.replace("Markus S. Solomon", "Madison Sheahan")
    assert parse(PAD + t + APP.replace("Markus S. Solomon", "Madison Sheahan"))[2] == "an ICE signer's name"


def test_header_on_separate_lines():
    t = SIG.replace("For the LEA:                                             For ICE:", "For the LEA:\n\n                                                         For ICE:")
    assert parse(PAD + t + APP)[0] == "Markus S. Solomon"


def test_clean_name():
    assert clean_name("Eric Randall") == "Eric Randall"
    assert clean_name("Jo") == "" and clean_name("Riviera Beach Police Department") == "" and clean_name("John 2nd") == ""


def test_contact_from_appendix_a():
    assert contact(PAD + SIG + APP) == ("Markus S. Solomon", "Chief of Police")
    assert contact(PAD + APP.replace("Chief of Police", "Public Information Officer")) == ("", "")
    assert contact(PAD + APP.replace("Markus S. Solomon", "Chief William Rataczak").replace("Chief of Police", "PO Box 34")) == ("William Rataczak", "Chief")


def test_honorific_and_title_cleanup():
    t = SIG.replace("Name· Markus S. Solomon", "Name· Chief Markus S. Solomon").replace("Title: Chief of Police    ", "Title: chief of police    ")
    assert parse(PAD + t + APP)[:2] == ("Markus S. Solomon", "Chief Of Police") or parse(PAD + t + APP)[:2] == ("Markus S. Solomon", "Chief of Police")
    t2 = SIG.replace("Title: Chief of Police    ", "Title: William s County Sheriff")
    assert parse(PAD + t2 + APP)[2] == "title not legible"


def test_underscore_before_honorific():
    t = SIG.replace("Name· Markus S. Solomon", "Name: _Chief Markus S. Solomon")
    assert parse(PAD + t + APP)[0] == "Markus S. Solomon"
