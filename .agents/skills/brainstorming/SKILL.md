---
name: brainstorming
description: Use for uncertain features, consequential design decisions, or substantial work needing a design boundary. Classify spikes, bounded changes, and architectural work before selecting its process.
---

# Brainstorming Ideas Into Designs

Resolve the intent and design the smallest useful implementation. Match the artifact to the path; do not use process as a substitute for resolving ambiguity.

Scale process to project size and risk. For a small discussion, work through the stages without creating tracking artifacts.

## Choosing A Path

Classify the work before detailed design and state the classification so the user can correct it:

| Path | Use when | Deliverable |
|---|---|---|
| **Spike** | The question is feasibility or discovery, and the output is a recommendation rather than kept code. | Approved probe and reported findings. |
| **Bounded** | The request changes a well-understood existing flow and has low implementation risk. | Short design in chat, explicit approval, direct implementation. |
| **Architectural** | The request creates a new project or subsystem, changes cross-component interfaces, or affects behavior consumers depend on. | Reviewed design, written spec when requested or required, and an implementation plan for substantial work. |

If implementation exposes hidden complexity, stop and reclassify upward. Do not silently continue under a lighter path.

## Design Gate

Read-only exploration is allowed before approval. Do not implement until the selected path's approval is complete:

- **Spike:** approve the question and investigation plan.
- **Bounded:** approve the short in-chat design.
- **Architectural:** approve the discussed design and the written spec or plan where one is used.

Approval applies to the artifact presented, not to later artifacts that do not yet exist. An explicit request to implement the same approach described in that artifact is approval; do not restart the workflow.

## Understanding The Idea

- Inspect relevant code, docs, tests, and recent changes before asking questions the project can answer.
- Assess scope independently of apparent simplicity. If requirements are unclear or independent subsystems are bundled together, clarify or decompose before implementing.
- Ask one focused question at a time when the answer materially affects behavior, scope, interfaces, compatibility, permissions, or acceptance criteria.
- Prefer multiple-choice questions with a recommendation; allow a differently framed answer.
- Establish the user, purpose, success criteria, and relevant operational, data, and platform constraints.
- Distinguish explicit requirements from assumptions. Mark material unknowns rather than converting guesses into decisions.

## Exploring Approaches

- Offer two or three approaches for genuine choices; do not manufacture alternatives for a settled or straightforward task.
- Lead with the recommended approach and explain why it fits requirements and existing code.
- Compare behavior, failure modes, maintenance cost, and reversibility, not merely implementation effort.
- Apply YAGNI without removing required behavior. Treat capability removal and public-interface changes as product decisions requiring approval.

## Presenting The Design

- Scale detail to complexity. A bounded design may be one paragraph; an architectural design may need architecture, data flow, error handling, and tests.
- Explain boundaries, failure behavior, verification, and compatibility risks that matter to the decision. Omit empty sections.
- Check agreement at decision boundaries rather than after every sentence.
- Revise the design when feedback exposes an incorrect assumption; do not preserve a discarded approach for ceremony.

## Architectural Design For Isolation And Clarity

- Give units a clear purpose, explicit interface, and understandable dependencies.
- Verify that contracts can be understood without reading internals and can change without surprising consumers.
- Choose boundaries that carry meaningful responsibility. More files or smaller functions are not inherently better.
- Keep domain rules and duplicated knowledge in one source of truth without coupling unrelated concepts because their code looks similar.

## Working In Existing Codebases

- Follow established patterns and reuse existing capabilities before introducing new ones.
- Include structural changes when current structure obstructs the requested work or makes it unsafe; connect the improvement to the goal.
- Keep cleanup within the requested scope. Report unrelated opportunities separately.

## After The Design

### Documentation

For a bounded design, the approved conversation is sufficient. For an architectural design, create a spec when requested or required by the project workflow; otherwise prefer keeping the approved design in the conversation. Use the project's convention or, absent one, `docs/specs/YYYY-MM-DD-<topic>-design.md`. Do not commit without explicit authorization.

Record behavior, interfaces, constraints, important tradeoffs, and verification. Omit conversation transcripts and discarded approaches unless their rationale constrains the final design.

### Spec Self-Review

Check the design before implementation or handoff:

1. **Completeness:** unresolved decisions are small, reversible, or explicitly assigned.
2. **Consistency:** requirements, boundaries, and data flow agree.
3. **Scope:** no unrequested features or bundled independent efforts.
4. **Clarity:** behavior, failures, and acceptance are specific enough to verify.

Fix issues inline. Use [spec-document-reviewer-prompt.md](spec-document-reviewer-prompt.md) only when the design's complexity warrants independent review.

### User Review

When a spec or written plan is created, give its path and ask the user to review it before implementation. Incorporate feedback and recheck affected sections; do not restart approval for unchanged decisions already accepted in the same artifact.
