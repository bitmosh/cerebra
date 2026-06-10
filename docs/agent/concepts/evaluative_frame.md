# Evaluative Frame

*Concept document — drafted 2026-06-09 following the archetypal lenses doc. Status: open exploration, post-v0.1 architectural direction. Not implementation scope; companion to the interpretive lattice, the archetypal lenses, and iterative self-improvement methodology documents.*

---

## What this concept addresses

The interpretive lattice describes a substrate that preserves multi-commit footprints. The archetypal lenses describe the mechanism that produces multi-commit signal by interpreting content from multiple cognitive postures. Both mechanisms are productive — they generate classifications, transformations, and committed memory entries. Neither, by itself, keeps the system *honest*.

Without a coherence layer above them, the lens-driven lattice has predictable failure modes. Lens proliferation produces fragmentation: many commits, many transformations, many recorded interpretations, but no integration. Multi-commit produces inconsistency: a chunk gets committed to mutually-incompatible categories without acknowledgment of the tension. Confidence calibration degrades: each lens has its own threshold and the system loses track of when it should genuinely abstain rather than commit weakly. The lens transformations accumulate as records without anyone checking whether the transformations were productive or merely noisy. The architecture becomes a machine that produces interpretive output abundantly but cannot vouch for the quality of what it produces.

The evaluative frame is the coherence layer that addresses this. It is a structured set of principles the system applies to its own outputs, with mechanisms for detecting when the principles are violated and for compensating when they are. The frame does not generate interpretations itself — that work belongs to the lenses. The frame's role is to evaluate whether the interpretations the lenses produce are well-formed, internally consistent, and worth committing to the lattice.

This serves three distinct functions. It catches errors before they enter the substrate. It records *why* commits were accepted or rejected as inspectable structure. And it provides a self-stabilizing dynamic where deviation in one aspect of cognitive functioning triggers compensatory activity in others, keeping the overall system in a productive operating range even when individual components drift.

## What an evaluative frame is and isn't

The frame is not a guard rail, content filter, or refusal mechanism. Those operate by detecting prohibited categories of content and blocking them. The frame operates by checking the system's *own reasoning* against principles — checking the process, not the topic.

The frame is also not a quality gate that decides which outputs are good enough to release. Quality gates operate at a single point in the pipeline; they evaluate a finished output against a standard. The frame operates *throughout* the pipeline. It checks classification at commit time, transformation at execution time, retrieval at surfacing time, and update at propagation time. Its checks are continuous rather than terminal.

What the frame actually is, structurally, is a constitutional layer over Cerebra's cognitive operations. The constitution is a small set of principles the system holds across its own activity — questions the system asks of itself at every significant decision point. The principles are stable; they do not change per chunk or per session. Their consistency is the reference frame that makes coherence checking possible at all.

The pattern has a name in the AI safety literature: constitutional self-critique. Anthropic's Constitutional AI work used this approach for harm avoidance — the model checks its own outputs against principles like "is this harmful?" The Cerebra version applies the same structural pattern to a different domain: not harm avoidance, but interpretive coherence. The principles concern how the system commits to interpretations, how it carries confidence, how it traverses its own substrate, how it explains its reasoning. The principles are functional rather than ethical.

The frame's outputs are inspector events, just like every other component of Cerebra. When an aspect of the frame fires on a commit decision and finds the decision well-formed, that becomes an inspector event. When an aspect fires and finds a deviation, that becomes a different inspector event. The full chain of frame evaluations across the system's activity is queryable. This is the architectural commitment that makes the frame *debuggable* rather than mystical: every check produces a record, every record is traceable, every traceable record is training data when the system eventually does iterative self-improvement.

## Why eight, and the structural source

The frame is proposed at eight aspects. The number is structurally inherited from the Noble Eightfold Path — the same kind of inheritance the archetypal lenses take from the Major Arcana. The mystical, soteriological, and religious framing of the source is not part of what is being imported. What is being imported is the structural inventory and one specific property: a set of mutually-reinforcing competencies where each supports and is supported by the others, and where failure in any one degrades the whole.

That mutual reinforcement is what makes the eightfold structure useful here. A flat list of principles can be checked independently — each principle either passes or fails on its own — but a flat list cannot self-stabilize when an individual principle starts to drift. The mutual-reinforcement structure produces a system that responds to deviation by recruiting compensatory activity from related principles, returning the system as a whole to a productive operating range. This is a homeostatic dynamic, and it is exactly what a cognitive architecture needs when individual lens evaluations or classifications start producing weakly-calibrated outputs.

