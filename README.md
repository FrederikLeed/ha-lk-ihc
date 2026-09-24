# LK IHC til Home Assistant

<img src="custom_components/lk_ihc/brand/icon.svg" alt="LK IHC" width="110" align="right">

En Home Assistant-integration til LK IHC-controllere, der sættes op fra brugerfladen, giver hvert
produkt sin egen enhed og viser det, den indbyggede integration udelader: **tasterne på
vægkontakterne**.

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/overview-dark.svg">
  <img alt="Controlleren logges på fra brugerfladen og sender sit projekt; grupper bliver til områder, produkter til enheder og ressourcer til entiteter; Home Assistant får lys, kontakter, binære sensorer, sensorer og en hændelses-entitet for hver tast på hver vægkontakt. Skrivebeskyttet indtil du siger andet." src="docs/img/overview-light.svg">
</picture>

## Hvorfor

Home Assistant har allerede en `ihc`-integration. Den virker, og denne her skylder den det meste af
det, den ved om IHC-produkter. Men den kan kun sættes op i YAML, den har ingen vedligeholder, den
opretter ingen enheder, og den mapper kun udgange og sensorer. I et almindeligt hus betyder det, at
lampeudtag og relæer dukker op — og at de elleve vægkontakter, folk faktisk trykker på, ikke gør.

Denne integration:

- tilføjes fra **Indstillinger > Enheder og tjenester**, helt uden YAML,
- læser projektet fra controlleren og laver **én enhed pr. produkt**, navngivet og placeret som
  IHC-projektet har det, så entiteterne lander i de rigtige områder,
- opretter en **hændelses-entitet for hver tast** på hver vægkontakt, så et tryk kan starte en
  automatisering, mens tasten stadig gør det, anlægget i forvejen bruger den til,
- starter **skrivebeskyttet**, så du kan se hele anlægget igennem, før Home Assistant får lov at
  tænde eller slukke noget i det,
- bruger et **separat domæne** (`lk_ihc`), så den kan køre ved siden af den indbyggede
  `ihc`-integration, mens du sammenligner dem — intet, der virker i dag, skal slukkes først.

## Det denne gør, som den indbyggede `ihc` ikke gør

Begge taler med den samme controller over det samme SOAP-API. Forskellen er, hvor meget af anlægget
de lader dig se.

| | indbygget `ihc` | `lk_ihc` |
|---|---|---|
| Opsætning | kun `configuration.yaml` | Indstillinger → Enheder og tjenester |
| Enheder | ingen | én pr. produkt, 38 i huset herunder |
| Taster på vægkontakter | ikke eksponeret | en `event`-entitet pr. tast |
| Produktnavne | ressourcenumre | katalognavne, fx "Dataline wall switch, 2 keys" |
| Områder | tildeles manuelt | foreslås ud fra IHC-grupperne |
| Skrivebeskyttet tilstand | nej | ja, og det er standard |
| Hvad der styrer en udgang | ikke tilgængeligt | `ihc_controlled_by` og `ihc_function_block` |
| Trådløse enheder | ikke tilgængeligt | antal, lavt batteri, ikke hørt, signalstyrke |
| Controllerens ur | ikke tilgængeligt | afvigelse fra Home Assistant, og tidsserveren |
| Controllerens adresse | ikke tilgængeligt | IP, gateway og navneservere |
| Projektrevision | ikke tilgængeligt | vises, så et nyt projekt kan ses |
| Download af diagnostik | nej | ja |
| Vedligeholder | ingen | ja |

### Integrationssiden

Sat op fra brugerfladen, med version og antal enheder. Den indbyggede har slet ikke sin egen side.

![Integrationssiden](docs/img/screenshots/integration.png)

### Én enhed pr. produkt

Hvert produkt i IHC-projektet bliver en enhed, navngivet og placeret som projektet har det. Den
indbyggede integration opretter ingen, så alt lander i én flad liste af entiteter uden hardware bag.

![Enhedslisten](docs/img/screenshots/devices.png)

### Vægkontakterne

Hver tast på hver kontakt er en `event`-entitet. De er den mest brugbare trigger, et IHC-hus har, og
den indbyggede integration eksponerer dem slet ikke — kontakterne er usynlige for Home Assistant,
selvom folk trykker på dem hele dagen.

![En vægkontakt som enhed](docs/img/screenshots/wall-switch.png)

### Hvad der styrer en udgang

Projektfilen rummer controllerens egen logik — en vægkontakt, der kipper et relæ, en PIR, der tænder
en lampe — og de links, der forbinder den til produkterne. De links følges ved opsætningen, så et
relæ, der skifter uden at Home Assistant har bedt om det, kan fortælle, hvad der flyttede det:

