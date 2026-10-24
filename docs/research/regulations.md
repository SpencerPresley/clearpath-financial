# Marketing compliance review: regulatory substance for AI pre-review rules

## What to know first

1. **Reg Z has no record retention rule for ads.** 12 CFR 1026.25(a) applies the 2-year rule to everything "other than advertising requirements under §§ 1026.16 and 1026.24." The retention rules that do cover ads come from other regulations: Reg N for mortgage ads, Reg B and FCRA for prescreened offers (see §7).
2. **The Reg B discouragement rule (1002.4(b)) was rewritten, effective July 21, 2026** (91 FR 21620). Anything citing the old text, including CFPB Supervisory Highlights Issue 24, quotes the version that has been replaced.
3. **The CFPB withdrew a batch of guidance in May 2025** (FR doc 2025-08286). Bulletin 2014-02 (credit card promotional APR marketing) and Circular 2024-01 (digital intermediaries and lead generators) are gone. **Bulletin 2016-02 (service providers) is not on the withdrawal list**, so it is still the CFPB's operative statement on third parties.
4. **Whether Reg N applies depends on whether the company is a bank.** Reg N covers only "persons over which the Federal Trade Commission has jurisdiction," which means nonbanks. My working assumption is that the fictional company is a nonbank. If it is a bank, Reg N drops out and FDIC/OCC advertising rules come in.

Sources: CFPB's interactive regulations (consumerfinance.gov), the eCFR API (current version as of 2026-10-01; the ecfr.gov HTML pages block automated fetches), govinfo.gov for the U.S. Code, and CFPB/FTC documents.

---

## 1. Reg Z advertising

**Who is covered.** "All persons must comply with the advertising provisions in §§ 1026.16 and 1026.24, not just those that meet the definition of creditor." The owner of the medium the ad runs in is exempt. Affiliates are not, so they are directly covered (comment 2(a)(2)-2). An "advertisement" is "a commercial message in any medium that promotes, directly or indirectly, a credit transaction." https://www.consumerfinance.gov/rules-policy/regulations/1026/2/

### Closed-end credit: personal loans and mortgages (1026.24)
https://www.consumerfinance.gov/rules-policy/regulations/1026/24/

- **Actually available terms, (a).** The ad may state "only those terms that actually are or will be arranged or offered." The commentary gives the example that a creditor "may not advertise a very low annual percentage rate that will not in fact be available at any time." This is the Reg Z hook for bait pricing.
- **Clear and conspicuous, (b).** For non-mortgage ads there is no type-size or placement rule (comment 24(b)-1). For dwelling-secured ads:
  - "Equal prominence" is deemed met by the same type size.
  - "Close proximity" is deemed met by "immediately next to or directly above or below… without any intervening text."
  - A footnote does not count as close proximity (comment 24(f)-2).
  - Internet ads must not be "obscured by techniques such as graphical displays, shading, coloration."
- **Rates, (c).** Any stated rate must appear as an "annual percentage rate," using that term. "APR" is allowed (comment 24(c)-1).
  - If the APR may increase after consummation, the ad must say so.
  - No other rate may be shown, except a simple annual or periodic rate, and only "in conjunction with, but not more conspicuously than, the annual percentage rate."
- **Trigger terms, (d)(1):**
  - (i) the amount or percentage of any downpayment
  - (ii) the number of payments or period of repayment
  - (iii) the amount of any payment
  - (iv) the amount of any finance charge
  - Triggers count when they are implied, e.g. "80 percent financing" implies a 20% down payment (comment 24(d)-1).
  - Commentary examples that trigger: "48-month payment terms," "30-year mortgage," "$25 weekly," "$500 total cost of credit," "2 points."
  - **Not triggers:** "no downpayment," "no closing costs," a bare APR, "pay weekly," "take years to repay."
- **Required disclosures when a trigger appears, (d)(2):**
  - (i) the downpayment
  - (ii) "terms of repayment, which reflect the repayment obligations over the full term of the loan, including any balloon payment"
  - (iii) the "annual percentage rate," using that term, and whether it may increase
- **Representative examples.** Ads may use illustrative transactions, but each "must be labeled as such and must reflect representative credit terms made available by the creditor" (comment 24(d)(2)-5).
- **Website tables, (e).** A rate table counts as part of the same ad only if every trigger term elsewhere "clearly refers to the page or location where the table or schedule begins," for example by a link.
- **Mortgage rates and payments, (f).**
  - If more than one rate applies over the loan term, the ad must show each rate, the period it applies, and the APR, with equal prominence and in close proximity.
  - A stated payment requires each payment amount and its period.
  - First-lien ads must also state that payments "do not include amounts for taxes and insurance premiums… and that the actual payment obligation will be greater."
  - Envelopes and linked banner or pop-up ads are excluded.
