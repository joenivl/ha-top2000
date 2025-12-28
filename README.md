# NPO Radio 2 Top 2000 - Home Assistant Integration

Een Home Assistant HACS custom integration voor de NPO Radio 2 Top 2000, met real-time tracking van het huidige nummer, voorspellingen van komende nummers, en position history over de jaren heen.

## Features

- **Current Song Sensor**: Toont het huidige Top 2000 nummer dat op NPO Radio 2 wordt afgespeeld
  - Positie in de lijst
  - Artiest en titel
  - Release jaar
  - Cover art (via MusicBrainz)
  - Position history (posities uit vorige jaren)
  - Position trend (gestegen/gedaald t.o.v. vorig jaar)
  - Fun facts (optioneel)

- **Upcoming Songs Sensor**: Toont de komende 10 of 20 nummers
  - Configureerbaar aantal (10 of 20)
  - Inclusief cover art en position history per nummer
  - Updates alleen wanneer het huidige nummer verandert

- **Automatische Data Import**: Downloadt en importeert automatisch alle 2000 nummers van de Top 2000 2025
  - Importeert position history van meerdere jaren (default: 2023, 2024, 2025)
  - Trend berekening: zie hoe nummers stijgen (↑), dalen (↓) of gelijk blijven (→) t.o.v. vorig jaar

- **Notificaties**: Ontvang notificaties wanneer je favoriete artiest of nummer wordt afgespeeld
  - Configureerbaar via UI (Settings → Configure)
  - Artist-based rules (bijv. "Queen")
  - Title-based rules (bijv. "Bohemian Rhapsody")
  - **Notificeer voor huidige of komende nummers**: Kies of je notificaties wilt voor het nummer dat NU speelt, of voor nummers die BINNENKORT komen
  - **Multiple notification targets**: Stuur notificaties naar meerdere devices (mobile app, persistent notification, etc.)
  - Cover art in notificaties (bij mobile apps)

## Installatie

### Via HACS (aanbevolen)

1. Open HACS in Home Assistant
2. Ga naar "Integrations"
3. Klik op de 3 stipjes rechtsboven → "Custom repositories"
4. Voeg toe:
   - Repository: `https://github.com/joeni/ha-top2000`
   - Category: `Integration`
5. Klik op "NPO Radio 2 Top 2000" in de lijst
6. Klik op "Download"
7. Herstart Home Assistant

### Handmatig

1. Kopieer de `custom_components/npo_top2000` folder naar je `<config>/custom_components/` directory
2. Herstart Home Assistant

## Configuratie

### Initiële Setup

1. Ga naar **Settings** → **Devices & Services**
2. Klik op **+ Add Integration**
3. Zoek naar "NPO Radio 2 Top 2000"
4. Configureer:
   - **Aantal komende nummers**: 10 of 20
   - **Update interval**: 15-120 seconden (default: 30)
   - **Notificaties inschakelen**: Aan/uit

### Notificatie Instellingen Configureren

1. Ga naar **Settings** → **Devices & Services**
2. Zoek "NPO Radio 2 Top 2000" en klik op **Configure**
3. Kies **Notification settings**
4. Configureer:
   - **Notification targets**: Voeg je notify services toe (bijv. `notify.mobile_app_iphone,persistent_notification`)
   - **Notify for current song**: Aan = notificatie wanneer nummer NU speelt
   - **Notify for upcoming songs**: Aan = notificatie wanneer nummer BINNENKORT komt
   - **Upcoming positions to check**: Bijv. `1,2,3` = controleer de komende 3 nummers
5. Klik op **Submit**

### Notificatie Regels Toevoegen

1. Ga naar **Settings** → **Devices & Services** → **Configure**
2. Kies **Add notification rule**
3. Selecteer:
   - **Type regel**: Artist of Title
   - **Zoekpatroon**: Bijv. "Queen" of "Bohemian Rhapsody"
4. Klik op **Submit**

De notificatie verschijnt automatisch wanneer een matchend nummer wordt afgespeeld!

**Voorbeeld scenario:**
- Regel: Artist = "Queen"
- Notificatie voor huidige nummer: AAN
- Notificatie voor komende nummers: AAN, posities 1,2,3
- Targets: `notify.mobile_app_iphone,persistent_notification`

**Resultaat:**
- Als Queen - Bohemian Rhapsody NU speelt → notificatie op beide devices
- Als Queen - Don't Stop Me Now op positie #347 staat en #346 net is afgelopen → notificatie "Binnenkort op Radio 2"

## Sensor Attributes

### Current Song Sensor (`sensor.npo_top2000_current_song`)

**State**: `#1: Queen - Bohemian Rhapsody`

**Attributes**:
```yaml
position: 1
artist: "Queen"
title: "Bohemian Rhapsody"
year: 1975
cover_art_url: "http://coverartarchive.org/release/..."
detected_at: "2025-12-25T15:30:00"
position_history:
  - year: 2024
    position: 1
  - year: 2023
    position: 1
  - year: 2022
    position: 2
position_trend: "↑ 1"
position_trend_direction: "up"
fun_fact_1: "Dit nummer werd opgenomen in 3 weken..."
fun_fact_2: "Freddie Mercury schreef dit nummer..."
fun_fact_3: "Het nummer bestaat uit 6 verschillende delen"
```

### Upcoming Songs Sensor (`sensor.npo_top2000_upcoming_songs`)

**State**: `10` (aantal songs)