```yaml
ihc_controlled_by: ["Tryk 2 tast (v. db. dør til terasse)"]
ihc_function_block: ["Kip blok med tænd, sluk og timer funktion"]
```

![Et relæ som enhed](docs/img/screenshots/relay-device.png)

### Controlleren selv

Det, vi ikke styrer, kan vi stadig læse. Elleve diagnostiksensorer på controller-enheden: de trådløse
enheder, den hører, og hvordan de har det; dens ur målt mod Home Assistants; dens adresse; og
projektrevisionen. Alt sammen skrivebeskyttet — at ændre noget af det hører hjemme i IHC Administrator.

Uret er det, der er værd at holde øje med. En controller kører sin egen tidsstyrede logik, så et ur,
der stille er drevet, flytter på, hvornår huset gør ting. Det herunder er 3.375 sekunder bagud — med
NTP slået til og tydeligvis ikke virkende.

![Controllerens diagnostik](docs/img/screenshots/controller-diagnostics.png)

### Alle entiteter

![Entitetslisten](docs/img/screenshots/entities.png)

## Ikke at ødelægge noget

Det her taler med det system, der styrer lyset i et rigtigt hus, så:

- **Skrivebeskyttet som standard.** En ny controller sættes op skrivebeskyttet. Alt vises, og et
  forsøg på at tænde eller slukke noget fortæller, hvorfor det ikke skete. Slå det fra i
  indstillingerne, når du er klar.
- **Intet skrives ved opstart.** Opsætningen læser projektet og abonnerer på værdier. En kommando
  sendes kun, fordi nogen eller en automatisering har bedt om den.
- **Kommandoer er afgrænsede.** En kommando går kun til en ressource, der kommer fra controllerens
  eget projekt, og hver forespørgsel til controlleren har en HTTP-timeout, som sdk'et ikke selv
  sætter. En controller, der holder op med at svare midt i en forespørgsel, kan ikke holde en
  Home Assistant-arbejdstråd fanget for evigt.
- **Taster læses, aldrig styres.** Tasterne på vægkontakterne er indgange. Integrationen abonnerer på
  dem og skriver aldrig til dem, så anlæggets egen kobling rører den ikke.
- **Den kører ved siden af den gamle.** Andet domæne, andre entitets-id'er, sin egen opsætning. Kan
  du ikke lide den, sletter du opsætningen, og intet andet ændrer sig.

## Installation

### HACS

1. HACS > menuen med tre prikker > **Brugerdefinerede repositories**.
2. Tilføj `https://github.com/FrederikLeed/ha-lk-ihc` med kategorien **Integration**.
3. Installér **LK IHC** og genstart Home Assistant.

### Manuelt

Kopiér `custom_components/lk_ihc/` til `config/custom_components/` og genstart.

Kræver Home Assistant 2026.3 eller nyere.

## Opsætning

**Indstillinger** > **Enheder og tjenester** > **Tilføj integration** > **LK IHC**, og udfyld:

| Felt | Værdi |
|---|---|
| Adresse | `http://192.168.1.3`, controllerens adresse på dit netværk. `https://` virker, hvis controlleren er sat op til det. |
| Brugernavn | En IHC-bruger. Læseadgang er nok til at starte; styring kræver en bruger, der må betjene anlægget. |
| Adgangskode | Brugerens adgangskode. |

Integrationen logger på, læser projektet og opretter enheder og entiteter. Opsætningen er
skrivebeskyttet, indtil du siger andet: **Konfigurer** på opsætningen, og slå **Skrivebeskyttet** fra.

## Det du får

| Platform | Fra | Bemærkninger |
|---|---|---|
| Lys | Lampeudtag og dæmpere | En dæmper får lysstyrke, et udtag er tændt eller slukket. |
| Kontakt | Relæer og stikudtag | |
| Binær sensor | PIR, magnetkontakter, røg, vand, skumring | Med den rigtige enhedsklasse, så Home Assistant viser dem korrekt. |
| Sensor | Temperatur og andre målte værdier | |
| Hændelse | Hver tast på hver vægkontakt | Tryk, enkelt- og dobbelttryk, langt tryk og slip — se nedenfor. Det er den del, den indbyggede integration ikke har. |

Produkter, kataloget ikke kender, vises stadig: deres udgange bliver kontakter, og deres indgange
bliver binære sensorer, der oprettes deaktiverede — så intet er skjult, og intet er i vejen.

### En tast på en vægkontakt i en automatisering

```yaml
automation:
  - alias: "Dobbelttryk ved terrassedøren slukker alt udenfor"
    triggers:
      - trigger: state
        entity_id: event.stue_alrum_tryk_2_tast_v_db_dor_til_terasse_tast_venstre
    conditions:
      - condition: template
        value_template: "{{ trigger.to_state.attributes.event_type == 'press' }}"
    actions:
      - action: light.turn_off
        target:
          area_id: udendors
```

