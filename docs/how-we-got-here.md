# How this integration got to where it is

A design history of `lk_ihc`: what was built, in what order, and why each step was worth taking.
It doubles as the record of two investigations — a firmware teardown and an API evaluation — whose
main value was telling us what *not* to change.

## The starting point

Home Assistant already ships an `ihc` integration, maintained by the author of the IHC SDK. It
works and it is widely used, but it is YAML-only, creates no devices, and maps only outputs and
sensors. In a typical IHC house that means the lamp outlets and relays appear as bare entities, and
the wall switches people actually press — the most useful trigger an IHC house has — are invisible.

`lk_ihc` was built to fix that, as a separate domain running beside the built-in one, so a live
house keeps working while the new integration is compared against it. It reuses `ihcsdk` for the
SOAP transport and adds a model on top.

## The build, version by version

- **v0.1.0** — the foundation: a config flow instead of YAML, one device per product, and an
  `event` entity for every key on every wall switch. Read-only by default, so a whole installation
  can be looked at before Home Assistant is allowed to switch anything.
- **v0.1.1** — a refused command (read-only mode, or a resource not in the project) raises a
  translated validation error rather than a server traceback.
- **v0.1.2** — its own brand icon and a README diagram.
- **v0.2.0** — devices read as products, not part numbers: `model` is the catalogue name
  ("Dataline wall switch, 2 keys"), `model_id` the IHC identifier.
- **v0.2.1** — continuous integration (HACS Action + hassfest), the price of being submittable to
  the HACS default list. `requirements_test.txt` was also made self-contained; it had been missing
  the integration's own runtime dependencies, so a fresh clone could not collect the tests.
- **v0.3.0** — the installation's own logic, read from the project: function blocks and the links
  that wire a wall switch through a block to a relay. Entities gained `ihc_controlled_by` and
  `ihc_function_block`, so a relay that changes without Home Assistant asking can say what moved it.
- **v0.4.0** — reading what we do not control. A read-only client for the SOAP services `ihcsdk`
  does not wrap (AirlinkManagementService, TimeManagerService, the configuration reads), surfaced in
  diagnostics: wireless devices, the controller clock, its network settings.
- **v0.5.0** — the same state made visible as entities rather than buried in a diagnostics file:
  eleven diagnostic sensors on the controller device (wireless counts and signal, clock offset,
  time server, project revision, address, gateway, DNS).
- **v0.6.0** — the controller's logic resources: flags and enums that live only inside its logic,
  as read-only diagnostic entities (enums as sensors, flags as disabled-by-default binary sensors).

## Investigation 1 — the firmware teardown

The question was whether the firmware hid a cleaner way to talk to the controller. Getting into it
took four steps:

1. **The `.fwf` file is fully encrypted.** Measured, not guessed: entropy 8.0000 across the whole
   file, no header, no magic, a 15-character longest string in 12.7 MB, and zero repeated blocks in
   1.6 million — which ruled out ECB and pointed at a stream cipher.
2. **The key was in LK's Windows software, not the controller.** `FirmwareLoader.exe` is a JSmooth
   wrapper around a GCJ-built Java app; the real JAR sits in its `.rsrc` section. Decompiled, the
   firmware path reads `EncryptedInputStream(Rc4Cipher(k.a())) -> ZipInputStream`, and `k.a()`
   returns a hardcoded 8-byte RC4 key (`91 15 FE A8 0D 3B 7F 62`), the same for every controller.
3. **RC4 with that key turns the file into a ZIP.** Inside: a manifest, install scripts, a rootfs
   overlay and the controller binary.
4. **What the controller is:** a PowerPC 32-bit big-endian embedded Linux box running a Java
   application AOT-compiled with GCJ 3.4.3. The wired bus (dataline) is driven over i²c by a
   separate microcontroller; the wireless units are PIC18F chips flashed by an install script. The
   full API is **twelve SOAP services, 216 operations** — `ihcsdk` uses four, IHC Captain seven.

The teardown is written up in full in `/workspace/ihc-firmware/FIRMWARE.md` and `FINDINGS.md`
(outside this repo, as it concerns the device, not the integration).

## Investigation 2 — is there a cleaner API?

The firmware revealed an `openapi` service (42 operations) that LK built for third parties, plus
services `ihcsdk` never touched. It looked like a cleaner foundation, so it was tested against the
live controller: `authenticate`, `getValues` (batch read), `enableSubscription` + `waitForEvents`,
`setValues` — all worked.

Then every openapi operation was mapped against `ihcsdk`, and the honest result was: **openapi
offers nothing `ihcsdk` lacks.** Even batch reads already exist (`get_runtime_values`). openapi is a
thinner *transport*, not a richer one, and it has no project model — the names, areas, products,
wiring and diagnostics that make this integration worth having all come from parsing the project,
which openapi does not help with.

An earlier note in this project called `ihcsdk` "unmaintained" and used that to argue for replacing
it. That was wrong: `ihcsdk` had a release in March 2026, is actively maintained by the same author
as the built-in integration, and is proven in thousands of houses. Swapping a healthy, well-tested
library for our own code, on the thing that runs the lights, in exchange for nothing — that is a bad
trade. **The transport stays on `ihcsdk`.**

The rule that settled it, from the project owner: *use the new thing only if it gives us something
we do not already have.* openapi did not. What the firmware *did* give was confirmation that flags
and enums are addressable resources — and that became v0.6.0.

## Where it stands against the alternatives

| | built-in `ihc` | `haihc-betatest` (author's beta) | `lk_ihc` |
|---|---|---|---|
| UI config flow | no | yes | yes |
| Devices per product | no | no | yes |
| Wall-switch keys as events | no | no | yes |
| Function-block wiring | no | no | yes |
| Wireless / clock / network diagnostics | no | no | yes |
| Flags and enums | no | no | yes |
| Transport | ihcsdk | ihcsdk | ihcsdk |

The author's own beta uses the same parsing approach, which is good confirmation the foundation is
right; `lk_ihc` simply goes further with the project model.

## Deliberately not done

- **Replacing the transport.** ihcsdk is healthy and proven; openapi adds nothing (above).
- **Writing flags or enums.** They are inputs to logic the controller runs; ihcsdk has no enum
  setter, and writing one would reach into that logic blind. Exposed read-only.
- **Timers and scenes as entities.** A timer reads as a near-always-zero countdown; a scene has no
  readable value. Neither is worth an entity.
- **Uploading a project (`storeIHCProject`).** The API supports it, but changing the installation's
  logic from Home Assistant is out of scope and high-risk.

## The house this was built against

A live 38-product installation on controller serial 1062 (a 2006 unit, firmware 2.7.220 from 2015):
17 function blocks, 22 products with traced wiring, 27 wireless devices, 2 enums, 15 flags. One
finding fed back to the owner: the controller's clock runs ~56 minutes behind with NTP enabled and
not working — visible now as the `clock_offset` sensor.