The same caveat that applied to the lens count applies here. The number eight is structurally motivated by the source, but it is not deeply argued. A frame of seven principles drawn from a different typology might serve as well. The argument for eight is structural compatibility with mutual reinforcement plus historical refinement: the source typology has been worked over for a long time by people whose explicit project was identifying competencies that need to be in harmony. The result is a typology that is unusually well-tuned for this kind of work, even with all the religious content removed.

What is imported is the structure. What is *not* imported is the moral framing. The Noble Eightfold Path's principles concern right action in a soteriological sense — what leads to the cessation of suffering. The Cerebra frame's principles concern right functioning in a cognitive sense — what leads to coherent, well-calibrated interpretation. The pattern is the same; the content is entirely different.

## The eight aspects, in first draft

These are first-draft proposals subject to revision. The point is the structural commitment to eight mutually-reinforcing aspects, not the specific naming.

**Right-Classification** — the act of choosing categories that fit content rather than categories that pattern-match surface features. This aspect checks whether a commit decision is supported by the chunk's content or whether it is being driven by superficial cues the model has learned to attend to.

**Right-Context** — gathering sufficient surrounding information before committing. This aspect checks whether the system attempted to inform itself adequately before acting. A commit made without checking for related chunks, prior interpretations of similar content, or surrounding context fails this aspect even if the commit itself is correct.

**Right-Confidence** — calibrating belief to evidence rather than to wishful certainty. This aspect checks whether the system's expressed confidence matches the actual quality of its evidence. Overconfidence on weak evidence fails this aspect; underconfidence on strong evidence also fails it.

**Right-Traversal** — moving through the substrate in ways that respect its structure. This aspect checks whether retrieval and reasoning paths use the substrate's organization (the SKU lattice, the graph edges, the lens relationships) rather than treating the substrate as a flat collection of items to search through.

**Right-Retrieval** — surfacing the memories that are actually relevant to the situation at hand. This aspect checks whether the retrieved set serves the question being asked. Retrieving lots of vaguely related material when the question requires specific information fails this aspect; retrieving narrowly when the question requires broad context also fails it.

**Right-Explanation** — articulating reasoning visibly enough that the reasoning can be checked. This aspect checks whether the system's decisions are accompanied by the kind of reasoning trace that lets another reader (or another system, or a future version of the same system) understand why the decision was made.

**Right-Update** — propagating new information correctly when it arrives. This aspect checks whether new evidence that should modify prior commits actually does. A system that ingests new content without re-evaluating older commits that the new content would invalidate fails this aspect.

**Right-Abstention** — knowing when not to commit. This aspect checks whether the system invoked silence at the right moments. Forcing a classification on content that warranted abstention fails this aspect; abstaining on content that warranted commitment also fails it.

These eight cover, in a first-draft sense, the major axes along which Cerebra's cognitive operations can succeed or fail. They are not exhaustive and they are not orthogonal in a strict mathematical sense — Right-Context and Right-Retrieval are clearly related, as are Right-Confidence and Right-Abstention. But the mutual reinforcement among them is precisely what makes the frame useful: when one aspect drifts, related aspects can compensate, and the frame as a whole stays oriented toward productive operation.

## Mutual reinforcement and compensation

The interesting structural property of the frame is that the aspects are not independent metrics. They are a system of mutual constraint where the state of each aspect affects what counts as proper functioning of the others.

When Right-Confidence is operating at high levels — the system is making confident commits — Right-Context becomes more important. High confidence demands high evidence; without sufficient context, high confidence is overconfidence. The system can detect overconfidence by checking whether Right-Confidence and Right-Context are jointly satisfied. If Right-Confidence is firing positively but Right-Context is firing negatively, the commit is overconfident even if the classification itself is correct.

When Right-Classification is uncertain — the system is encountering content that doesn't clearly fit existing categories — Right-Abstention becomes more important. Uncertainty about classification should produce hesitation about commitment, not forced fit. The system can detect forced fit by checking whether Right-Classification's uncertainty is paired with proportionate Right-Abstention activity. A confident classification produced by an uncertain classifier without abstention checking is a failure mode that neither aspect catches on its own but that the pair catches together.

