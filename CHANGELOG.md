# Changelog

## 1.3.1

- A map is no longer stopped by one bad entry. Before compiling, KnoxMap checks
  the WorldEd project: anything past the edge of the map or its cell is moved
  where it belongs or left out, and a building file that is missing or broken is
  left out, all written to the log - instead of WorldEd refusing the whole map
  ("Could not open project", "invalid cell coordinates"). Maps made with older
  versions are repaired too, without building again.
- One building that cannot be laid out is left out, with the reason in the
  log, instead of stopping Build for the rest.
- A problem report includes WorldEd's own logs.

## 1.3

- KnoxMap updates itself: a new release downloads in the background, is checked
  against GitHub's fingerprint, and installs on restart, keeping your maps,
  logs, settings, Python and map tools. Setup and the Python packages are
  brought up to date only when a release changes them, and a map compiler
  setup installed is replaced when a release ships a new one. From 1.2.1 or
  earlier, download 1.3 by hand once; after that it is automatic.

## 1.2.1

- Fixed WorldEd refusing a map with "error reading world, invalid cell
  coordinates": a railing on a bridge along the map's bottom or right edge
  stood in a cell past the edge. Nothing in the project can name such a cell
  now. Maps made before this need **Build** again, then **Compile**.

## 1.2

- A proper error log: logs/knoxmap.log with a description of the PC, every step
  and every error in full; an id on each error in the app; WorldEd's output
  from every compile; a setup log; and a report zip to post in #bug-reports.
- The README's screenshot shows the current window.

## 1.1

**Fixes from the Discord**
- Errors come back as a message and a knoxmap_error.log, not "<!doctype is
  not valid JSON"; and the app runs in UTF-8, which fixes generating a map on
  Korean and Japanese Windows.
- Overpasses and flyovers on ramps, with railed decks on posts, and the roads
  underneath left whole; bridges over water laid square with railings.
- Arches, columns, statues and fountains from OpenStreetMap's monuments.
- Sinks, televisions, lamps and pot plants stand on a counter, cabinet or table;
  nothing blocks the two tiles in front of a door or the tile in front of a
  fridge, stove or wardrobe; a bed keeps floor at its foot.
- No window on the inside corner of a stepped diagonal wall, where it took half
  the wall with it.
- Small blocks of flats have bedrooms and bathrooms, not a living room for
  every flat.

## 1.0 (first release)

KnoxMap grows [Knoxify](https://github.com/arytek/knoxify)'s terrain generator
into a full pipeline, from a real place to an installed Project Zomboid Build 42
map.

**Choosing an area**
- Rectangle, polygon, circle and freehand lasso tools, and a search result's
  real boundary (a park, a district, a town). Only the shape is built; main
  roads and rivers run on past it.
- `?q=<place>&outline=1` opens the app straight to a place.

**Terrain**
- Streets at real widths, with pavements, kerbs and centre lines; the map turns
  so the main street grid runs along the tiles.
- Seas from OpenStreetMap coastlines, harbours and lakes from multipolygons,
  rivers with their bridges, canals, piers and railways.
- Parks, schoolyards, industrial yards, cemeteries, orchards, playgrounds,
  pools, fences, walls and hedges; dense city blocks paved.

**Buildings**
- Every building on its real footprint, turned to the grid, with rooms laid out
  for what it is: houses, blocks of flats with corridors and separate flats,
  shops, schools, churches, clinics, offices, factories and sheds.
- Real heights up to 30 storeys, borrowed from tagged neighbours where missing.
- Lifts in buildings of five storeys or more, working with the Elevators mod.
- Windows that suit the building: kind, size and spacing follow what it is
  and how tall (glass towers, shop fronts, tall panes on flats), with
  matching curtains or blinds. Window count is not a setting.
- A light switch in every room, clear staircases, roofs that follow the
  footprint, loot tables that match the room.

**In the game**
- The paper map (M) with real buildings, water, streets, street names and
  landmarks.
- Zombies spawned from an estimate of who lived and worked in each building,
  with a census and a one-second recount.
- Buildings are what they really are: the shops, restaurants, banks, offices,
  hotels and theatres OpenStreetMap maps inside them become the game's own
  rooms - a pizza place is a dining room and a pizza kitchen, a hotel's floors
  are guest rooms, a theatre is a foyer and an auditorium - so the loot fits.
- Shops fitted out like Knox County's: rows of shelving, fridges along the
  walls, a till by the door and a stockroom behind; offices with desks and
  filing cabinets; every flat with its own sofa, beds, wardrobes and kitchen.
- Restaurants, cafés and bars fitted out like the game's own: diner and pizzeria
  booth sets, tables with their chairs (against the wall in a narrow place), a
  counter across the back, and kitchens of steel counters, commercial ovens, a
  griddle and fryers. Narrow shops mix fridges with shelving; theatres have rows
  of seats. Army bases get the game's army storage rooms.
- *Square up buildings* setting: how far off the grid a building may be and
  still stand upright (15 degrees by default, 45 for every building).
- No windows, shop fronts or doors in walls shared with the building next door;
  stairs at the back of a shop, not in the middle of it.
- Uses Erika's Tiles when it is installed: glass shop fronts with glass doors
  and shop signs, drinks machines, posters and bookcases in shops, pictures,
  mirrors and plants in homes, and speed limit signs on the streets. Maps made
  with it require it.
- Spawn points inside homes across the town, and the map's landmarks as
  starting points in the Spawn Selector mod when it is installed.

**The app**
- One window: search, generate, build, compile, install. Setup.bat downloads
  the tools, extracts tiles from your own game and checks everything.
- No Python needed beforehand: setup fetches the official python.org build into
  the KnoxMap folder when the PC has none.
- A dark, plain window with a link to the Discord.
- Presets and fine tuning for zombies, living space, heights,
  woodland, parking and more.
- A patched, headless map compiler so compiling needs no clicks in WorldEd.

**Behind the scenes**
- Follows OpenStreetMap's tile, Nominatim and Overpass usage policies; credits
  OpenStreetMap in every map; ships the compiler with its GPL source. See
  [docs/LEGAL.md](docs/LEGAL.md).
- `tools/selftest.py` runs the whole pipeline offline, `tools/audit_layouts.py`
  stress-tests floor plans, and GitHub Actions runs both on every push.