**Attributes**:
```yaml
count: 10
current_position: 1
songs:
  - position: 2
    artist: "Eagles"
    title: "Hotel California"
    year: 1977
    cover_art_url: "..."
    position_history:
      - year: 2024
        position: 3
    position_trend: "↑ 1"
  - position: 3
    ...
```

## Notificatie Voorbeelden

### Automatische Notificaties via UI

De makkelijkste manier is via de UI (zie configuratie hierboven). De integratie stuurt automatisch notificaties wanneer een regel matcht.

**Voorbeeld notificatie (huidig nummer):**
```
NPO Radio 2 Top 2000

Nu op Radio 2:
#1: Queen - Bohemian Rhapsody (1975)

💡 Dit nummer werd opgenomen in slechts 3 weken tijd...
```

**Voorbeeld notificatie (komend nummer):**
```
NPO Radio 2 Top 2000

Binnenkort op Radio 2:
#347: Queen - Don't Stop Me Now (1979)

💡 Dit nummer werd geschreven door Freddie Mercury...
```

### Hoe vind ik mijn notify service naam?

Je notify services vind je in Home Assistant via:
1. **Developer Tools** → **Services**
2. Zoek naar `notify.` in de lijst
3. Veelgebruikte namen:
   - `notify.mobile_app_iphone` (Home Assistant Companion app op iPhone)
   - `notify.mobile_app_android` (Home Assistant Companion app op Android)
   - `notify.persistent_notification` (In-app notificaties in Home Assistant)
   - `notify.telegram` (Telegram bot)

Gebruik de naam ZONDER `notify.` prefix in de configuratie, of met de volledige naam (beide werken):
- ✅ `mobile_app_iphone` OF `notify.mobile_app_iphone`

### Handmatige Automation (voor advanced use cases)

```yaml
automation:
  - alias: "Top 2000 - Stuur naar mobile app"
    trigger:
      - platform: state
        entity_id: sensor.npo_top2000_current_song
    condition:
      - condition: template
        value_template: "{{ 'Queen' in state_attr('sensor.npo_top2000_current_song', 'artist') }}"
    action:
      - service: notify.mobile_app_iphone
        data:
          title: "Top 2000"
          message: >
            Nu op Radio 2: #{{ state_attr('sensor.npo_top2000_current_song', 'position') }}
            {{ state_attr('sensor.npo_top2000_current_song', 'artist') }} -
            {{ state_attr('sensor.npo_top2000_current_song', 'title') }}
          data:
            image: "{{ state_attr('sensor.npo_top2000_current_song', 'cover_art_url') }}"
```

## Lovelace Card Voorbeeld

```yaml
type: entities
title: NPO Top 2000
entities:
  - entity: sensor.npo_top2000_current_song
    name: Nu op Radio 2
    secondary_info: last-updated
  - type: attribute
    entity: sensor.npo_top2000_current_song
    attribute: position_trend
    name: Trend t.o.v. vorig jaar
  - entity: sensor.npo_top2000_upcoming_songs
    name: Komende nummers
```

## Technische Details

### Data Bronnen

- **Top 2000 Data**: [Top2000app/data GitHub](https://github.com/Top2000app/data)
- **NPO Metadata**: NPO Radio 2 website scraping (3-tier fallback strategie)
- **Cover Art**: MusicBrainz Cover Art Archive API (gratis, geen API key vereist)

### Architectuur

- **Database**: SQLite embedded database met 2000 nummers
- **Update Coordinator**: Elke 30 seconden NPO metadata ophalen
- **Fuzzy Matching**: Automatische matching tussen NPO metadata en Top 2000 database
- **Caching**: Cover art 24h cached, NPO metadata 30s cached

### Componenten

- **Database**: 2000+ nummers met position history, fun facts, en cover art
- **NPO Scraper**: 3-tier fallback strategie voor real-time metadata
- **Fuzzy Matching**: Automatische koppeling NPO metadata ↔ Top 2000 database
- **Cover Art**: MusicBrainz API + NPO CDN
- **Notificaties**: Configureerbaar via UI met artist/title regels

## FAQ

**Q: Waarom zie ik geen data?**
A: De integratie werkt alleen tijdens de Top 2000 uitzending (25-31 december). Buiten deze periode wordt er geen data van NPO Radio 2 opgehaald.

**Q: Kan ik position history van meerdere jaren zien?**
A: Ja! De integratie importeert automatisch position history van 2023, 2024 en 2025. De sensor attributes tonen de posities uit vorige jaren en trends (↑/↓/→).

**Q: Kan ik meer jaren importeren?**
A: Ja, de database ondersteunt position history van meerdere jaren (2018-2025). Nieuwe jaren worden automatisch toegevoegd wanneer beschikbaar.

**Q: Werkt dit ook met andere radio stations?**
A: Nee, deze integratie is specifiek voor NPO Radio 2 en de Top 2000.

## Roadmap

- [x] Notification platform met UI voor regels ✅
- [x] Position history tracking (meerdere jaren) ✅
- [x] Cover art via MusicBrainz ✅
- [x] Fun facts generation met OpenAI (GPT-4o-mini) ✅
- [x] Multiple notification targets (mobile, persistent, etc.) ✅
- [x] Upcoming song notifications ✅
- [ ] Custom Lovelace card
- [ ] Service calls voor handmatige refresh
- [ ] Statistics & history tracking
- [ ] Voice announcements via TTS

## Credits

- Data: [Top2000app](https://github.com/Top2000app)
- Cover Art: [MusicBrainz Cover Art Archive](https://musicbrainz.org/doc/Cover_Art_Archive)
- NPO Radio 2: [NPO](https://www.nporadio2.nl)

## License

MIT License