En hændelses-entitets tilstand er tidspunktet for det seneste tryk, så et nyt tryk er en ny tilstand,
og triggeren udløses hver gang. Tasten bliver ved med at styre det, IHC har koblet den til.

Controlleren melder kun, at en tast går ned og kommer op. Resten regner integrationen ud af tiden
imellem, så en automatisering kan vælge den bevægelse, den vil have, fra listen i brugerfladen:

| Hændelse | Hvornår |
|---|---|
| `press` | Hver gang tasten går ned, med det samme. |
| `single_press` | Et kort tryk, der ikke blev fulgt af et nyt. Kommer 0,3 sekunder efter slip, for først da vides det, at det ikke var starten på et dobbelttryk. |
| `double_press` | Tasten går ned igen inden for 0,3 sekunder efter et kort tryk. |
| `long_press` | Tasten har været holdt nede i 0,8 sekunder — mens den stadig holdes. |
| `short_release` | Tasten slippes, før den blev til et langt tryk. |
| `long_release` | Tasten slippes efter et langt tryk. |

`press` kommer stadig ved hvert tryk, så en automatisering, der kun vil vide, at der blev trykket,
venter aldrig. Skal enkelt- og dobbelttryk gøre hver sin ting, så brug `single_press` og
`double_press` i stedet.

## Indstillinger

| Indstilling | Hvad den gør |
|---|---|
| Skrivebeskyttet | Så længe den er slået til, sendes der aldrig en kommando til anlægget. |
| Tryk på vægkontakter som hændelser | Opretter hændelses-entiteterne. Slå den fra for en kortere entitetsliste. |

Ændrer du en indstilling, genindlæses opsætningen. Det tager et sekund eller to og kræver ingen
genstart.

## Handlinger: sæt en ressource på dens nummer

Entiteterne dækker det, der er værd at have en entitet: lamper, relæer, sensorer, taster. Men et
anlæg har ressourcer, ingen entitet repræsenterer — en funktionsbloks timer, et flag dens logik
tester, en indgang der kun findes for at blive pulset — og en automatisering skal af og til ramme
præcis sådan én. Det gør du med handlingerne, der adresserer en ressource på dens `ihc_id`:

| Handling | Felter |
|---|---|
| `lk_ihc.set_runtime_value_bool` | `ihc_id`, `value` (true/false) |
| `lk_ihc.set_runtime_value_int` | `ihc_id`, `value` |
| `lk_ihc.set_runtime_value_float` | `ihc_id`, `value` |
| `lk_ihc.set_runtime_value_timer` | `ihc_id`, `value` (millisekunder) |
| `lk_ihc.set_runtime_value_time` | `ihc_id`, `value_hour`, `value_minute`, `value_second` |
| `lk_ihc.pulse` | `ihc_id` — kort tænd-og-sluk, som et tastetryk |

Navnene og felterne er de samme som den indbyggede `ihc`-integrations services, så en
automatisering skrevet til `ihc.set_runtime_value_bool` virker her ved at skifte domænet. Med flere
controllere sat op vælger feltet `controller` én på serienummer; med én kan det udelades.

```yaml
# Sæt PIR-blokkens timer til 10 minutter
action: lk_ihc.set_runtime_value_timer
data:
  ihc_id: 133392
  value: 600000
```

To ting ændrer sig ikke, fordi en ressource rammes på nummer i stedet for via en entitet:
**skrivebeskyttelsen gælder stadig**, og **projektet afgrænser stadig, hvad der kan skrives til.** En
handling går kun til et id, der findes i controllerens eget projekt — det sæt er bredere end
entiteterne (timere og flag er med), men et nummer, der ikke findes i anlægget, afvises. En tastefejl
kan ikke skrive blindt ind i huset.

## At skifte fra den indbyggede `ihc`-integration

Du kan køre begge samtidig — det er hele pointen med det separate domæne. Sådan skifter du:

1. Installér denne, sæt den op, og lad YAML-integrationen være.
2. Sammenlign: lys og relæer bør vises i begge, med de samme tilstande.
3. Slå skrivebeskyttelsen fra her, og test ét lys.
4. Peg dine automatiseringer, scripts og dashboards på de nye entitets-id'er. De er anderledes,
   fordi de gamle er bygget af IHC-ressourcenummeret (`light.stue_alrum_303966`) og de nye af
   produktet og dets placering (`light.stue_alrum_lampeudtag_i_loft`).
5. Fjern `ihc:`-blokken fra `configuration.yaml`, og genstart.

Intet tvinger dig til trin 5. To integrationer må gerne tale med én controller; de har hver sin
session.

## Sådan læses enhederne

Hver enhed navngives og beskrives ud fra projektet, så enhedslisten siger, hvad tingen er, i stedet
for hvilket nummer den har:

| | |
|---|---|
| Navn | Produktet og hvor det sidder: `Universal relæ (på loft over gang)` |
| Model | Produktet i ord: `Dataline wall switch, 2 keys` |
| Model-id | Identifikatoren, projektfilen bruger: `0x2101` |
| Producent | LK |
| Område | Den IHC-gruppe, produktet ligger i — eller det område, du allerede har til den: samme navn, gruppens navn som alias, eller samme id |
| Forbundet via | Controlleren, så hele anlægget hænger på én enhed |

Entiteterne får ikon efter, hvad de er: en tast er `mdi:gesture-tap-button`, et relæ er
`mdi:electric-switch`, et stikudtag er `mdi:power-socket`. Lys, binære sensorer og temperatursensorer
røres med vilje ikke, fordi Home Assistant selv vælger ikon ud fra enhedsklassen og skifter det med
tilstanden.

## Diagnostik

**Download diagnostik** på opsætningen giver controllerens firmware, hvor mange produkter og
ressourcer der blev fundet, og hvilke produkt-identifikatorer anlægget indeholder — plus hvor mange
af dem kataloget ikke genkender. Den rapporterer identifikatorer frem for modelnavne, fordi et
produkt, kataloget ikke kender, får sit navn fra projektfilen, som er tekst ejeren selv har skrevet
om sit hus. Der er hverken adresse, login, rumnavne, produktplaceringer eller entitets-id'er i den,
så den kan vedhæftes en fejlrapport, som den er.

## Begrænsninger

- Testet mod en LK IHC-controller med firmware 2.7.220 og et projekt på 38 produkter, og af en
  bidragyder mod firmware 3.3.44 og 67 produkter (RS485 LED-dæmpere, 80 taster). Anden
  firmware bør virke, fordi grænsefladen ikke har ændret sig i årevis, men det er ikke bevist her.
- Langt tryk og dobbelttryk regnes ud fra, hvornår controlleren melder tasten ned og op, med faste
  tider: 0,8 sekunder for et langt tryk og 0,3 sekunder til et dobbelttryk. De kan ikke ændres endnu.
- Funktionsblokkenes udgange — fx om alarmen er tilkoblet — kommer med som binære sensorer på
  controller-enheden, navngivet efter blokken og deaktiverede som flagene. Slå dem til, du har brug
  for. Scener, timere og funktionsblokkenes øvrige ressourcer eksponeres ikke.
- Controlleren har ikke noget begreb om "utilgængelig" for et enkelt produkt, så en entitet beholder
  sin seneste kendte værdi, indtil controlleren melder en ny.
- Projektet læses ved opsætningen. Ændrer du anlægget i IHC-softwaren, skal opsætningen
  genindlæses for at se det.

## Grafikken

Ikonet, ordmærket og diagrammet ovenfor genereres af
[`tools/build_brand.py`](tools/build_brand.py), så en ændring i dem er en diff frem for en binær fil,
nogen skal åbne i et tegneprogram:

```bash
.venv/bin/pip install cairosvg
.venv/bin/python tools/build_brand.py           # skriver brand/ og docs/img/
.venv/bin/python tools/build_brand.py --check   # fejler, når de er forældede
```

Home Assistant serverer `custom_components/lk_ihc/brand/icon.png` og de større størrelser direkte,
så integrationen viser sit eget mærke uden at vente på brands-repositoriet.

## Designhistorie

Hvordan integrationen er nået til sin nuværende form, og de to undersøgelser (en
firmware-nedbrydning og en API-vurdering), der har formet, hvad den gør og ikke gør:
[docs/how-we-got-here.md](docs/how-we-got-here.md).

## Udvikling

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt ruff==0.16.7 ihcsdk==2.8.12 defusedxml==0.7.1
.venv/bin/python -m pytest --cov=custom_components/lk_ihc --cov-report=term-missing
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Testene rører aldrig et netværk: sdk-controlleren er erstattet af en stand-in, og projektet kommer
fra en opdigtet fil i `tests/fixtures/`.

## Tak og licens

Denne integration står på skuldrene af **Jesper Nielsen** ([dingusdk](https://github.com/dingusdk)).
Han har skrevet og vedligeholder [ihcsdk](https://github.com/dingusdk/PythonIhcSdk), som al
kommunikation med controlleren går igennem, og han er ophavsmand til Home Assistants indbyggede
`ihc`-integration, som produkt-identifikatorerne og deres betydning kommer fra. Uden hans mangeårige
arbejde med at åbne IHC — sdk'et, integrationen, ESP8266-klienten, MQTT-gatewayen og
projekt-vieweren — havde denne integration ikke haft noget at bygge på.

Ikke tilknyttet LK, Schneider Electric eller Lauritz Knudsen. MIT-licens.