- **Prohibited in mortgage ads, (i).** (1) through (7) are the items in the regulation; the last bullet is from the 24(f) commentary.
  - (1) **"Fixed"**: an ARM ad may not use "fixed" unless "Adjustable-Rate Mortgage," "Variable-Rate Mortgage," or "ARM" appears before the first "fixed" and is at least as conspicuous. Each "fixed" also needs an equally prominent, adjacent statement of how long the rate is fixed and that it may vary afterward.
  - (2) Comparisons against a teaser rate or payment ("save $300 per month" is an implied comparison).
  - (3) "government loan program" or "government-supported loan," unless the loan really is FHA, VA, or similar.
  - (4) Using the consumer's current lender's name without an equally prominent advertiser name and a non-affiliation statement.
  - (5) Debt-elimination claims. The commentary's examples: "Wipe-Out Personal Debts!", "New DEBT-FREE Payment", "Set yourself free; get out of debt today", "Refinance today and wipe your debt clean!", "Get yourself out of debt * * * Forever!", "Pre-payment Penalty Waiver."
  - (6) "counselor" for a for-profit broker or creditor.
  - (7) Some trigger terms only in a foreign language and others only in English.
  - A rate or payment based on the index and margin is "reasonably current" if it was in effect within 60 days of mailing (direct mail) or 30 days (email or web).
- **Note:** the "fixed" prohibition in 1026.24 is limited to dwelling-secured credit. Reg Z has no specific "fixed" rule for personal-loan ads; a misleading "fixed" there falls under UDAAP.

### Open-end credit and credit cards (1026.16)
https://www.consumerfinance.gov/rules-policy/regulations/1026/16/

