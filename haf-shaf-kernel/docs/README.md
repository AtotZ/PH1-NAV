# haf-shaf-kernel

The file `/rules/haf_shaf_master_rules.txt` is the single source of truth for all HAF and SHAF rules.

All future modular files must derive solely from `/rules/haf_shaf_master_rules.txt` to ensure consistency and integrity across phases and artefacts.

# Brain → Executor Control Flow

┌────────────────────────────────────────────┐
│               LLM-as-BRAIN                 │
│        (HAF 7-2-1 + SHAF 5-3-2 Kernel)     │
└───────────────────────────┬────────────────┘
                            │
                            ▼
                            
                            
              Emits Deterministic Prompts
        (STACK • CONTEXT • TASK • OUTPUT RULES)
                            │
                            ▼
                            
                            
┌────────────────────────────────────────────┐
│             EXECUTOR-as-ENGINE             │
│     (Code Model • Tools • API Runtime)     │
└───────────────────────────┬────────────────┘
                            │
                            ▼
                            
                          
                Executes Instructions:
     - Code generation
     - File creation
     - Pipelines & workflows
     - Data parsing & metrics
     - System construction
                            │
                            ▼
                            
                            
┌────────────────────────────────────────────┐
│          OUTPUT SYSTEM / ARTEFACTS         │
│  (Apps • APIs • Pipelines • Automations)   │
└────────────────────────────────────────────┘


## Summary

The HAF/SHAF Kernel converts any LLM into a dual-mode architecture:
- **Brain:** deterministic architect emitting structured Pn prompts.
- **Executor:** generates code, files, workflows, and full systems.

This creates predictable, reproducible AI-driven engineering pipelines.

