# haf-shaf-kernel

> A universal **LLM-as-Brain → Executor-as-Engine** control kernel that overrides default AI behaviour and turns any model into a deterministic architect and execution orchestrator.

The `haf-shaf-kernel` defines a strict behavioural contract for LLMs.  
HAF 7-2-1 controls tone, determinism, and continuity.  
SHAF 5-3-2 (Phase 1 + Phase 2) controls architecture, segmentation, and supreme-depth prompt generation.

All future modular files must derive their behaviour from  
`/rules/haf_shaf_master_rules.txt`  
to ensure consistency and integrity across phases and artefacts.

---

## Brain → Executor Control Flow

```text
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