- **Trigger, (b)(1).** "Any term required to be disclosed under § 1026.6(b)(3) set forth affirmatively or negatively" triggers disclosures. Those terms are finance charges and other plan charges: late, over-limit, and termination fees, and voluntary credit insurance (https://www.ecfr.gov/current/title-12/section-1026.6).
  - **Negative statements trigger here, unlike in closed-end:** "if a creditor states no interest or no annual membership fee… additional information must be provided" (comment 16(b)(1)-1).
  - "No interest charges until May" triggers; "you won't be billed until May" does not (comment 16(b)(1)-4).
- **Required disclosures:**
  - (i) any minimum, fixed, transaction, or activity charge that is a finance charge
  - (ii) any periodic rate expressed as an APR, and whether it is variable
  - (iii) any membership or participation fee
- **"Fixed," (f).** An APR may not be called "fixed" unless the ad specifies the period it is fixed. If no period is given, the rate must not increase while the plan is open.
- **Promotional rates, (g).**
  - "introductory" or "intro" must be "in immediate proximity to each listing" of an introductory rate or fee. Same phrase counts as immediate proximity.
  - When the promotion ends and the post-promotion APR must appear "closely proximate to the first listing."
- **Deferred interest, (h).**
  - "if paid in full" must precede the deferred-interest period.
  - The period must be in immediate proximity to each "no interest," "no payments," "deferred interest," or "same as cash."
  - The ad must also say that interest is charged from the purchase date if the balance is not paid in full.

## 2. Mortgage-specific rules

**Reg N / MAP Rule, 12 CFR 1014** (nonbanks only, per §1014.1). https://www.ecfr.gov/current/title-12/part-1014

Section 1014.3 prohibits "any material misrepresentation, expressly or by implication" about any term. The listed categories are:
- (a) interest
- (b) APR or any other rate
- (c) fees, "including… that no fees are charged"
- (d) add-on products such as credit insurance
- (e) taxes and insurance
- (f) prepayment penalties
- (g) variability, "including… the word 'fixed'"
- (h) comparisons against teaser rates or payments
- (i) product type, including "fully amortizing"
- (j) amount of cash or credit available
- (k) payments
- (l) default risk
- (m) debt relief
- (n) government affiliation, "including… formats, symbols, or logos that resemble"
- (o) the ad's source, e.g. impersonating the consumer's current lender or servicer
- (p) right to reside in the home
- (q) "whether the consumer has been preapproved or guaranteed"
- (r) refinance or modification likelihood
- (s) counseling

Enforcement example: in Prime Choice Funding (2020), the CFPB treated "You have been pre-selected for a U.S. [VA program]" as misleading because the company "did not have specific information" about the recipients' finances. https://files.consumerfinance.gov/f/documents/cfpb_prime-choice-funding_consent-order_2020-07.pdf

**Equal Housing logo: there is no federal ad-logo mandate for a nonbank that I could find.**
- HUD's fair housing advertising rule, 24 CFR Part 109, was removed in 1996 (61 FR 14378, https://www.govinfo.gov/content/pkg/FR-1996-04-01/html/96-7786.htm). The current eCFR has no Part 109.
- 24 CFR 110 is a poster rule.
- 24 CFR 100.75 prohibits ads that indicate a "preference, limitation or discrimination," including through "photographs, illustrations, symbols." Its subsection (d) still points to Part 109 as guidance. https://www.ecfr.gov/current/title-24/section-100.75
- The ad-logo requirement that does exist is bank-specific. FDIC 12 CFR 338.3 requires FDIC-supervised institutions to "prominently indicate" non-discrimination in dwelling-loan ads, "directly or through third parties." Written ads can meet it with the Equal Housing Lender or Equal Housing Opportunity logo; oral ads with the spoken phrase "Equal Housing Lender." https://www.ecfr.gov/current/title-12/part-338
- Unverified: whether HUD Handbook 4000.1 imposes a logo requirement on FHA-approved mortgagees.
- **Treat the logo as a policy or state-law check, not a federal rule.**

**NMLS ID: the federal rules do not reach ads; state rules do.**
- Federal:
  - 12 CFR 1026.36(g) requires the NMLS ID on the credit application, the Loan Estimate and Closing Disclosure, the note, and the security instrument. It does not cover ads. https://www.ecfr.gov/current/title-12/section-1026.36
  - 12 CFR 1007.105 (bank MLOs) requires the ID "through the originator's initial written communication." https://www.ecfr.gov/current/title-12/section-1007.105
  - 12 CFR 1008 (state SAFE Act licensing) defines MLO activity to include advertising but sets no ad-display rule.
- State example (verified): Virginia 10VAC5-160-60 requires "NMLS ID #" followed by the number and the NMLS Consumer Access URL in every ad; on radio and TV it must follow the company name. https://law.lis.virginia.gov/admincode/title10/agency5/chapter160/section60/
- Illinois (38 Ill. Adm. Code 1050.940) and Ohio (OAC 1301:8-7-07) have similar rules. I saw these only in search snippets and did not verify the text.

## 3. FCRA prescreened firm-offer notice (12 CFR 1022.54)
https://www.consumerfinance.gov/rules-policy/regulations/1022/54/

Every written prescreened solicitation needs both a short and a long notice, in the same language as the offer.

**Short notice:**
- Content: states the opt-out right and gives the toll-free number; points to where the long notice is and states its heading; "shall not contain any other information."
- Type size: larger than the principal text and never under 12-point.
- Placement: on the front of the first page of the principal promotional document (electronic: same page as the main marketing message and close to it).
- Visually distinct from surrounding text (e.g. a border) and in a distinct type style.

**Long notice:**
- Content: the 15 U.S.C. 1681m(d) items:
  - the consumer report was used
  - the consumer was selected because they met the criteria
  - the offer may not be extended if the consumer no longer meets the criteria or does not provide collateral
  - the right to opt out
  - how to opt out, with the notification system's address and toll-free number (https://www.govinfo.gov/content/pkg/USCODE-2023-title15/html/USCODE-2023-title15-chap41-subchapIII-sec1681m.htm)
- Form: no smaller than the principal text and at least 8-point; heading "PRESCREEN & OPT-OUT NOTICE" in capitals and underlined; distinct type style; set apart by blank lines and indented margins.

The model notices in Appendix D are images, not text: https://www.consumerfinance.gov/rules-policy/regulations/1022/D/

## 4. UDAAP marketing pitfalls

Statutory basis: 12 U.S.C. 5536(a)(1)(B) makes UDAAP unlawful for covered persons and service providers, and (a)(3) makes "knowingly or recklessly" giving substantial assistance a violation too. https://www.govinfo.gov/link/uscode/12/5536?type=usc&year=mostrecent&link-type=html

Each finding below comes from a primary CFPB source:

- **"No credit check."** Lenders that "falsely represented on storefronts and in photos on proprietary websites that they would not check a consumer's credit history" were found deceptive (Supervisory Highlights Issue 24, §2.8.2). https://files.consumerfinance.gov/f/documents/cfpb_supervisory-highlights_issue-24_2021-06.pdf
- **"As low as" pricing.** Advertising rates "as low as" X% while leaving out that the rate depends on creditworthiness was found deceptive. The fix was to show the full range ("X.XX% – YY.YY%") and disclose that the lowest rates go only to the most creditworthy applicants (Issue 24, §2.9.1; the finding was about private student loans, but the principle carries over).
- **Bonus offers not honored.** Credit card bonus ads were deceptive where issuers failed to pay the advertised bonuses (Issue 25). https://files.consumerfinance.gov/f/documents/cfpb_supervisory-highlights_issue-25_2021-12.pdf
- **Preapproved or guaranteed (mortgage).** Covered by 1014.3(q) and the Prime Choice order above. **For personal loans and cards I found no CFPB finding** specifically on "guaranteed approval"; it would rest on general deception plus the 1026.24(a) "actually available" rule.
- **"Won't affect your credit score."** **I found no CFPB or FTC enforcement action on this claim.** The claim needs substantiation: CFPB consumer guidance says soft inquiries don't lower scores while hard inquiries "can affect" them (https://www.consumerfinance.gov/ask-cfpb/what-is-a-credit-inquiry-en-1317/). So the claim is true only if the application step uses a soft pull and the copy limits the claim to that step. The closest finding is the "no credit check" one above.
- **Undisclosed paid endorsements.** In NewDay Financial (2015), the lender was found deceptive for "failing to disclose payments to a veteran's organization that endorsed Respondent." https://files.consumerfinance.gov/f/201502_cfpb_consent-order_newday-financial.pdf The FTC's Endorsement Guides (16 CFR 255.5) require clear and conspicuous disclosure of material connections, which covers affiliates and influencers. https://www.ecfr.gov/current/title-16/section-255.5

## 5. ECOA / Reg B discouragement, 1002.4(b) (current text, effective 2026-07-21)
https://www.consumerfinance.gov/rules-policy/regulations/1002/4/ · Final rule: https://www.federalregister.gov/documents/2026/04/22/2026-07804/equal-credit-opportunity-act-regulation-b

- **Rule:** no statement "in advertising or otherwise" that the creditor "knows or should know would cause a reasonable person to believe that the creditor would deny, or would grant on less favorable terms," an application "because of the applicant or prospective applicant's prohibited basis characteristic(s)."
- **Statements explicitly include** "visual images such as symbols, photographs, or videos."
- **New commentary:**
  - Statements encouraging one group to apply "cannot discourage other consumers."
  - Affirmative outreach to "traditionally disadvantaged groups" remains permitted.
- The pre-amendment exam finding in Issue 24 §2.5.5 involved mailers with models "all of whom appeared to be non-Hispanic white" and headshots of loan officers that were nearly all white. Under the new standard, this is still a useful reviewer prompt, but the legal test has changed.

## 6. TCPA (SMS) and CAN-SPAM (email)

**TCPA, 47 CFR 64.1200.** https://www.ecfr.gov/current/title-47/section-64.1200
- **Consent:** autodialed or prerecorded marketing calls and texts to wireless numbers require "prior express written consent," (a)(2).
- **What the consent must say, (f)(9):** the signed agreement must:
  - identify the number
  - authorize the seller to send marketing calls or texts using an autodialer or prerecorded voice
  - disclose clearly and conspicuously that consent is "not required… as a condition of purchasing."
  - The current text has no one-to-one (single-seller) consent requirement.
- **Revocation, (a)(10):**
  - Revocation can be by "any reasonable method."
  - Replies of "stop," "quit," "end," "revoke," "opt out," "cancel," or "unsubscribe" are reasonable per se, and other wording counts if a reasonable person would read it as a revocation.
  - Revocations must be honored within 10 business days, and the sender may not require one exclusive way to opt out.
  - One confirmation text is allowed if it contains no marketing, (a)(12).
- **Quiet hours:** no telephone solicitations before 8 a.m. or after 9 p.m. at the called party's local time, (c)(1).
- **Do Not Call:** National Do Not Call registrations must be honored, (c)(2).

**CAN-SPAM, 15 U.S.C. 7704 / 16 CFR 316.** https://www.govinfo.gov/content/pkg/USCODE-2023-title15/html/USCODE-2023-title15-chap103-sec7704.htm · https://www.ecfr.gov/current/title-16/part-316
- No misleading subject lines.
- Each commercial email needs:
  - clear identification as an advertisement (not needed with prior affirmative consent)
  - notice of the opt-out
  - a valid physical postal address: street address, registered PO box, or registered private mailbox (316.2(p))
- The opt-out must keep working for 30 days after sending; requests must be honored within 10 business days; no fee can be charged to opt out (316.5).
- **Affiliate liability:** "initiate" includes "procure," meaning "intentionally to pay or provide other consideration to, or induce, another person to initiate such a message on one's behalf" (7702(9), (12)). Under that definition, an affiliate email the lender pays for is legally the lender's email.

## 7. Record retention

- **Reg Z 1026.25(a):** 2 years, but advertising is explicitly excluded. https://www.consumerfinance.gov/rules-policy/regulations/1026/25/
- **Reg N 1014.5 (mortgage, nonbank):** 24 months from the last date the ad was disseminated. Must keep:
  - copies of all materially different ads, sales scripts, training materials, and marketing materials
  - documents showing every mortgage product and term available at the time
  - documents on add-on products
  - Failing to keep these is itself a violation.
- **Reg B 1002.12(b)(7) (prescreened offers):** 25 months after the offer. Must keep the solicitation text, the selection criteria, and complaint correspondence. https://www.ecfr.gov/current/title-12/section-1002.12
- **FCRA 1681m(d)(3):** selection and creditworthiness criteria and collateral requirements kept for 3 years from the offer.
- **TCPA consent and CAN-SPAM:** I found no retention rule in either regulation. Keeping consent records is still necessary to prove consent in litigation; how long to keep them is a judgment call, not a rule.
- **Tracker design point:** the 24-month clock runs from the last dissemination date, not the approval date. The tracker therefore needs a "last run date" per ad version.

## 8. Third-party, affiliate, and lead-generator responsibility

- **Bulletin 2016-02 (still in effect).** It says a service-provider relationship "does not absolve the supervised bank or nonbank of responsibility," and that "legal responsibility may lie with the supervised bank or nonbank as well as with the supervised service provider." The CFPB expects:
  - due diligence
  - review of the provider's policies, training, and controls
  - contract terms with compliance expectations and "enforceable consequences"
  - ongoing monitoring
  - prompt corrective action, including termination
  - Bulletin page: https://www.consumerfinance.gov/compliance/supervisory-guidance/compliance-bulletin-and-policy-guidance-2016-02-service-providers/
  - PDF: https://files.consumerfinance.gov/f/documents/102016_cfpb_OfficialGuidanceServiceProviderBulletin.pdf
  - It amends and reissues Bulletin 2012-03.
- **Most direct finding on partner ads (Issue 37, Winter 2024, BNPL).** Merchant-partner sites advertised wrong loan costs. Because "the lenders exercised control and approval rights over these advertisements," the lenders themselves "engaged in a deceptive act or practice." The remedy was to "enhance[] the marketing review process across merchant partners." https://files.consumerfinance.gov/f/documents/cfpb_Supervisory-Highlights-Issue-37_Winter-2024.pdf
- **Enforcement:**
  - Prospect Mortgage (2017): RESPA §8 violation for paying per lead and under marketing services agreements in exchange for referrals. https://files.consumerfinance.gov/f/documents/201701_cfpb_ProspectMortgage-consent-order.pdf
  - Zero Parallel (2017): a lead aggregator selling leads to small-dollar and installment lenders, including for consumers in states where the loans were void. https://files.consumerfinance.gov/f/documents/201709_cfpb_zero-parallel-llc_consent-order.pdf
  - NewDay (2015): see §4.
- **Withdrawn (May 2025):** Circular 2024-01 (lead-gen steering), the 2022 interpretive rule narrowing the "time or space" exception for digital marketers, and Bulletin 2014-02 (promotional APR marketing). https://www.federalregister.gov/documents/2025/05/12/2025-08286/interpretive-rules-policy-statements-and-advisory-opinions-withdrawal The statutory "time or space" exception, 12 U.S.C. 5536(b), still applies.

---

## Rule checks for an automated pre-reviewer

| # | If the copy… | Then require or flag | Source |
|---|---|---|---|
| 1 | Is closed-end and has a payment amount, a term ("60 months," "5-year"), a down payment, or a dollar finance charge (including implied ones) | The word "APR" (or "annual percentage rate"), full-term repayment terms, the down payment if any, and "may increase" if the rate is variable | 1026.24(d) |
| 2 | Shows any rate | The rate is labeled "APR"; any other rate (e.g. "interest rate") is no more prominent than the APR; personal loans also allow a periodic rate; mortgage ads only a simple annual rate | 1026.24(c) |
| 3 | Uses "as low as," "starting at," or "rates from" | A range or full rate band plus a creditworthiness qualifier; check the advertised rate against the current rate sheet | 1026.24(a) / 1026.16(a); SH Issue 24 §2.9.1 |
| 4 | Is a credit card ad that states a rate or fee, or says "no annual fee" / "no interest" | APR (with variable flag), finance charges, and membership fee | 1026.16(b)(1) + comment 1 |
| 5 | Has a card intro rate | "intro" / "introductory" in the same phrase as the rate; end date and go-to APR near the first mention | 1026.16(g)(3)–(4) |
| 6 | Says "no interest," "same as cash," or "deferred interest" | "if paid in full" before the period; G-24-style warning that interest is charged from the purchase date | 1026.16(h) |
| 7 | Says "fixed" | Mortgage ARM: "ARM" or "Adjustable-Rate Mortgage" before the first "fixed" plus the fixed period. Card: the fixed period. Personal loan: confirm the product is actually fixed | 1026.24(i)(1); 1026.16(f); 1014.3(g) |
| 8 | Is a first-lien mortgage ad with a payment amount | All payment streams and periods, plus "does not include taxes and insurance; actual payment will be greater," adjacent and not in a footnote | 1026.24(f)(3), comment 24(f)-2 |
| 9 | Is a mortgage ad using "government," "FHA," "VA," "HUD," or a seal or eagle image; a competitor or servicer name; "counselor"; or debt-wipe phrases | Block unless it is actually an FHA/VA product; current-lender name needs a non-affiliation statement; phrase list from comment 24(i)-3 | 1026.24(i)(3)–(6); 1014.3(m)–(o) |
| 10 | Says "pre-approved," "pre-selected," "guaranteed," or "you qualify" | Block unless it is a prescreened firm offer backed by selection criteria; mortgage version is an express violation | 1014.3(q); Prime Choice order |
| 11 | Says "no credit check" or "won't affect your credit score" | Require evidence of the underwriting pull type; limit the claim to the soft-pull step | SH Issue 24 §2.8.2; CFPA 1036 |
| 12 | Is a prescreened mailer or email | Short notice (≥12pt, front page, bordered, toll-free number, points to long notice) plus long notice headed "PRESCREEN & OPT-OUT NOTICE" (≥8pt, set apart) | 1022.54(c) |
| 13 | Is a mortgage ad in a licensed state | "NMLS ID #" + number + nmlsconsumeraccess.org, using a per-state rule table | 10VAC5-160-60 (VA); other states unverified |
| 14 | Is an SMS campaign | Consent record on file with "not a condition of purchase" language; STOP/QUIT/END/REVOKE/OPT OUT/CANCEL/UNSUBSCRIBE handling; send window 8am–9pm recipient local time | 47 CFR 64.1200(a)(2), (a)(10), (c)(1), (f)(9) |
| 15 | Is a marketing email (including affiliate emails) | Identified as an ad, opt-out link, physical postal address, subject line consistent with body | 15 U.S.C. 7704(a); 7702(12); 16 CFR 316 |
| 16 | Is an affiliate, influencer, or social creative | Material-connection disclosure ("#ad," "paid partner"); routed through the same rules as first-party copy | 16 CFR 255.5; 1026.2(a)(2) cmt 2; SH Issue 37 |
| 17 | Contains images or photos of people, or geographic targeting | Human-review flag for discouragement on a prohibited basis | 1002.4(b) (2026 text) |
| 18 | Every approved asset | Store each materially different version, the product terms valid at the time, and the last dissemination date; retain 24 months after last run (mortgage) or 25 months / 3 years (prescreen) | 1014.5; 1002.12(b)(7); 1681m(d)(3) |

## Open questions for Spencer

1. Is the fictional company a nonbank or a bank? This decides whether Reg N or FDIC 338.3 applies.
2. Which states should the demo cover for NMLS and state ad rules? Only Virginia is verified so far.
3. Is the company an FHA-approved mortgagee? If so, HUD Handbook 4000.1 needs a check for an ad or logo requirement.
