<!-- source row_id: api-97b1b6a1 -->

Title: Proof-Queued Consensus: A Distributed Checkpointing Protocol That Treats Zero-Knowledge Verification as the Consensus Bottleneck

Thesis:
The buildable path for combining zero-knowledge proof, distributed systems, and consensus protocols is to redesign consensus around proof-queue limits: zero-knowledge proof imposes latency, memory, and proof-size constraints; distributed systems contributes batching, backpressure, and horizontal proving; consensus protocols must therefore become proof-queued checkpoint systems that finalize only when batched validity evidence clears a dedicated verification pipeline, replacing raw signature checks with proof verification [Polygon Improvement Proposal PIP-49: ZK Checkpointing; zkVerify Documentation: Core Architecture; zkVerify Documentation: zkVerifyJS Reference / Domain Management; zkVerify Documentation: Handle Valid Proof / Mainchain API].

The System:
Build a checkpointing network with three layers.

1. Consensus layer: proof-backed checkpoints  
Use a checkpoint protocol in the style of Polygon’s ZK Checkpointing, where an off-chain prover generates a proof that a majority of validators voted for a checkpoint, and the base chain verifies the proof instead of directly verifying validator signatures [Polygon Improvement Proposal PIP-49: ZK Checkpointing]. This makes zero-knowledge proof structurally essential to consensus itself, not an external audit artifact.

2. Distributed proving and verification layer: bounded aggregation domains  
Run checkpoint proofs through a verification-focused distributed system modeled on zkVerify: a Substrate-based chain specialized for proof verification and batching, with verifier pallets for multiple proof systems and batch receipts published as Merkle roots for downstream chains [zkVerify Documentation: Core Architecture]. Each checkpoint domain uses explicit queue controls: aggregationSize up to 128 proofs and queueSize up to 16 pending aggregations [zkVerify Documentation: zkVerifyJS Reference / Domain Management]. If the queue fills, the pipeline hard-stops ingress through CannotAggregate or DomainStorageFull until an aggregation is published [zkVerify Documentation: Handle Valid Proof / Mainchain API]. That means consensus must respect backpressure from the proof system.

3. Proof production layer: horizontal and recursive compression  
Use horizontally scalable provers where adding physical machines cuts proof-generation time proportionally while preserving total runtime cost, as described by Polygon’s Type 1 prover [Polygon blog: Upgrading Every EVM Chain to ZK: Introducing the Type 1 Prover]. Use recursive proof machinery where available, since Plonky2 is explicitly positioned for recursive aggregation and Ethereum verification, with a reported recursive proof time of 170 ms on a MacBook Pro and proofs shrinkable to about 45 kB in size-optimized mode at roughly 20 s proving time [Polygon blog: Introducing Plonky2]. This makes aggregation strategy a first-class consensus parameter.

The constraint collision is direct.

- Zero-knowledge proof’s hardest constraint is proving and verification cost under real latency and memory ceilings. Concrete systems report 92 ms proving and 23 ms verification for a 1920-byte credential in Vega, with 108 kB proofs and a 464 kB proving key; an 896-byte credential reports 62 ms proving, 17 ms verification, and 83 kB proofs on a commodity client device [Microsoft Research publication: Vega: Low-Latency Zero-Knowledge Proofs over Existing Credentials]. Other systems trade speed for compactness: Plonky2 can produce about 45 kB proofs but at roughly 20 s proving time in size-optimized mode [Polygon blog: Introducing Plonky2]. Scribe scales to 2^28-gate circuits on commodity hardware using only 2 GB of memory with 10–35% proving-latency overhead over HyperPlonk [IACR ePrint 2024/1970: Scribe: Low-memory SNARKs via Read-Write Streaming]. Hobbit reports 8×–56× prover-time gains and up to 23× less total space across four applications [USENIX Security 2025: Hobbit: Space-Efficient zkSNARK with Optimal Prover Time]. These facts show that proof systems are bounded by latency, memory, and size tradeoffs, not by abstract correctness alone.

- Imposing that constraint onto distributed systems forces the distributed layer to stop acting like an unbounded mempool and instead behave like a bounded proof factory. zkVerify’s aggregationSize and queueSize limits, plus hard stop events when domains are full, are exactly the required shape [zkVerify Documentation: zkVerifyJS Reference / Domain Management; zkVerify Documentation: Handle Valid Proof / Mainchain API]. Spice shows why: batching raises throughput but adds latency because individual requests must wait for batch verification before confirmation; on a 16-server cluster it reports 488–1167 TPS using batching and a multi-writer storage primitive [Microsoft Research / OSDI paper: Proving the correct execution of concurrent services in zero-knowledge]. Therefore the distributed system must surface proof backlog as an explicit control signal to consensus.

