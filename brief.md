---
project: ha-lk-ihc
repo: https://github.com/FrederikLeed/ha-lk-ihc
updated: 2026-09-23
status: active
---

# LK IHC til Home Assistant

Custom integration (domæne `lk_ihc`) til LK IHC-controllere: config flow i stedet for YAML, én enhed
pr. produkt og en hændelses-entitet for hver tast på hver vægkontakt. Bygget fordi Home Assistants
indbyggede `ihc`-integration er på legacy-kvalitetsniveau, ingen vedligeholder har, ingen enheder
opretter og kun mapper udgange og sensorer — så vægkontakterne, der er den mest brugbare trigger i et
IHC-hus, er usynlige.

Bygget oven på Jesper Nielsens ([dingusdk](https://github.com/dingusdk)) arbejde: `ihcsdk` er hans,
og det samme er den indbyggede `ihc`-integration, som kataloget over produkt-identifikatorer stammer
fra. Han krediteres i README og skal blive ved med at være det.

Dokumentationen (README, denne brief og designhistorien i `docs/`) er på dansk med vilje: LK IHC er
et dansk produkt, og brugerne er det stort set alle. Kode, docstrings og commit-beskeder er engelsk.

## Nuværende tilstand

- v0.6.0: controllerens egne logik-ressourcer er synlige. Ud over et produkts fysiske ind- og udgange
  rummer projektet ressourcer, der kun lever inde i controllerens logik: flag, den sætter og tester,
  og enums, der vælger mellem navngivne tilstande. De var usynlige — et flags tilstand kunne kun
  udledes af, hvad lyset gjorde. Enums er nu diagnostiksensorer på controller-enheden
  (device_class enum, valgmuligheder læst fra den fælles `enum_definition`, ressourcen peger på via
  `typedef`); flag er binære diagnostiksensorer, deaktiverede som standard, fordi et anlæg har mange,
  og de fleste er intern rørføring. Skrivebeskyttet med vilje: et flag eller en enum er input til
  logik, controlleren kører, ihcsdk har ingen enum-sætter, og at skrive én ville række blindt ind i
  den logik. Timere og scener er udeladt — en timer læses som en nedtælling, der næsten altid er nul,
  og en scene har ingen læsbar værdi. Tjekket mod firmwaren: openapi/setValues tilbyder intet, ihcsdk
  mangler, så transporten bliver på ihcsdk (se firmware-noterne). Verificeret live: 2 enums, 15 flag.
- v0.5.0: controllerens egen tilstand er synlig, ikke bare downloadbar. v0.4.0 lagde den i
  diagnostikken, som er en fil, man henter og læser som JSON — ubrugeligt til faktisk at holde øje
  med et anlæg. Nu er det elleve diagnostiksensorer på controller-enheden: antal trådløse enheder,
  hvor mange der har lavt batteri eller ikke er hørt, svageste og stærkeste signal, urafvigelsen,
  tidsserveren, projektrevisionen samt adresse, gateway og navneservere. En sensor, hvis værdi
  controlleren ikke kan levere, oprettes slet ikke, så en ældre controller får færre entiteter frem
  for en række "ukendt". De trådløse tællinger giver ingenting frem for 0, når controlleren ingen
  trådløs tjeneste har, fordi 0 læses som "den hørte ingen", når sandheden er, at den aldrig kunne
  spørge. `clock_offset` fjerner controllerens egen GMT-forskydning og sommertid, før der
  sammenlignes, så den måler øjeblikket og ikke, hvordan controlleren skriver det ned — på den
  levende controller viser den -3369 s, et ur næsten en time bagud med NTP slået til og ikke virkende.
- v0.4.0: det, vi ikke styrer, kan vi stadig læse. `services.py` pakker de SOAP-tjenester ind, som
  ihcsdk lader ligge — AirlinkManagementService, TimeManagerService og konfigurationslæsningerne — og
  diagnostikken rummer nu de trådløse enheder (antal, lavt batteri, ikke hørt, signalstyrker),
  projektrevisionen, controllerens ur og hvordan det holdes, dens porte og om mail er sat op. Alt
  sammen skrivebeskyttet med vilje: det er controllerens egne indstillinger, og at ændre dem hører
  hjemme i IHC Administrator. Intet her er fatalt — en ældre controller svarer kun på nogle af dem, og
  et manglende svar efterlader et felt som None frem for at fejle opsætningen. Verificeret mod den
  levende controller: 27 trådløse enheder, ingen lave, ingen uhørte. `getBatteryLevel` og
  SD-kort-kaldene returnerer intet på hw 6.1; batteriflaget kommer fra enhedslisten i stedet.
- v0.3.0: anlæggets egen logik læses, så en entitet kan sige, hvad der ellers flytter den.
  Projektfilen rummer funktionsblokke (en vægkontakt, der kipper et relæ, en PIR, der tænder en
  lampe) og de links, der kobler dem til produkter; linkene følges én gang ved opsætningen, og hvert
  produkt får at vide, hvilke produkter der når det, og gennem hvilken blok. Entiteterne fik
  `ihc_controlled_by` og `ihc_function_block`, diagnostikken fik `function_blocks` og
  `products_with_wiring`. Et link er to halvdele, der navngiver hinanden, og begge sidder inde i det
  produkt eller den blok, de hører til, så koblingen læses ved at spørge, hvem der ejer hver halvdel —
  at matche på `link1`-attributten finder intet, hvilket var det, der først fik logikken til at se
  ukoblet ud. Verificeret mod det levende anlæg på 38 produkter: 17 blokke, 22 produkter med sporet
  kobling.
- v0.2.1: continuous integration, så repositoriet kan indsendes til HACS' standardliste.
  `.github/workflows/` kører HACS Action og hassfest ved push, ved pull requests og ugentligt, hvilket
  HACS kræver, før den accepterer et repository som standard. `requirements_test.txt` fik
  integrationens egne manifest-krav (`ihcsdk`, `defusedxml`): Home Assistant installerer dem ved
  kørsel, men pytest importerer pakken direkte, så et frisk klon slet ikke kunne indsamle testene.
  Intet i integrationens adfærd ændrede sig; versionen flyttede kun, fordi HACS vil have en udgivelse
  oprettet, efter at actions er grønne, og dette repository har én kendt installation.
- v0.2.0: enheder, der læses som produkter og ikke varenumre. `model` er katalognavnet
  ("Dataline wall switch, 2 keys"), `model_id` er IHC-identifikatoren, og entiteterne bærer et ikon,
  hvor Home Assistant ingen god standard har (taster, relæer, stikudtag). Diagnostikken rapporterer
  identifikatorer frem for modelnavne, fordi et ukendt produkt får sit navn fra ejerens egen
  projektfil.
- v0.1.2. Mærke-grafik og README-diagrammet genereres af `tools/build_brand.py` (én tegning, SVG plus
  de PNG-størrelser, Home Assistant serverer fra `brand/`, lyst og mørkt diagram, `--check`-tilstand).
  v0.1.1 gjorde afviste kommandoer til ServiceValidationError med oversatte beskeder.
- v0.1.0, første virkende version. 46 tests, 97 % dækning, ruff og hassfest rene lokalt.
- Platforme: lys (tænd/sluk og dæmpbar), kontakt, binær sensor (PIR, magnet, røg, vand, skumring),
  sensor (temperatur), hændelse (taster på vægkontakter, udløser `press`).
- Tørkørsel mod et rigtigt anlæg på 38 produkter: 38 enheder, 63 entiteter (38 taster, 10 lys,
  12 kontakter, 3 binære sensorer), alle produkter genkendt, 11 områder foreslået ud fra
  IHC-grupperne.

## Centrale beslutninger

- **Separat domæne, ikke en erstatning.** `lk_ihc` kører ved siden af den indbyggede
  `ihc`-integration, så et hus i drift bliver ved med at virke, mens den nye sammenlignes med den. En
  custom component med domænet `ihc` ville have skygget for den indbyggede uden varsel — det modsatte
  af sikkert.
- **Skrivebeskyttet som standard.** En ny opsætning sender aldrig en kommando, før indstillingen slås
  fra. Skrivning afvises også for enhver ressource, der ikke findes i controllerens eget projekt.
- **HTTP-timeouts sætter vi selv.** ihcsdk poster uden timeout, og et executor-job kan ikke afbrydes,
  når det først kører, så `apply_http_timeout` pakker sdk-sessionens `post` ind. Uden den ville en
  controller, der holder op med at svare midt i en forespørgsel, holde en Home Assistant-arbejdstråd
  fanget.
- **Kataloget er data, ikke kode.** `catalog.py` mapper produkt-identifikator til rolle; ukendte
  produkter får stadig kontakter for udgange og deaktiverede binære sensorer for indgange, så intet
  går tabt i stilhed.
- **Projektfilen kommer aldrig i repoet.** Den er et kort over nogens hus. `.gitignore` blokerer
  `*.xml` uden for `tests/fixtures/`, og testene bruger et opdigtet anlæg.
- **Transporten bliver på ihcsdk.** Firmwaren afslørede en `openapi`-tjeneste, der lignede et renere
  fundament; testet mod den levende controller tilbød den intet, ihcsdk mangler. Et sundt, afprøvet
  bibliotek byttes ikke ud med egen kode for ingenting — slet ikke på det, der styrer lyset. Se
  `docs/how-we-got-here.md`.

## Faldgruber fundet undervejs

- `DeviceInfo(via_device=...)` er udfaset i 2026.9: giv `via_device_id` med controller-enhedens
  registry-id, hvilket betyder, at den enhed skal oprettes, før platformene sættes i gang.
- `device_registry.async_get_device(identifiers=...)` er også udfaset;
  `async_get_device_by_identifier(identifier, config_entry_id)` er erstatningen.
- Entitets-id'er bliver `<område>_<enhed>_<entitet>`, fordi enheden bærer `suggested_area`.
- Den første værdi, et abonnement leverer, er den nuværende, så en hændelses-entitet skal ignorere
  den — ellers ligner en tast, der tilfældigvis holdes nede ved opstart, et tryk.
- HA's history-API sætter `end_time` til start + 1 døgn som standard. En forespørgsel "7 dage tilbage"
  uden `end_time` giver altså kun det ene døgn for 7 dage siden — nemt at fejllæse som "ingen data".
- Et `pkill -f` med et mønster, der matcher ens egen shell-kommando, dræber shellen selv (exit 144).
- Frontendens `hassTokens` skal seedes med `add_init_script`, ikke `localStorage.setItem` efter
  navigation — ellers racer man mod frontendens egen bootstrap og lander på `/auth/authorize`.

## Næste

- Indsend til HACS' standardliste (`hacs/default`, filen `integration`); actions er grønne.
- Langt tryk og dobbelttryk som separate hændelsestyper.
- Overvej at flytte RF-sensorernes rå SOAP (`services.py`) over på ihcsdk-sessionen, hvis ihcsdk får
  AirlinkManagementService — indtil da er den rå klient bevidst.
