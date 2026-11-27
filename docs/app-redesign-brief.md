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
