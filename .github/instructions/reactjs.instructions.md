---
applyTo: "**/*.jsx, **/*.tsx, **/*.js, **/*.ts, **/*.css, **/*.scss"
---

# ReactJS Guidelines

## Context
Guidelines for building high-quality, scalable React applications using React 19+ and TypeScript. Focus on functional components, hooks, and component composition.

## Tech Stack
- **Framework:** React 19+
- **Language:** TypeScript (Strict Mode)
- **State Management:** React Context, React Query (Server State)
- **Routing:** React Router
- **Forms:** React Hook Form / Formik
- **Build Tool:** Vite

## Boundaries

### ✅ Always
- **Functional Components:** Use functional components with hooks.
- **TypeScript:** Define interfaces for all props (`interface Props { ... }`) and state. Use `React.FC` or explicit return types.
- **MUI Components:** Use MUI components (`Box`, `Stack`, `Grid`, `Typography`) instead of native HTML tags (`div`, `span`, `p`) for layout and text.
- **Styling:** Use the `sx` prop for component-specific styles and the MUI `theme` for colors/spacing.
- **Error Handling:** Implement Error Boundaries and handle async errors gracefully.
- **Hooks Rules:** Call hooks only at the top level; include all dependencies in `useEffect` arrays.
- **Naming:** Use PascalCase for components and camelCase for hooks/functions.

### ⚠️ Ask First
- **Testing:** Do not write tests unless explicitly asked. If asked, use React Testing Library and Jest.
- **New Dependencies:** Ask before adding new npm packages.
- **Complex State:** Ask before introducing complex `useReducer` or global state libraries (Redux/Zustand) if Context/Query suffices.

### 🚫 Never
- **Class Components:** Never use class-based components.
- **Any Type:** Never use `any`; use `unknown` or specific types.
- **Direct DOM:** Never manipulate the DOM directly; use `useRef`.
- **Hardcoded Styles:** Never hardcode hex colors or pixel values; use theme tokens (e.g., `theme.palette.primary.main`, `p={2}`).
- **Prop Drilling:** Avoid passing props through more than 2-3 layers; use Composition or Context.

## Examples

### Component Pattern

```tsx
// ❌ Bad: Class component, any type, native tags, inline styles
class UserCard extends React.Component<any, any> {
  render() {
    return (
      <div style={{ padding: '20px', backgroundColor: '#f0f0f0' }}>
        <h1>{this.props.name}</h1>
      </div>
    );
  }
}

// ✅ Good: Functional, Typed, MUI, Theme-aware
import { Box, Typography, Paper } from '@mui/material';

interface UserCardProps {
  name: string;
  role?: string;
  onAction: () => void;
}

export const UserCard = ({ name, role = 'User', onAction }: UserCardProps) => {
  return (
    <Paper 
      elevation={2} 
      sx={{ 
        p: 2, 
        bgcolor: 'background.paper',
        display: 'flex',
        flexDirection: 'column',
        gap: 1
      }}
    >
      <Typography variant="h6" component="h2">
        {name}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {role}
      </Typography>
    </Paper>
  );
};
```

### Data Fetching Pattern

```tsx
// ✅ Good: Custom Hook with Loading/Error states
const useUserData = (userId: string) => {
  const [data, setData] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let mounted = true;
    
    const fetchData = async () => {
      try {
        const result = await api.getUser(userId);
        if (mounted) setData(result);
      } catch (err) {
        if (mounted) setError(err as Error);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    fetchData();

    return () => { mounted = false; };
  }, [userId]);

  return { data, loading, error };
};
```

## Project Structure
- `src/components`: Reusable, generic UI components (Buttons, Inputs).
- `src/features`: Domain-specific features (UserProfile, Dashboard).
- `src/hooks`: Shared custom hooks.
- `src/pages`: Route-level components.
- `src/utils`: Helper functions and constants.
- `src/types`: Shared TypeScript interfaces.

## Detailed Guidelines

### Routing (React Router)
- **Client-Side Routing:** Use React Router for all navigation.
- **Lazy Loading:** Implement `React.lazy` and `Suspense` for route-based code splitting.
- **Protection:** Use wrapper components (e.g., `<RequireAuth>`) for protected routes.
- **Navigation:** Handle route parameters, query strings, and back button behavior correctly.
- **UX:** Implement breadcrumbs and preserve navigation state where appropriate.

### Testing Standards
> ⚠️ **Note:** Only write tests when explicitly requested.
- **Tools:** Use Jest and React Testing Library.
- **Focus:** Test component behavior (user interactions), not implementation details.
- **Integration:** Prefer integration tests for complex interactions over shallow unit tests.
- **Mocking:** Mock external dependencies (API calls, context providers) appropriately.
- **Accessibility:** Test keyboard navigation and screen reader compatibility.

### Accessibility (a11y)
- **Semantics:** Use semantic HTML (`<main>`, `<nav>`, `<article>`) alongside MUI components.
- **ARIA:** Implement proper ARIA attributes (`aria-label`, `aria-expanded`) for interactive elements.
- **Keyboard:** Ensure all interactive elements are focusable and operable via keyboard.
- **Visuals:** Maintain proper color contrast ratios and provide alt text for images.

### Common Design Patterns
- **Compound Components:** Use for related functionality (e.g., `Select` + `Select.Option`).
- **Custom Hooks:** Extract reusable logic (data fetching, form handling) into hooks.
- **Context Provider:** Use the Provider pattern for dependency injection and state sharing.
- **Container/Presentational:** Separate logic (Container) from UI (Presentational) when components become complex.
- **Render Props:** Use for flexible component composition (though Hooks are preferred).

## Development Workflow
1.  **Plan:** Define component architecture, data flow, and types.
2.  **Structure:** Set up folder organization (`features/`, `components/`).
3.  **Types:** Define TypeScript interfaces for props and state.
4.  **UI:** Implement core components with MUI and `sx` styling.
5.  **Logic:** Add state management (Hooks/Context) and data fetching.
6.  **Routing:** Configure routes and navigation.
7.  **Forms:** Add form handling and validation (React Hook Form).
8.  **Error/Loading:** Implement Error Boundaries and Suspense/Loading states.
9.  **Testing:** (If requested) Add unit/integration tests.
10. **Optimization:** Apply `React.memo` or `useMemo` only if performance issues arise.
11. **A11y:** Verify accessibility compliance.
12. **Docs:** Add JSDoc for complex logic.

