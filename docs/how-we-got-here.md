# Hvordan integrationen er nået hertil

En designhistorie for `lk_ihc`: hvad der blev bygget, i hvilken rækkefølge, og hvorfor hvert trin
var værd at tage. Den er samtidig referatet af to undersøgelser — en firmware-nedbrydning og en
API-vurdering — hvis største værdi var at fortælle os, hvad vi *ikke* skulle ændre.

## Udgangspunktet

Home Assistant har allerede en `ihc`-integration, skrevet og vedligeholdt af Jesper Nielsen
([dingusdk](https://github.com/dingusdk)), som også står bag IHC-sdk'et. Den virker, og den er udbredt, men den kan kun sættes op i YAML, opretter ingen enheder og mapper kun
udgange og sensorer. I et almindeligt IHC-hus betyder det, at lampeudtag og relæer dukker op som nøgne
entiteter, mens vægkontakterne, folk faktisk trykker på — den mest brugbare trigger, et IHC-hus har —
er usynlige.

`lk_ihc` blev bygget for at rette det, som et separat domæne der kører ved siden af det indbyggede,
så et hus i drift bliver ved med at virke, mens den nye integration sammenlignes med den gamle. Den
genbruger `ihcsdk` til SOAP-transporten og lægger en model ovenpå.

## Bygningen, version for version

- **v0.1.0** — fundamentet: en config flow i stedet for YAML, én enhed pr. produkt og en
  `event`-entitet for hver tast på hver vægkontakt. Skrivebeskyttet som standard, så et helt anlæg
  kan ses igennem, før Home Assistant får lov at tænde eller slukke noget.
- **v0.1.1** — en afvist kommando (skrivebeskyttet tilstand, eller en ressource der ikke findes i
  projektet) giver en oversat valideringsfejl i stedet for en server-traceback.
- **v0.1.2** — eget mærke-ikon og et diagram i README.
- **v0.2.0** — enheder, der læses som produkter og ikke varenumre: `model` er katalognavnet
  ("Dataline wall switch, 2 keys"), `model_id` er IHC-identifikatoren.
- **v0.2.1** — continuous integration (HACS Action + hassfest), prisen for at kunne indsendes til
  HACS' standardliste. `requirements_test.txt` blev samtidig gjort selvbærende; den manglede
  integrationens egne runtime-afhængigheder, så et frisk klon ikke kunne køre testene.
- **v0.3.0** — anlæggets egen logik, læst fra projektet: funktionsblokke og de links, der kobler en
  vægkontakt gennem en blok til et relæ. Entiteterne fik `ihc_controlled_by` og
  `ihc_function_block`, så et relæ, der skifter uden at Home Assistant har bedt om det, kan sige,
  hvad der flyttede det.
- **v0.4.0** — at læse det, vi ikke styrer. En skrivebeskyttet klient til de SOAP-tjenester, `ihcsdk`
  ikke dækker (AirlinkManagementService, TimeManagerService, konfigurationslæsningerne), vist i
  diagnostikken: trådløse enheder, controllerens ur, dens netværksindstillinger.
- **v0.5.0** — samme tilstand gjort synlig som entiteter frem for begravet i en diagnostikfil: elleve
  diagnostiksensorer på controller-enheden (trådløse antal og signal, urafvigelse, tidsserver,
  projektrevision, adresse, gateway, DNS).
- **v0.6.0** — controllerens logik-ressourcer: flag og enums, der kun lever inde i dens logik, som
  skrivebeskyttede diagnostik-entiteter (enums som sensorer, flag som binære sensorer, der er
  deaktiverede som standard).
- **v0.7.0** — handlinger, der sætter en ressource på dens nummer: `set_runtime_value_bool/int/
  float/timer/time` og `pulse`, med samme navne og felter som den indbyggede integrations services.
  Det lukkede det største funktionelle hul i forhold til Jesper Nielsens integration (se
  sammenligningen nedenfor). Skrivebeskyttelsen og projekt-afgrænsningen holder uændret; "kendte
  id'er" blev bare udvidet til alle ressourcer i projektet, så en funktionsbloks timer kan sættes,
  selvom den ingen entitet har.

## Undersøgelse 1 — firmware-nedbrydningen

Spørgsmålet var, om firmwaren gemte på en renere måde at tale med controlleren på. At komme ind i
den tog fire trin:

1. **`.fwf`-filen er fuldt krypteret.** Målt, ikke gættet: entropi 8,0000 over hele filen, ingen
   header, ingen magic, en længste streng på 15 tegn i 12,7 MB og nul gentagne blokke ud af 1,6
   millioner — hvilket udelukkede ECB og pegede på en strømkryptering.
2. **Nøglen lå i LK's Windows-software, ikke i controlleren.** `FirmwareLoader.exe` er en
   JSmooth-wrapper om en GCJ-bygget Java-app; den rigtige JAR ligger i dens `.rsrc`-sektion.
   Dekompileret lyder firmware-stien `EncryptedInputStream(Rc4Cipher(k.a())) -> ZipInputStream`, og
   `k.a()` returnerer en hardcodet 8-byte RC4-nøgle (`91 15 FE A8 0D 3B 7F 62`), den samme for alle
   controllere.
3. **RC4 med den nøgle gør filen til en ZIP.** Indeni: et manifest, installationsscripts, et
   rodfilsystem-overlay og controller-binæren.
4. **Hvad controlleren er:** en PowerPC 32-bit big-endian embedded Linux-boks, der kører en
   Java-applikation AOT-kompileret med GCJ 3.4.3. Den kablede bus (dataline) styres over i²c af en
   separat mikrocontroller; de trådløse enheder er PIC18F-chips, som et installationsscript flasher.
   Det fulde API er **tolv SOAP-tjenester, 216 operationer** — `ihcsdk` bruger fire, IHC Captain syv.

Nedbrydningen er skrevet fuldt op i `/workspace/ihc-firmware/FIRMWARE.md` og `FINDINGS.md` (uden for
dette repo, da den handler om enheden og ikke integrationen).

## Undersøgelse 2 — findes der et renere API?

Firmwaren afslørede en `openapi`-tjeneste (42 operationer), som LK byggede til tredjeparter, plus
tjenester `ihcsdk` aldrig har rørt. Den lignede et renere fundament, så den blev testet mod den
levende controller: `authenticate`, `getValues` (batch-læsning), `enableSubscription` +
`waitForEvents`, `setValues` — alt virkede.

Derefter blev hver eneste openapi-operation holdt op mod `ihcsdk`, og det ærlige resultat var:
**openapi tilbyder intet, som `ihcsdk` mangler.** Selv batch-læsning findes allerede
(`get_runtime_values`). openapi er en *tyndere* transport, ikke en rigere, og den har ingen
projektmodel — navnene, områderne, produkterne, koblingerne og diagnostikken, der gør denne
integration værd at have, kommer alt sammen fra at parse projektet, og det hjælper openapi ikke med.

En tidligere note i projektet kaldte `ihcsdk` "uvedligeholdt" og brugte det som argument for at
udskifte det. Det var forkert: `ihcsdk` havde en udgivelse i marts 2026, vedligeholdes aktivt af Jesper Nielsen —
samme mand som bag den indbyggede integration — og er afprøvet i tusindvis af huse. At bytte et sundt,
gennemtestet bibliotek ud med vores egen kode — på det, der styrer lyset — i bytte for ingenting: det
er en dårlig handel. **Transporten bliver på `ihcsdk`.**

Reglen, der afgjorde det, kom fra projektets ejer: *brug kun det nye, hvis det giver os noget, vi
ikke allerede har.* Det gjorde openapi ikke. Det, firmwaren *til gengæld* gav, var bekræftelsen af,
at flag og enums er adresserbare ressourcer — og det blev til v0.6.0.

## Hvor den står i forhold til alternativerne

| | indbygget `ihc` | `haihc-betatest` (forfatterens beta) | `lk_ihc` |
|---|---|---|---|
| Opsætning fra brugerfladen | nej | ja | ja |
| Enheder pr. produkt | nej | nej | ja |
| Taster på vægkontakter som hændelser | nej | nej | ja |
| Funktionsbloks-koblinger | nej | nej | ja |
| Diagnostik for trådløst / ur / netværk | nej | nej | ja |
| Flag og enums | nej | nej | ja |
| Handlinger på ressource-id (`set_runtime_value_*`, `pulse`) | ja | ja | ja, fra v0.7.0 |
| Transport | ihcsdk | ihcsdk | ihcsdk |

Forfatterens egen beta bruger samme parsing-tilgang, hvilket er en god bekræftelse af, at fundamentet
er rigtigt; `lk_ihc` går bare længere med projektmodellen.

## Bevidst ikke gjort

- **At udskifte transporten.** ihcsdk er sundt og afprøvet; openapi tilføjer intet (ovenfor).
- **At skrive til flag eller enums.** De er input til logik, controlleren kører; ihcsdk har ingen
  enum-sætter, og at skrive én ville række blindt ind i den logik. Eksponeret skrivebeskyttet.
- **Timere og scener som entiteter.** En timer læses som en nedtælling, der næsten altid er nul; en
  scene har ingen læsbar værdi. Ingen af dem er en entitet værd.
- **At uploade et projekt (`storeIHCProject`).** API'et understøtter det, men at ændre anlæggets
  logik fra Home Assistant er uden for scope og højrisiko.

## Huset, den blev bygget mod

Et levende anlæg på 38 produkter på controller med serienummer 1062 (en 2006-enhed, firmware 2.7.220
fra 2015): 17 funktionsblokke, 22 produkter med sporet kobling, 27 trådløse enheder, 2 enums, 15
flag. Ét fund gik tilbage til ejeren: controllerens ur går ~56 minutter bagud, med NTP slået til og
ikke virkende — nu synligt som sensoren `clock_offset`.