- Consensus protocols must become proof-scheduled rather than signature-scheduled. ZKsync already uses batches, generates a validity proof for each batch, and finalizes after the L1 contract verifies both the proof and data availability [ZKsync Docs: Introduction / L1 contracts]. Its published timing exposes the consequence: proof generation for a batch typically takes about 1 hour, and overall finality is around 3 hours; adding an aggregation step increases objective finality while lowering submission cost [ZKsync Docs: Finality / Gateway Features]. ZKsync OS points to the target end-state: sustained >15K TPS, horizontally scalable proving, approximately 1-second block proofs, and minutes-to-Ethereum finality using Airbender [ZKsync Docs: ZKsync OS Overview]. The conclusion is strict: consensus cannot define finality independently of proof pipeline capacity.

This yields one concrete design: Proof-Queued Consensus.

- Validators produce votes for checkpoints.
- A prover cluster horizontally scales checkpoint proof generation [Polygon blog: Upgrading Every EVM Chain to ZK: Introducing the Type 1 Prover].
- Proofs enter bounded aggregation domains with queue and batch limits [zkVerify Documentation: zkVerifyJS Reference / Domain Management].
- The verification chain batches proofs and emits Merkle-root receipts for downstream settlement [zkVerify Documentation: Core Architecture].
- The settlement contract accepts checkpoint finality only after proof verification, matching the validity-proof settlement model used by ZKsync and the signature-replacement model proposed in PIP-49 [ZKsync Docs: Introduction / L1 contracts; Polygon Improvement Proposal PIP-49: ZK Checkpointing].

The novelty is not “use ZK in consensus.” The novelty is making queue saturation, aggregation width, recursive compression choice, and proving scale-out explicit consensus variables.

Interdependence proof:
- Remove zero-knowledge proof: the system collapses back to direct validator-signature verification and loses the core checkpoint transformation that PIP-49 defines, where proof verification replaces on-chain signature verification [Polygon Improvement Proposal PIP-49: ZK Checkpointing]. It also loses the validity-proof settlement model that lets batch state transitions be finalized by succinct verification [ZKsync Docs: Introduction / L1 contracts].

- Remove distributed systems: the system cannot manage proof verification as a production pipeline. It loses batching, queue bounds, and backpressure controls such as aggregationSize, queueSize, CannotAggregate, and DomainStorageFull [zkVerify Documentation: zkVerifyJS Reference / Domain Management; zkVerify Documentation: Handle Valid Proof / Mainchain API]. It also loses the demonstrated throughput gains and latency tradeoff from batched zero-knowledge execution in Spice [Microsoft Research / OSDI paper: Proving the correct execution of concurrent services in zero-knowledge].

- Remove consensus protocols: the proofs no longer decide finality. They become auxiliary attestations instead of the mechanism by which checkpoints or batch state transitions are accepted. That eliminates the essential role seen in ZK Checkpointing and ZKsync settlement, where proof verification determines whether consensus output is finalized on the base chain [Polygon Improvement Proposal PIP-49: ZK Checkpointing; ZKsync Docs: Introduction / L1 contracts].

Failure mode:
If checkpoint production exceeds bounded aggregation capacity, zkVerify-style queues fill, CannotAggregate or DomainStorageFull fires, and consensus finality stalls behind the proof publication pipeline [zkVerify Documentation: Handle Valid Proof / Mainchain API].  
If aggregation is increased to recover throughput, Spice’s tradeoff applies: latency rises because confirmations wait for batch verification, pushing consensus into slower finality windows [Microsoft Research / OSDI paper: Proving the correct execution of concurrent services in zero-knowledge].

Open question:
What is the optimal consensus rule for adapting checkpoint frequency to real-time proof backlog when proof systems span fast low-latency modes like Vega, recursive aggregation modes like Plonky2, and long-latency batch-finality regimes like current ZKsync [Microsoft Research publication: Vega: Low-Latency Zero-Knowledge Proofs over Existing Credentials; Polygon blog: Introducing Plonky2; ZKsync Docs: Finality / Gateway Features]?