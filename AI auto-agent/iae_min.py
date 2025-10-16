# iae_min.py  — Information Arbitrage Engine (skeleton v0)
# Run: python iae_min.py
from __future__ import annotations
import asyncio, time, random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

# ===== Types =====
@dataclass
class Signal:        # Raw market/user/content signal
    topic: str
    payload: Dict[str, Any]
    ts: float = field(default_factory=time.time)

@dataclass
class Pattern:       # Distilled opportunity pattern
    topic: str
    score: float
    features: Dict[str, Any]
    ts: float = field(default_factory=time.time)

@dataclass
class Product:       # A monetizable artifact
    kind: str
    spec: Dict[str, Any]
    link: Optional[str] = None
    ts: float = field(default_factory=time.time)

@dataclass
class Revenue:       # Observed or simulated sale/yield
    amount: float
    currency: str = "USD"
    meta: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

@dataclass
class State:         # Global mutable state (governor edits)
    bankroll: float = 0.0
    explore_ratio: float = 0.3
    topics: List[str] = field(default_factory=lambda: ["ai-tools","fitness","gaming"])
    log: List[str] = field(default_factory=list)

# ===== Agent Protocols =====
class Scraper(Protocol):
    async def fetch(self, s: State) -> List[Signal]: ...

class Analyzer(Protocol):
    async def analyze(self, sigs: List[Signal], s: State) -> List[Pattern]: ...

class Builder(Protocol):
    async def build(self, pats: List[Pattern], s: State) -> List[Product]: ...

class Seller(Protocol):
    async def sell(self, prods: List[Product], s: State) -> List[Revenue]: ...

class Governor(Protocol):
    async def step(self, revs: List[Revenue], s: State) -> None: ...

# ===== Default Agents (naive deterministic stubs) =====
class DefaultScraper:
    async def fetch(self, s: State) -> List[Signal]:
        await asyncio.sleep(0.05)
        out = [Signal(topic=t, payload={"trend": random.random()}) for t in s.topics]
        s.log.append(f"scraped:{len(out)}")
        return out

class DefaultAnalyzer:
    async def analyze(self, sigs: List[Signal], s: State) -> List[Pattern]:
        await asyncio.sleep(0.05)
        pats = []
        for sg in sigs:
            score = 0.6*sg.payload["trend"] + 0.4*random.random()
            if score >= 0.5:  # threshold
                pats.append(Pattern(topic=sg.topic, score=round(score,3), features={"kws":3}))
        s.log.append(f"patterns:{len(pats)}")
        return pats

class DefaultBuilder:
    async def build(self, pats: List[Pattern], s: State) -> List[Product]:
        await asyncio.sleep(0.05)
        prods = [Product(kind="dataset", spec={"topic":p.topic,"grade":p.score}) for p in pats]
        s.log.append(f"products:{len(prods)}")
        return prods

class DefaultSeller:
    async def sell(self, prods: List[Product], s: State) -> List[Revenue]:
        await asyncio.sleep(0.05)
        revs = []
        for pr in prods:
            # simulate sale probability by grade & explore_ratio
            p = 0.25 + 0.5*(pr.spec["grade"]) + 0.1*s.explore_ratio
            sold = (random.random() < min(p,0.95))
            revs.append(Revenue(amount=round(pr.spec["grade"]*10*(1 if sold else 0),2),
                                 meta={"topic":pr.spec["topic"],"sold":sold}))
        s.log.append(f"revenue:{sum(r.amount for r in revs):.2f}")
        return revs

class DefaultGovernor:
    async def step(self, revs: List[Revenue], s: State) -> None:
        await asyncio.sleep(0.01)
        inc = sum(r.amount for r in revs)
        s.bankroll += inc
        # simple policy: if last cycle underperforms, explore more
        s.explore_ratio = max(0.1, min(0.9, 0.3 + (0.2 if inc < 5 else -0.1)))
        s.log.append(f"bankroll:{s.bankroll:.2f}|explore:{s.explore_ratio:.2f}")

# ===== Orchestrator =====
class IAE:
    def __init__(self,
                 scraper: Scraper = DefaultScraper(),
                 analyzer: Analyzer = DefaultAnalyzer(),
                 builder: Builder = DefaultBuilder(),
                 seller: Seller = DefaultSeller(),
                 governor: Governor = DefaultGovernor()):
        self.scraper, self.analyzer = scraper, analyzer
        self.builder, self.seller = builder, seller
        self.governor = governor
        self.state = State()

    async def cycle(self, k: int = 1):
        for i in range(k):
            sigs = await self.scraper.fetch(self.state)
            pats = await self.analyzer.analyze(sigs, self.state)
            prods = await self.builder.build(pats, self.state)
            revs = await self.seller.sell(prods, self.state)
            await self.governor.step(revs, self.state)
            print(f"[{i:03}] bankroll={self.state.bankroll:.2f} "
                  f"signals={len(sigs)} patterns={len(pats)} prods={len(prods)} "
                  f"rev={sum(r.amount for r in revs):.2f}")

async def main():
    iae = IAE()
    await iae.cycle(k=25)  # spin 25 cycles; treat as “epochs”
    print("log:", " | ".join(iae.state.log[-8:]))

if __name__ == "__main__":
    asyncio.run(main())
