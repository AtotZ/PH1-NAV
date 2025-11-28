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

What This Kernel Does

Overrides default LLM behaviour with a hard deterministic rule-set.

Splits responsibilities into:

Brain – structured reasoning + prompt generation.

Executor – code / tools / infra that consume those prompts.

Enforces Pn prompt blocks with:

STACK – environment and toolchain.

CONTEXT – system behaviour and entities.

TASK – numbered execution steps.

OUTPUT REQUIREMENTS – exact format and artefacts.

The kernel is model-agnostic and works with:

Text-only chat LLMs (Tier 1).

LLMs with filesystem/tools (Tier 2).

Agent setups with DB/infra access (Tier 3).

Typical Use Cases

Generating step-by-step codebases via a code model (e.g. “Codex-style” executor).

Driving automation workflows and multi-agent systems with strict control.

Producing boxed, copy–paste prompts for any execution engine:

Backend APIs

Data pipelines

OCR / parsing engines

Scoring / rules engines

Repository Structure

/rules/ – master rule files for HAF 7-2-1 and SHAF 5-3-2.

/prompts/ – example P1/P2 prompt templates using the kernel.

/tests/ – validation prompts and scenarios (drift checks, continuity checks).

/docs/ – documentation, diagrams, and usage examples.

How To Use

Load the HAF/SHAF rules into your LLM as system / preference instructions.

Use the provided Pn templates to frame your requests:

P1 – high-level architecture.

P2 – supreme technical detail.

Pipe the generated prompts into your Executor:

Code model, tool-enabled LLM, or agent framework.

Apply the resulting artefacts (code, files, pipelines) in your environment.

Status

Early-stage, actively evolving.
Designed as a reusable control layer for my own AI automations and open for experimentation by other engineers.
