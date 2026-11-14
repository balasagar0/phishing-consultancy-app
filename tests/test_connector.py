"""The mail connector turns a reported email into events. The messages here are made up for the test; they are not real mail."""
import sys
from email.message import EmailMessage
from conftest import APP
sys.path.insert(0, str(APP / "connectors"))
from imap_connector import events_from_message


def suspicious():
    m = EmailMessage(); m["From"] = "Bank Support <alerts@secure-bank-verify.example>"; m["To"] = "ravi@client.example"; m["Subject"] = "Account locked"
    m.set_content("Your account is locked. Verify now at http://secure-bank-verify.example/login and http://secure-bank-verify.example/login."); return m


def test_forwarded_as_attachment_uses_the_forwarder_as_recipient():
    outer = EmailMessage(); outer["From"] = "Ravi <ravi@client.example>"; outer["To"] = "report-phishing@client.example"; outer["Subject"] = "Fwd: suspicious"
    outer.set_content("Please check the attached message."); outer.add_attachment(suspicious())
    rec, ev = events_from_message(outer.as_bytes())
    assert rec == "ravi@client.example"
    assert ev[0]["channel"] == "email" and ev[0]["subject"] == "Account locked" and ev[0]["identity"] == "alerts@secure-bank-verify.example"
    assert [e["text"] for e in ev[1:]] == ["http://secure-bank-verify.example/login"]          # links de-duplicated, trailing dot removed


def test_a_direct_message_uses_its_first_to_address():
    rec, ev = events_from_message(suspicious().as_bytes())
    assert rec == "ravi@client.example" and len(ev) == 2


def test_an_empty_message_gives_no_events():
    m = EmailMessage(); m["From"] = "x@client.example"; m["To"] = "y@client.example"
    assert events_from_message(m.as_bytes()) == (None, [])
