# iZone Plus (Home Assistant)

Companion to the built-in `izone` integration. Adds Home Assistant access to
the parts of the iZone ASH bridge **local API** that the built-in integration
never exposes, plus raw probe services for further exploration.

Built and verified against bridge `000052973` (ASH, C325 2.4 / C225 3.55 /
CL5B 3.23, Mitsubishi Electric unit, 8 zones).

## What the built-in `izone` integration misses (and this adds)

| Data | Source | Entities |
|---|---|---|
| Filter reminder interval (months: 0/3/6/12) | `SystemV2.FilterWarn` | `select.*_filter_reminder_interval`, `sensor.*_filter_reminder_interval` |
| Filter cleaning required (yes/no) | `SystemV2.Warnings` = `filter` | `sensor.*_filter_cleaning_required` |
| Reset filter warning | `ResetWarning` = `filter` | `button.*_reset_filter_warning` (second press within 30s confirms) |
| Installer flags (economy lock, fan auto, iZone/AC ownership, airflow locks, reverse dampers, scrooge, hide induct, auto off, room-temp display, wired LEDs) | matching `SystemV2` field | `switch.*` config entities. Wired LEDs write `SetWiredLeds`; scrooge writes `ScroogeMode` |
| Economy min/max, auto deadband, damper time (0 = automatic), fan-auto capacity, RF channel | matching `SystemV2` field | `number.*` config entities. RF channel writes `ChangeRfCh` |
| Return-air sensor mode, fan-auto type, control zone | `RAS` / `FanAutoType` / `CtrlZone` | `select.*`. Writes are `RASSet`, `FanAutoType`, `MasterZone` |
| AC fault history with descriptors | V2 Type=4 `AcUnitFaultHistV2` | `sensor.*_latest_ac_fault` (+history attr) |
| Per-board firmware | V2 Type=6 `Fmw` | `sensor.*_firmware` |
| Damper position % | V2 Type=2 `ZonesV2.DmpPos` | `sensor.*_<zone>_damper_position` |
| Zone sensor fault | `ZonesV2.SensorFault` | `binary_sensor.*_<zone>_zone_sensor_fault` |
| Schedules (8 slots) | V2 Type=3 `SchedulesV2` | raw probe (write schema validated) |

Also visible via probes but not writable from this integration: `UnitOpt`
(no command in the spec), `OemMake` (no command), and AC brand. `AcUnitBrand`
and `SetAcUnitBrandSet` use different enums, and this firmware does not return
`AcUnitBrandSet`, so a brand control would retarget the unit to the wrong make.
Do not send `ChangePass`. The local API does not check the config password.

## Raw probe services (all return responses)

- `izone_plus.v2_request` — `type`, `no`, `no1` → `POST /iZoneRequestV2`
  - Types: 1 system, 2 zone (no=index), 3 schedules (no=0-7), 4 AC fault list,
    5 Temperzone diag, 6 firmware, 7/8 unsupported on this firmware
- `izone_plus.v2_command` — `payload` → `POST /iZoneCommandV2` (validated: `SchedName`, ...)
- `izone_plus.v1_command` — `command`, `data` → `POST /<Command>` (legacy)
- `izone_plus.raw_post` / `izone_plus.raw_get` — arbitrary path/body

## Protocol notes (verified)

- V2 reads: `POST /iZoneRequestV2` `{"iZoneV2Request":{"Type":x,"No":y,"No1":z}}`
- V2 writes: `POST /iZoneCommandV2` `{Command: {...}}` → `{OK}` / `{ERROR}`
- V1 reads: `GET /SystemSettings`, `/Zones1_4`, `/Zones5_8`, `/Zones9_12`, `/Zones13_14`
- V1 writes: `POST /<CommandName>` e.g. `/ZoneCommand`, `/AirMaxCommand`
- iPower: `POST /PowerRequest {"PowerRequest":{"Type":n,...}}` (endpoint present, no hardware paired)
- iLight: `POST /iLightRequest` (endpoint present, empty — nothing paired)
- iDrate: no HTTP surface on this bridge despite `iDrate` UDP tag
- Undocumented Type ≥9: `{ERROR}`
- Content-Type polarity: this bridge answers **without** `Content-Type`;
  client auto-negotiates both.
- ⚠️ `iZoneRequestV2` Type=1 returns the bridge admin **`Pass` and `LockCode` in
  plaintext**. This integration redacts them; never expose raw Type=1 output to
  dashboards or logs.

## Schedule writes

`SchedFullSettings` requires `Fan`, `Mode` and `AcSetpoint` in addition to the
fields the read returns — omitting them yields `{ERROR}`. `SchedName` alone
works for renames. Per-field commands available: `SchedEnable`, `SchedName`,
`SchedZones`, `SchedSettings`, `SchedAcMode`, `SchedAcFan`.

Official API header (authoritative command list):
`https://developer.izone.com.au/downloads/iZone_JSON_datastrings.h`

## Requirements

- iZone Wi-Fi/ETH bridge (ASH) on the LAN. Keep the built-in `izone`
  integration installed — it owns climate control; this adds the extras.
- No extra pip dependencies (pure aiohttp).
