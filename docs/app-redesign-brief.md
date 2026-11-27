# Nyay Sahayak app — redesign brief (Gemini / kisi bhi designer ke saath baat ke liye)

## App kya hai
Nainital High Court (Uttarakhand) ke vakilon aur case ke paksh-kaaron (party) ke liye mobile-first web app (PWA, phone par "Add to Home screen").
Abhi: https://77sharmaakshay-byte.github.io/kv-sync/
Koi server nahi — GitHub roz cause list aur case data ki JSON files banata hai; app unhe padhta hai. Bhasha: Hinglish (Roman Hindi).

## Kaun use karta hai
1. **Vakil** (mukhya): roz subah dekhna — aaj mere kitne case, kis court mein, kaunsa item number, court abhi kis item par hai.
2. **Party** (aam aadmi): mera case kab laga, agli tareekh, kya order hua — saral bhasha mein.

## Abhi ke screen (tab)
Vakil: Aaj · Live · Cause list · Khoj · Mere cases · Main
Party: Mera case · Khoj · Cause list · Main
- **Aaj**: aaj/kal ke mere cases (naam se cause list mein dhoondh kar)
- **Live**: court abhi kis item number par (display board)
- **Cause list**: poori list, court-wise, search
- **Khoj**: vishay ke hisaab se purane faisle (jaise Compassionate appointment), keyword search
- **Mere cases**: saved cases, har case ki history, orders, agli tareekh
- **Case page**: parties, vakil, history, orders ke PDF
- **Main**: naam, role, apna AI model ka haal

## Data jo hamare paas hai (redesign mein use ho)
- Roz ki cause list (Nainital HC, saare court), 25+ din ki
- 6,000+ cases ki poori history aur orders
- Faislon ka database: ~2 lakh HC case, vishay/nateeja ki chhantai
- Har vakil ki A-Z list: kitne case, kis taraf, kis vishay, jeet/haar (sirf vakil ke apne liye — public ranking nahi, Bar Council Rule 36)
- Apna AI model (Nyay, Qwen 7B par train) — jald hi: faisle ka saar, mudde, nateeja

## Redesign ke lakshya (inpar Gemini se raay lo)
1. Vakil ke liye "aaj ka din" ek nazar mein: mere case, court, item, live board — kam se kam tap.
2. Live court se jodna: "mera item aane mein ~X item baaki" + notification.
3. Case page: timeline jaisa (tareekh → kya hua), orders ka AI saar.
4. Khoj: "mere case jaise purane faisle" — ek line likho, milte faisle + nateeja.
5. Vakil dashboard (private): apne cases vishay-wise, pending/disposed.
6. Party ke liye bahut saral: badi likhai, Hindi/Hinglish, "agli tareekh" sabse upar.
7. Bharosa: har AI jawab ke saath asli faisle ka link; "machine ka nateeja — jaanch karein".

## Naye section (user ne tay kiye, 27 Nov)
1. **Live court** (pehle se hai): kaunsa item chal raha hai — ise aur saaf, "mera item kitna door".
2. **Apna matter likho → research**: vakil apne case ke tathya / mudda likhe. App de:
   - **Paksh ke faisle** — jitne zyada mil sakein (har ek: case no., tareekh, judge, ek line kyun kaam ka, asli ansh + PDF)
   - **Khilaf ke faisle** — wahi format, aur kis aadhar par khilaf gaye
   - **Aakhir mein conclusion** — kaunsi dalil mazboot, kaunsa faisla sabse kareeb, kya dhyan rakhein (appeal/SLP ho to woh bhi)
   - Har baat ke saath asli faisle ka link; koi faisla ya quote banaya hua nahi
3. **Case search**: case number (jaise WPSS/557/2023) daalo → parties, vakil, judge, poori history, har order, agli tareekh, **PDF download**.
4. **Category section**: Bail, Criminal, Service, Land, Compassionate… har category mein:
   - us vishay ke faisle, nateeje ke hisaab se (paksh / khilaf / nipataara)
   - vakil ka record: kitne case, kitne paksh mein, kitne khilaf, kitne nipataara / vibhag vichaar
   - (Bar Council Rule 36: vakil ka record "best vakil" ranking ya prachaar jaisa na dikhe — design mein dhyan)

## Claude ke sujhav (aur section)
- **Meri diary / calendar**: mere saare case ki agli tareekhein ek calendar mein; ek din pehle aur subah reminder
- **Order aate hi suchna**: mere case mein naya order upload ho to notification + AI saar
- **Bench ka rukh**: is judge ne isi vishay (jaise bail, compassionate) mein pehle kya kiya — numbers + faisle
- **Drafting madad**: bail application, delay condonation, urgency application ke dhaanche (vakil khud bharega; tathya kabhi khud se nahi)
- **Limitation / court fee calculator**: appeal / revision ki aakhri tareekh, court fee
- **Saathi faisle**: ek faisla khola to "isse milte-julte faisle" aur "isko kisne follow / overrule kiya"
- **WhatsApp share**: case ka haal ya agli tareekh party ko ek tap mein
- **Awaaz se likhna (Hindi)**: matter bol kar likhna
- **Offline**: aaj ki list aur mere case bina internet bhi

## Takneeki zaroorat (Claude ka note)
- Section 2 (matter → paksh/khilaf/conclusion) ke liye ek search server + apna AI model chalana padega (abhi app bina server ke hai) — sabse sasta raasta Claude dhoondhega
- Section 3: eCourts se live case + PDF (kv-relay / case-lookup pehle se hain)
- Section 4: vakil A-Z aur vishay list pehle se ban chuki hai (data branch lists/vakil-sab/)

## Seemayein (design inke andar ho)
- Phone pehle (360 px chaudai), dhoop mein padhne layak contrast, light + dark mode
- Kamzor internet: offline cache, halka page (abhi koi framework nahi — plain HTML/CSS/JS)
- Hosting muft (GitHub Pages); koi login/server nahi — vakil ka naam sirf phone par
- Personal data / client documents app mein upload nahi
- Bar Council niyam: vakil ka prachaar/ranking public nahi

## Gemini se kya maangna hai
- 3 alag design disha (layout + rang + typography), har ek ke fayde-nuksaan
- Har screen ka wireframe (Aaj, Live, Case, Khoj, Mere cases)
- Navigation: kitne tab, kya naam
- Notification / reminder ka flow
Jo pasand aaye, woh Claude ko bhejo — Claude use code mein banayega aur live karega.
