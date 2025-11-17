# OnisAI — Uber Trip Logger & Zone Intelligence

OnisAI is a **modular pipeline** that watches the Uber Driver app, parses offers via OCR, calculates metrics, and builds databases of trips, summaries, and pickup/dropoff intelligence.  
It acts like a **personal co-pilot**, helping to decide which trips are worth it, and learning patterns of traffic delays and bad zones.

## Key Features
- OCR screenshot extraction via Apple Vision
- Automated trip parsing and metrics computation
- JSON grid databases for pickup/dropoff intelligence
- 1-tap and 2-tap iOS Shortcut integration
- Automatic SUMMARY + RAW log building
- Zone intelligence, guardrail logic and delay detection
---
Modular Structure

OnisAI/
├── UnifiedDB.txt              # Master daily log
├── State/.uber_triplogger_state.json
├── TripDB/TripLog-YYYY-MM-DD-SUMMARY.txt
├── UberDB/TripLog-YYYY-MM-DD-RAW.txt
├── GridZoneDB/
│   ├── pickup_grid_db.json
│   ├── dropoff_grid_db.json
│   ├── pickup_zone_summary.txt
│   ├── dropoff_zone_summary.txt
│   └── grid_guardrail_log.txt
└── Bot/
    ├── Main.py                # 1-tap entrypoint
    ├── Orchestrator.py        # 2-tap entrypoint
    ├── ACCCOBuilder.py        # accept/complete stamping
    ├── SARWBuilder.py         # RAW+SUMMARY builder + pruning
    ├── PUDOBuilder.py         # pickup/dropoff grid summaries
    ├── PUDOUpdater.py         # refresh grid after SARW
    ├── BDOBuilder.py          # bad dropoff detector
    ├── metrics.py             # £/mi, £/min, fuel, status
    ├── notify.py              # iOS push notifications
    ├── ocr_ios.py             # Vision OCR + Photos asset guard
    ├── parse.py               # OCR parsing + pickup rules
    ├── store.py               # DB/file helpers
    └── utils.py               # shared utilities
    
    
    

## 🚦 Runtime Flow (Sequence)

@startuml
actor Driver
rectangle "iOS Shortcut (1-tap)" as Shortcut
rectangle "AssistiveTouch (2-tap)" as AT
rectangle Main
rectangle Orchestrator
rectangle ACCCOBuilder
rectangle SARWBuilder
rectangle PUDOUpdater
rectangle PUDOBuilder
rectangle UnifiedDB
rectangle TripDB
rectangle UberDB
rectangle GridZoneDB

Driver --> Shortcut : 1-tap
Shortcut --> Main
Main --> UnifiedDB : append TRIP
Main --> Driver : push notif

Driver --> AT : 2-tap
AT --> Orchestrator
Orchestrator --> ACCCOBuilder : stamp ACCEPTED/COMPLETE
Orchestrator --> SARWBuilder : only if latest TRIP completed
SARWBuilder --> UberDB : RAW
SARWBuilder --> TripDB : SUMMARY
SARWBuilder --> UnifiedDB : prune
SARWBuilder --> PUDOUpdater
PUDOUpdater --> PUDOBuilder
PUDOBuilder --> GridZoneDB
@enduml


______________





@startuml OnisAI-Components
package "OnisAI/Bot" {
  [Main.py] --> [ocr_ios.py]
  [Main.py] --> [parse.py]
  [Main.py] --> [metrics.py]
  [Main.py] --> [notify.py]
  [Main.py] --> [utils.py]
  [Main.py] --> [store.py]

  [ACCCOBuilder.py] --> [UnifiedDB.txt]
  [SARWBuilder.py] --> [UnifiedDB.txt]
  [SARWBuilder.py] --> [PUDOUpdater.py]
  [PUDOUpdater.py] --> [PUDOBuilder.py]
  [BDOBuilder.py] --> [SARWBuilder.py]

  [store.py] --> [TripDB / UberDB]
  [PUDOBuilder.py] --> [GridZoneDB]
  [BDOBuilder.py] --> [bad_dropoffs.json]
}

artifact "UnifiedDB.txt" as UDB
artifact "TripDB/*.SUMMARY" as SUMMARY
artifact "UberDB/*.RAW" as RAW
artifact "GridZoneDB/*.json/txt" as GRID
artifact "bad_dropoffs.json" as BDO

[Main.py] --> UDB
[SARWBuilder.py] --> RAW
[SARWBuilder.py] --> SUMMARY
[PUDOBuilder.py] --> GRID
[BDOBuilder.py] --> BDO
@enduml
