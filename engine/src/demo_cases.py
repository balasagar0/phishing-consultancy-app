"""The eight demo cases TC-01 to TC-08. HAND-WRITTEN, NOT A TEST SET: never compute a rate from them and never train on them.
Before this file they lived only in PROJECT_STATE.md (15 Oct) and in the presets of tests/test_window_and_ids.py and the console.
The messages are the ones v2 was demonstrated with; each case is a /correlate request body (TC-03 is a call, which v2 cannot assess).
Used by tests/test_demo_cases.py, the console presets, scripts/preflight.py and scripts/benchmark.py."""
import copy

KYC_SMS = dict(channel="sms", text="Dear customer, your SBI account will be blocked today. Update your KYC now at http://sbi-kyc-update.top/verify-now.php or call 9876543210", identity="+91 98765 43210", time="0")
KYC_URL = dict(channel="url", text="http://sbi-kyc-update.top/verify-now.php", time="4")
KYC_EMAIL = dict(channel="email", text="Dear customer, your bank account has been suspended. Verify your password within 24 hours at http://sbi-kyc-update.top/verify-now.php or your account will be closed.", subject="Urgent: account suspended", time="12")

BENIGN = [dict(channel="sms", text="Hey, can we move our project meeting to 4 pm tomorrow? I will email you the notes and an article on planning.", identity="+91 90000 11111", time="0"),
          dict(channel="email", text="Thanks for confirming. I wrote up the notes from yesterday. The article I mentioned is at https://en.wikipedia.org/wiki/Project_management if you want to read it. Call me tomorrow if anything changes.", subject="Re: project meeting", time="6"),
          dict(channel="url", text="https://en.wikipedia.org/wiki/Project_management", time="10")]
WEAK = [dict(channel="sms", text="Hello, there is a problem with your delivery address. Update it at parcel-redelivery.info/confirm today", time="0"),
        dict(channel="url", text="http://parcel-redelivery.info/track?id=88213", time="7"),
        dict(channel="email", text="Hello, we could not deliver your parcel today because the address on the label is incomplete. Please confirm your address at http://parcel-redelivery.info/confirm so we can try again. Thank you.", subject="Delivery problem with your parcel", time="15")]
COURIER = [dict(channel="sms", text="Your package will arrive tomorrow between 10 and 2. Track it at https://www.fedex.com/fedextrack/?trknbr=123456789012", identity="FedEx", time="0"),
           dict(channel="email", text="Hi, your FedEx shipment 123456789012 is on its way and will arrive tomorrow. You can follow it at https://www.fedex.com/fedextrack/?trknbr=123456789012. Thanks for shipping with us.", subject="Your shipment is on the way", time="10")]
CALL = dict(channel="call", text="Caller said he was from the bank's KYC desk and asked for the OTP sent to my phone to stop the account being blocked.", identity="+91 98765 43210", time="0")


def retime(ev, times):
    out = copy.deepcopy(ev)
    for e, t in zip(out, times): e["time"] = str(t)
    return out


CASES = {
    "TC-01": {"name": "Phishing email alone", "events": [dict(KYC_EMAIL, time="0")]},
    "TC-02": {"name": "Smishing SMS alone", "events": [dict(KYC_SMS)]},
    "TC-03": {"name": "Voice call (not assessed: no voice detector)", "events": [dict(CALL)]},
    "TC-04": {"name": "SMS + URL + email on one domain, 12 min", "events": [dict(KYC_SMS), dict(KYC_URL), dict(KYC_EMAIL)]},
    "TC-05": {"name": "A colleague shares an article, 10 min", "events": copy.deepcopy(BENIGN)},
    "TC-06": {"name": "Weak parcel campaign, 15 min", "events": copy.deepcopy(WEAK)},
    "TC-07": {"name": "TC-06's messages, 3 days apart", "events": retime(WEAK, [0, 4320, 8640])},
    "TC-08": {"name": "Courier SMS + email sharing a tracking number", "events": copy.deepcopy(COURIER)},
}


def case(cid):
    """A deep copy of one case, so callers can change it freely."""
    return copy.deepcopy(CASES[cid])


# Four Indian stories for the console (R3-13). HAND-WRITTEN, NOT A TEST SET: written the way a real sender would write them, run once, and
# kept with whatever they score (rule 2). The hosts are made up; do not open them. IN-04 is a legitimate order that should stay quiet.
STORIES = {
    "IN-01": {"name": "KYC freeze (SMS, link, call)", "note": "A bank KYC freeze threat by SMS, its link, then a caller asking for the OTP. The call is not assessed.", "events": [
        dict(channel="sms", text="Dear Customer, Your SBI YONO account will be blocked today. Please update your PAN card immediately. Click here http://yono-sbi-kyc.co.in/pan-update", identity="VM-SBIUPD", time="0"),
        dict(channel="url", text="http://yono-sbi-kyc.co.in/pan-update", time="3"),
        dict(channel="call", text="Caller said he is from SBI head office and asked me to share the OTP to complete my KYC.", identity="+91 82104 66391", time="20")]},
    "IN-02": {"name": "Courier customs fee (SMS, email, link)", "note": "A small customs fee by SMS and a larger one by email, both pointing to the same payment page.", "events": [
        dict(channel="sms", text="India Post: Your parcel is held at customs due to unpaid duty of Rs 48. Pay within 24 hrs or it will be returned: https://indiapost-customs-fee.top/pay", identity="+91 74285 51902", time="0"),
        dict(channel="email", subject="Customs clearance pending for your international shipment",
             text="Dear customer, your shipment from abroad has arrived at Mumbai customs. A clearance fee of Rs 2,499 must be paid before delivery. Pay securely at https://indiapost-customs-fee.top/pay. For help call +91 7428551902.", time="25"),
        dict(channel="url", text="https://indiapost-customs-fee.top/pay", time="27")]},
    "IN-03": {"name": "Work-from-home task scam (SMS, email)", "note": "A part-time 'like videos' job by SMS, then an email asking for a deposit to withdraw earnings. Linked by the WhatsApp number.", "events": [
        dict(channel="sms", text="Hi, I am Priya from Amazon HR team. Earn Rs 3000-8000 daily from home by liking YouTube videos. Part time job, no investment. Reply on WhatsApp +91 98123 45670", time="0"),
        dict(channel="email", subject="Your task payment is ready",
             text="Congratulations! You completed 3 tasks and earned Rs 450. To unlock the premium task group and withdraw your earnings, deposit Rs 2,000 to start. Contact your mentor on WhatsApp: +91 98123 45670", time="40")]},
    "IN-04": {"name": "Legitimate order (should stay quiet)", "note": "A real-looking shipping SMS, its order email and the order page. Nothing here should alert.", "events": [
        dict(channel="sms", text="Shipped: Your Amazon order for boAt Rockerz 450 will be delivered by Thursday. Track: https://amzn.in/d/2bX9Kq1", identity="AX-AMAZON", time="0"),
        dict(channel="email", subject="Your Amazon.in order #403-5523718-2265912 has shipped",
             text="Hello, your package has been shipped and is on the way. Arriving Thursday. You can track your package from Your Orders on Amazon.in. Thank you for shopping with us.", time="2"),
        dict(channel="url", text="https://www.amazon.in/gp/your-account/order-history", time="5")]},
}


def presets():
    """Everything the console offers as one-click presets, each marked hand-written."""
    return [{"id": k, **copy.deepcopy(v), "kind": "demo case" if k.startswith("TC") else "Indian story", "label": "hand-written, not a test set"}
            for k, v in list(CASES.items()) + list(STORIES.items())]
