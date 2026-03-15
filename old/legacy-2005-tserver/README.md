# Legacy Genesys T-Server Tools (2005)

Auto-dialer and T-Server/PBX verification utilities written in C against the Genesys TLib SDK.

## Files

| File | Description | Date |
|------|-------------|------|
| `dial.c` | Auto-dialer — places outbound calls via T-Server, waits for answer, transfers to agent DN. Supports redial with configurable timeout/attempts. | Aug 2005 |
| `verify.c` | T-Server + PBX connectivity verifier — tests TLib connection and DN registration. | Oct 2005 |

## Dependencies

These files require the Genesys TLib C SDK headers:
- `tlibrary.h`
- `kvlist.h`
- `convert.h`
- `connection.h`

## Author

Ighor Toth — `igtoth@gmail.com` (as referenced in the RCS `$Id$` tags)