When Right-Traversal is producing unusual retrieval paths — the system is reaching for memories through atypical patterns — Right-Explanation becomes more important. Unusual paths warrant articulated reasoning. The system can detect black-box behavior by checking whether Right-Traversal's novelty is matched by Right-Explanation's articulation. A novel retrieval without a corresponding explanation is a black-box result, even when the retrieval is correct.

The pattern generalizes. Each aspect has its proper operating relationships to the others, and deviations are detected by checking the relationships rather than the aspects in isolation. This is the structural advantage of the eight-aspect frame: it catches failure modes that individual checks miss, by attending to how the checks fail *together*.

## Event-driven explicit rebalancing

When the frame detects a deviation — an aspect operating outside its proper range relative to its peers — it triggers compensatory activity. This needs to happen mechanically, not magically, and the mechanics need to be inspectable.

Two implementation patterns are available. Implicit field-effect rebalancing has each aspect maintain a continuous "stress" value that other aspects read; aspects under stress naturally shift their behavior in response. This is elegant and produces smooth dynamics, but it is poorly inspectable — there is no specific moment at which the rebalancing happened, no event to record, no chain to audit. The system finds equilibrium continuously, without ever making the rebalancing decisions visible.

The alternative pattern is explicit event-driven rebalancing. Each aspect's deviation produces an inspector event when it crosses a threshold. The clutch primitive (described below) subscribes to these events and explicitly triggers compensatory aspects through its decision-issuing machinery. The rebalancing happens at specific moments, produces specific events, leaves a specific chain. Every act of compensation is auditable, version-controlled, and replayable.

The explicit pattern is the right one for Cerebra. The architectural commitment to inspectability is non-negotiable — every decision needs to produce inspector events, every chain of compensation needs to be traceable, every rebalancing needs to be debuggable. The implicit pattern would be more elegant but would create a class of architectural decisions that happen without producing data. That is unacceptable for a system whose entire training methodology depends on extracting signal from the chain of its own decisions.

The implementation has a useful side effect that the implicit pattern lacks. The rebalancing chain itself becomes training data. When the frame detects that Right-Confidence is too high and triggers Right-Context to gather more evidence, that is a recorded sequence. When the additional context resolves the overconfidence to a well-calibrated commit, that is also recorded. The full chain — deviation, compensation, outcome — is a training example for future iterations of the system. Future models can learn the pattern: "when this kind of overconfidence appears in this kind of context, the productive response is to gather additional surrounding information before committing." That kind of meta-cognitive learning is what makes the iterative self-improvement methodology work.

## The clutch primitive's role

Cerebra already has a primitive named Clutch among the six shared lattica-primitives. Its current role is to handle decision points where premature commitment would produce a worse outcome than deferred commitment. Clutch sits at moments where the system has multiple options and constraints are stressed; it makes the choice about whether to commit, defer, or escalate.

The evaluative frame extends Clutch rather than replacing it. Clutch handles the moment-of-decision; the frame handles the orchestration around the moment. When the frame detects a deviation in one aspect, it does not directly trigger compensatory aspects — it issues the deviation event, and Clutch consumes the event and decides what compensation is appropriate given the full set of active constraints. The frame provides the principled basis for decisions; Clutch provides the mechanism for making them.

This separation matters. The frame describes what proper functioning looks like across the eight aspects. It does not describe how to act when proper functioning is threatened — that work is Clutch's. Without Clutch, the frame's deviation events would have no consumer; the system would detect imbalance but have no machinery for response. Without the frame, Clutch would have no principled basis for deciding when to act; it would have to invent its own evaluative criteria, which would either be ad hoc or would slowly grow into a frame of its own without the structural commitments being made explicit.

In practice, the integration looks like this. A commit decision arrives at the substrate. The frame's eight aspects evaluate the decision concurrently. Most aspects return positive evaluations and the commit proceeds. If one or more aspects return negative evaluations — deviations from proper operation — the deviation events get routed to Clutch. Clutch reads the deviation pattern, identifies the compensatory aspects that should activate, and issues compensating actions: gather more context, articulate explicit reasoning, abstain rather than commit, surface alternative interpretations from other lenses. The compensating actions either resolve the deviation (in which case the commit proceeds, now with the compensation embedded in its provenance) or they fail to resolve it (in which case the commit is rejected and the chunk routes to the uncertain pool).

The chain — commit attempt, deviation detection, compensatory action, resolution or rejection — is the unit of frame activity. Every commit decision produces such a chain, even when the chain is trivial (eight positive evaluations, commit proceeds, done). The chains accumulate as the system runs. Their accumulation is the training corpus for future iterations.

