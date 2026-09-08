"""Hand-written transcripts for evaluating the script channel offline.

Twenty short transcripts, ten scam and ten ordinary, roughly sixty words each.
The ordinary set is weighted toward genuine-urgent calls (a relative asking for
money, a real bank verification, a delivery running late), because those are the
false-positive risk: a naive detector trips on a real relative who genuinely
needs money today.

Not a benchmark. n=20, one author, English only. It exists so the question "how
do you know the script channel separates scam from ordinary" has a measured
answer, and so the two score ranges can go on a slide with n attached.

Each entry is wrapped in its own parentheses so a dropped comma cannot silently
concatenate two transcripts into one.
"""

from __future__ import annotations

SCAM_TRANSCRIPTS: tuple[str, ...] = (
    (  # bank fraud team, account frozen
        "Madam, this is the fraud department at your bank. Your account has been "
        "frozen after a suspicious transaction of forty thousand rupees. You must "
        "act now, there is no time to verify this at the branch. Do not hang up "
        "and do not call the bank yourself. Read me the OTP I just sent so I can "
        "block the transfer immediately."
    ),
    (  # arrest threat, agency impersonation
        "I am calling from the CBI cyber crime cell. Your Aadhaar is linked to a "
        "money laundering case and an arrest warrant has been issued. This is "
        "urgent. Do not disconnect the call and do not tell anyone in your "
        "family, this must stay confidential. To clear your name today, transfer "
        "the money in your savings account to the secure account I will provide."
    ),
    (  # CEO / senior executive transfer request
        "This is the CEO. I need you to handle a payment discreetly before the "
        "bank closes today. Keep this between us, no one else should know until "
        "the deal is announced. There is no time to check with finance. Transfer "
        "the amount to the vendor account I am sending now, this is urgent and "
        "cannot wait."
    ),
    (  # KYC expiry
        "Your bank KYC has expired and your account will be blocked within 24 "
        "hours. This is urgent. To keep it active, do not visit the branch, "
        "there is no time for that. Stay on the line and share the OTP and your "
        "UPI pin so our system can re-verify your details right now."
    ),
    (  # courier parcel / customs
        "This call is from the courier company and customs department. A parcel "
        "in your name contains illegal items and has been seized. Police will "
        "register a case unless you resolve this right now. Do not tell your "
        "family, keep this confidential. Transfer the fine through UPI to the "
        "officer's account immediately, and stay on the call while it processes."
    ),
    (  # electricity disconnection
        "This is from the electricity board. Your connection will be disconnected "
        "tonight because last month's payment failed. This is your final warning. "
        "There is no time to check at the office. To stop disconnection, pay now "
        "using the link I send on WhatsApp and read out the OTP you receive so I "
        "can confirm the payment right now."
    ),
    (  # refund / overpayment
        "Sir, we processed your refund but by mistake sent ninety thousand "
        "instead of nine thousand. My manager will lose his job over this. Please "
        "do not tell anyone, just help me quietly. Install the app I send, log in "
        "to your bank, and transfer the extra amount back right now. Do not hang "
        "up, I must stay with you until it is done."
    ),
    (  # lottery / prize
        "Congratulations, your number won the lucky draw for twenty five lakh "
        "rupees. To release the prize you must pay the government tax and "
        "processing fee today, before the offer expires. Do not share this with "
        "neighbours, winners are asked to keep it confidential. Send the fee by "
        "UPI right now and stay on the line while I book your claim reference."
    ),
    (  # loan / credit card
        "This is the manager from the loan department. Your pre-approved loan "
        "will be cancelled if you do not confirm within 10 minutes. Do not "
        "discuss this with anyone, it is a limited internal offer. There is no "
        "time to visit the branch. Just share the OTP and your card CVV so I can "
        "lock the interest rate for you right now."
    ),
    (  # tech support
        "I am calling from technical support. Your account has been suspended due "
        "to fraud on the line. Stay on the call, do not hang up or the connection "
        "is lost forever. This is urgent. Install the support tool I send and "
        "read out the banking OTP so we can verify ownership and restore the "
        "account right now."
    ),
)

NORMAL_TRANSCRIPTS: tuple[str, ...] = (
    (  # delivery call
        "Hello, I am calling about your parcel scheduled for delivery this "
        "afternoon. The courier will reach your address between two and four. "
        "Please keep someone available to receive and sign for it. If the time "
        "does not suit you, reschedule through the app or ask a neighbour to "
        "accept it. Have a good day."
    ),
    (  # clinic appointment
        "This is a reminder from the clinic about your appointment with the "
        "doctor tomorrow at eleven in the morning. Please come fifteen minutes "
        "early to finish the paperwork, and bring your earlier prescriptions. If "
        "you need to cancel or move it, call the reception during working hours. "
        "Rescheduling once is free of charge."
    ),
    (  # relative genuinely asking for money, urgent
        "Hey, it's me. I am a bit stuck, my card is not working at the workshop "
        "and I need to pay the mechanic today. It is about four thousand. Can you "
        "transfer the money to my account and I will pay you back this weekend "
        "once I am home? Sorry to trouble you. Call me if it does not go through."
    ),
    (  # genuine bank verification call
        "Good afternoon, I am calling from the bank to confirm a card purchase. "
        "We saw a payment of six thousand at an electronics shop this morning. If "
        "you made it, there is nothing to do. If not, please open the app or "
        "visit your branch to block the card. We will never ask for your PIN or "
        "OTP on this call."
    ),
    (  # friend in a hurry
        "Hey, are you coming tonight or not? We are booking the table and I need "
        "a final headcount soon. If you are bringing someone, tell me so I can "
        "inform the restaurant. Also, could you pick up the cake on the way, the "
        "shop is close to your place. Message me back when you know."
    ),
    (  # mutual fund courtesy call
        "This is a courtesy call from your mutual fund provider. Your annual "
        "statement is ready in the account portal. There are no pending actions "
        "on your folio. If you would like a printed copy by post, reply to the "
        "email we sent or call the helpline. Our office hours are ten to six on "
        "weekdays. Thank you."
    ),
    (  # colleague about a real deadline
        "The client moved the review to tomorrow morning, so we need the deck "
        "finished tonight. Can you take the first ten slides and I will handle "
        "the rest. Send me your part by nine and I will merge everything. If "
        "something is missing, we can note it in the meeting rather than hold the "
        "whole thing."
    ),
    (  # utility bill reminder
        "This is an automated reminder that your electricity bill for this month "
        "is due in three days. You may pay online, at the office, or through any "
        "authorised centre. If you have already paid, please ignore this message. "
        "For any billing question, use the customer care number printed on your "
        "bill."
    ),
    (  # doctor's office with results
        "Your test results are back and the doctor would like to go over them at "
        "a follow up visit. Nothing looks worrying, but he wants to adjust one "
        "medicine. Please book a slot this week through reception, and bring your "
        "current medicine boxes so we can check the dosage together."
    ),
    (  # genuine net-banking security alert
        "We noticed a sign in to your net banking from a new device today. If "
        "this was you, you can ignore this call. If it was not, please change "
        "your password in the official app and visit your home branch with an "
        "identity document. We are not asking you to share anything on this call."
    ),
)
