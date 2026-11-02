# iZone Plus (Home Assistant)

Companion integration for the built-in `izone` integration. Adds raw access to
the iZone ASH bridge local API (V2 documented + V1 legacy) so undocumented /
unexposed capabilities can be explored and exposed: schedules, favourites,
fault lists, firmware, CTPS tablet temps, damper positions, iLight, iDrate.

## Services (all return responses)

- `izone_plus.v2_request` — `type`, `no`, `no1` → parsed + raw reply from `POST /iZoneRequestV2`
  - Types: 1 system info, 2 zone info (no=zone index), 3 favourites, 4 AC fault list,
    5 Temperzone status, 6 firmware list, 7 system status, 8 CTPS room temp
- `izone_plus.v2_command` — `payload` dict → `POST /iZoneCommandV2`
- `izone_plus.v1_command` — `command`, `data` → `POST /<command>` (legacy)
- `izone_plus.raw_post` / `izone_plus.raw_get` — arbitrary path/body probes (iLight/iDrate discovery)

Safe by default: no entities, no polling. The existing `izone` integration
keeps owning the climate side.