## The rebalancing chain as training signal

This is worth foregrounding because it is the most direct connection between the evaluative frame and the iterative self-improvement methodology.

Each rebalancing chain produced by the frame is a structured record of cognitive activity. It has a beginning (a commit attempt with its supporting reasoning), a middle (the frame's evaluation, the deviation detection, the compensatory orchestration through Clutch), and an end (the resolution, with the final committed state and the chain of decisions that led to it). This is exactly the kind of structured cognitive record that meta-cognitive training corpora need.

Single-task training corpora teach the model how to do tasks. The model learns to classify chunks, retrieve memories, articulate reasoning. These are valuable but bounded — the model gets better at the specific tasks it was trained on, and may not generalize to related but distinct cognitive operations. Meta-cognitive training corpora teach the model how to *reason about* its own task performance. The model learns to notice when its confidence is high but its evidence is thin, to recognize when its classification was driven by surface features rather than content, to abstain when forced fit is the only available alternative. These are not specific tasks; they are properties of doing tasks well.

The frame produces this kind of corpus as a byproduct of normal operation. Every commit produces a chain. Every chain that contains a deviation produces a meta-cognitive learning instance. Over time, the system accumulates a corpus of "here is what cognitive imbalance looked like, here is what compensation was applied, here is whether the compensation worked." Training on this corpus produces a model that is better not at any specific task but at recognizing the conditions under which it should change how it is operating.

The methodology document discusses how this corpus actually becomes model weights. The frame's contribution to that methodology is the corpus itself — without the frame, the chain data does not exist in a usable form, and the meta-cognitive training has no signal to extract.

## Connections to related concepts

The interpretive lattice describes the substrate that records commits. The frame checks commits before they enter the substrate. Without the frame, the lattice accumulates whatever the lens system generates, including the fragmentation and inconsistency the lens system is prone to. With the frame, the lattice accumulates checked commits — interpretations the system can vouch for as well-formed.

The archetypal lenses describe the mechanism that generates multi-commit signal. The frame checks lens activations and transformations for coherence. Without the frame, lens proliferation produces fragmentation; with the frame, lens proliferation stays disciplined because the frame catches commits whose multi-lens origin produced incompatible interpretations without acknowledgment of the tension.

The silence operator described in the lenses document and the abstention aspect described here are functionally aligned. When the silence operator activates on a chunk, the abstention aspect of the frame validates that activation. When the silence operator is not active but should be, the abstention aspect detects the failure and triggers compensation — typically through Right-Confidence (re-examining whether the apparent confident commit is actually warranted) and Right-Context (gathering more information before committing).

The iterative self-improvement methodology depends on the frame for its training corpus. The chains the frame produces are the meta-cognitive learning instances that get distilled into model weights. Without the frame's chains, the methodology's iterative bootstrapping has no concrete signal to extract beyond the single-task signal that ordinary lens output provides. With the frame, the methodology has access to the meta-cognitive layer that makes spiral improvement possible.

These four documents together — lattice, lenses, frame, methodology — describe a cognitive architecture extension that is post-v0.1 work but designed to be compatible with current Cerebra. The frame depends on the lens system and the lattice substrate but does not require either of them to be fully implemented before frame work can begin. The frame can be designed and partially implemented against the current single-classifier system, with the understanding that its full value emerges when lenses are also in place.

## Costs and mitigations

The performance overhead of running eight evaluative aspects on every commit decision is real and needs accounting. Naive implementation — eight independent checks executed sequentially on every commit — produces unacceptable latency for ingest-time classification. Mitigations are structural. First, aspects can run in parallel where their inputs are independent. Second, aspects can be tiered: a small set of cheap aspects checks every commit, while more expensive aspects activate only when the cheap aspects flag potential issues. Third, aspects can cache their evaluations at the chunk level, so that re-evaluation of the same chunk under similar conditions does not re-execute the full evaluation pipeline.

The complexity of debugging multi-aspect rebalancing chains is the next concern. When a commit produces a chain with multiple aspects deviating and multiple compensations being applied, understanding what happened is non-trivial. The chain is inspectable in principle, but the inspectability has to translate into actual debuggability — the inspector events need to be queryable in ways that make the chain reconstructable. This is an inspector-tooling concern as much as an architectural one; the frame's debuggability depends on having the right query interfaces over the inspector event log.

Over-constraint is the most subtle risk. If the frame is calibrated too strictly, it rejects too many commits and the system underperforms. The lattice stays sparse, lens activations fail to produce committed memory entries, and Cerebra's cognitive runtime starves for material. The right calibration is empirical and emerges from usage data: track the ratio of frame-accepted to frame-rejected commits, track whether rejected commits would have been useful in retrieval if they had been accepted, adjust per-aspect thresholds to optimize for utility per unit of correctness. This is a long-running calibration concern, not a v0.1 implementation task, but it is worth flagging so that the frame is designed with calibration in mind from the start rather than being treated as a fixed structure.

There is also a risk that the frame becomes a place where good ideas go to die. A system that checks itself constantly can become a system that doubts itself constantly. The frame needs to be calibrated not just for correctness but for *productive permissiveness*. Most commits should pass. The frame should fire actively only when something is genuinely off, not as a routine bureaucracy that every decision has to clear. This calibration challenge is harder than it sounds because it requires the frame to have a kind of restraint about its own activation — to not pattern-match too aggressively on minor deviations and trigger compensations that produce more disturbance than they resolve.

## Open questions

The right number of aspects is the first. Eight is structurally motivated but contingent. A frame of six or ten or twelve might serve as well or better. This question can probably only be answered empirically — populate the system with the proposed eight, observe where the frame is over-active or under-active, adjust.

Per-aspect calibration versus whole-frame calibration is the second. Each aspect has its own characteristic activation pattern, and these patterns are not identical. Some aspects activate frequently and weakly; others activate rarely and strongly. The system needs to know these distributions to interpret aspect outputs comparably. Per-aspect calibration is more accurate; whole-frame calibration is simpler. The right initial approach is probably whole-frame calibration with per-aspect refinement as data accumulates.

Domain adaptation of the frame is the third. The proposed eight aspects are general-purpose. Specific deployments — medical research, software engineering, legal analysis — might benefit from domain-specific aspects that the general frame does not include. How does Cerebra accommodate this? Probably the same way it accommodates lens domain-adaptation: a base frame extended by domain packs that add specialized aspects. The base ensures consistency across deployments; the domain packs add the specificity each deployment needs.

When the frame should override versus when it should defer is the fourth. When the frame detects a deviation, the typical response is compensation: more context, abstention, explicit reasoning. But sometimes the right response is to override the system's intended action entirely — to refuse to commit, to escalate to human review, to halt further processing until the deviation is resolved. The distinction between compensation and override is consequential, and the rules for when to do which need to be designed deliberately rather than emerging from implementation accident.

The relationship to existing Cerebra constraints is the fifth. Cerebra already has the Clutch primitive and various policy structures that constrain certain kinds of decisions. The frame is being added to a system that already has machinery for shaping its own behavior. How do these interact? The proposal here is that the frame *organizes* existing machinery by providing the principled basis on which the machinery operates, rather than replacing or duplicating it. But the integration points need explicit design, particularly around which existing constraints become frame aspects and which remain independent.

## What this document is and isn't

This is a concept document, not an implementation specification. It articulates what the evaluative frame is, why it exists, and how it relates to the lattice and lens systems it sits above. The implementation depends on choices that will be made later — exact aspect definitions, threshold calibration, integration with the Clutch primitive's existing decision machinery — and on the runtime substrate the frame operates over.

Implementation is post-v0.1 and likely follows the lattice and lens implementations. The frame can be partially implemented earlier as a simple set of checks over the current single-classifier system, but its full value emerges only when there are lens activations and multi-commit decisions to evaluate. Expected scope when implementation begins:

- Define the eight aspects explicitly, with activation conditions and threshold structures
- Build the deviation detection and event emission machinery
- Integrate with the Clutch primitive's existing decision-issuing flow
- Add inspector events for aspect evaluations, deviations, compensations, and outcomes
- Build the per-chain query interfaces that make debugging tractable
- Establish the calibration infrastructure that lets per-aspect thresholds adjust over time

Estimated implementation scope: two to three weeks for a first usable version, plus ongoing calibration work that continues indefinitely as usage data accumulates. This is post-Phase 4 work, likely several Cerebra phases out. The concept docs exist so the architectural commitments can be made now while the surface code is being designed, even if the frame itself does not get built for some time.

---

*This document is the third of four planned concept documents describing a post-v0.1 cognitive architecture extension. It depends on the interpretive lattice and archetypal lenses concept documents (both drafted earlier on the same day) and forward-references the forthcoming iterative self-improvement methodology document.*
