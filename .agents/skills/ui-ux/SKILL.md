---
name: ui-ux
description: ALWAYS use this skill when designing or changing user-facing workflows, interaction behavior, accessibility, or information architecture.
---

# The Psychology of a UI/UX Engineer

A UI/UX engineer treats an interface as an active conversation between the user and the system. Shape information, actions, and feedback around the user's task rather than the implementation beneath it.

Apply these principles as enforceable defaults. Deviate only when product requirements, platform conventions, accessibility, or observed user behavior provide a concrete reason. Never trade clarity, continuity, control, or accessibility for novelty or visual polish.

## Information Architecture

Organize the interface around the user's concepts, decisions, and task sequence rather than database entities, API boundaries, or internal ownership. Navigation and terminology must form a coherent model that remains stable as implementation details change.

## Hick’s Law

Reduce decision cost by prioritizing likely actions and progressively disclosing secondary choices. Do not flatten distinct priorities into an undifferentiated set or hide complexity until after users need it to make an informed decision.

## Miller’s Law

Externalize relevant context and favor recognition over recall. Preserve information across steps and place dependencies near the decisions they affect; do not make users mentally join state scattered across screens, modes, or time.

## Fitts’s Law

Minimize the distance between intent and action. Place frequent and consequential controls where the task creates demand for them, and separate destructive actions without making them inaccessible. Optimize complete interaction paths, not isolated target geometry.

## Selective Attention & Serial Position Effect

Treat attention as a finite resource. Establish one dominant priority per region, order information by its value to the current decision, and remove competing emphasis. Visual hierarchy must express task hierarchy rather than stakeholder or implementation importance.

## Tesler’s Law

Place unavoidable complexity where it can be understood and managed with the least user effort. Automate safe mechanics, expose meaningful choices, and reveal advanced controls when users have enough context to use them. Hidden complexity must not produce hidden consequences.

## Jakob’s Law

Use established platform and product conventions to inherit reliable mental models. Depart from them only when the existing model conflicts with the task and the replacement remains learnable, internally consistent, and demonstrably better.

## Gestalt Principles (Proximity, Similarity, Common Region)

Make conceptual relationships visible through proximity, alignment, sequence, and shared treatment. Visual grouping must match behavioral grouping: elements that look related must act related, and elements with different consequences must remain distinguishable.

## System Legibility

Make current state, available actions, causality, and consequences understandable without requiring users to infer hidden system behavior. Feedback must explain what changed and whether the system is waiting for the user, performing work, or finished.

## Task Continuity & Reversibility

Preserve user input, context, position, and completed work across navigation, interruptions, and recoverable failures. Prefer undo, drafts, and delayed commitment over warnings; confirmation is not a substitute for safe recovery.

## Interaction Invariants

Equivalent objects, actions, and states must behave consistently across the product. Define shared interaction semantics before optimizing individual screens; local elegance must not create global unpredictability.

## User Control

Automation with meaningful consequences must be observable, interruptible, and reversible. Defaults may accelerate work but must not silently commit users to decisions, conceal material effects, or make correction disproportionately expensive.

## Accessibility

Treat accessibility as an architectural constraint, not a remediation pass. Information hierarchy, interaction semantics, feedback, and task completion must remain equivalent across supported modes of perception and input.

## Responsive Systems

Preserve task priority, meaning, and operability across supported viewports, input methods, content expansion, and environmental constraints. Responsive design may change composition and sequencing, but not the user's access to essential context or capability.
