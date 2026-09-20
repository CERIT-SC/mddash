---
name: react
description: ALWAYS use this skill when working with React code, JSX/TSX, hooks, forms, UI state, or React application architecture.
---

# React Standards

## Architecture

- Follow the existing UI structure and directory conventions; do not add layers for a local change.
- Extract shared components and non-React utilities when they have demonstrated reuse or clarify a meaningful boundary.
- Prefer props and composition for coordination; use context or URL state when the required lifetime and consumers justify them.

## Data And State

- Reuse the project's server-state solution. Add caching, retries, or a new state library only for demonstrated requirements.
- Put state in URL search params when bookmarking, sharing, or navigation history is part of the behavior.
- Keep state local unless other consumers or persistence requirements require a wider owner.
- Use effects for synchronization with external systems.
- Include complete effect dependencies or restructure the code.
- Clean up subscriptions, timers, network requests, and observers.
- Use `AbortController` or equivalent cleanup for raw fetch effects.

## Forms And Validation

- Validate user input at the form boundary.
- Use schema-backed form validation for non-trivial forms.
- Keep validation schemas close to the form or shared with the API contract when the project has shared validation.
- Pair each input with accessible labels, descriptions, field-level errors, and submit state.

## Errors And Feedback

- Surface user-visible failures through the project's shared error notification pattern.
- Reuse existing notifications or show failures near the affected action; do not introduce a global notification system for a local change.
- Use inline field errors for validation failures.
- Handle reachable empty, loading, and error states. Offer retries or partial results when the operation supports them.

## Styling

- Use the project's design-system primitives and theme tokens.
- Define shared colors, radii, spacing, and semantic variants in the existing theme layer.
- Use semantic tokens for UI intent: background, foreground, muted, primary, destructive, and border.
- Reuse established visual tokens; do not build a design system solely to eliminate a local value.

## Accessibility And UX

- Add ARIA for behavior native HTML cannot express.
- Keep keyboard navigation, focus management, labels, and visible focus states intact.
- Pair color with text, iconography, or structure for meaning.
- Preserve responsive task clarity across viewport sizes.

## Performance

- Use stable keys from data identity.
- Add memoization when there is a measured render cost or a stable API contract requires it.
- Split heavy routes or widgets when bundle size or loading behavior warrants it.

## Verification

- Run the relevant typecheck, lint, component tests, or build after meaningful UI changes.
- Use behavior-focused tests for forms, data states, error states, and accessibility-critical interactions.
