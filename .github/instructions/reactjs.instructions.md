---
applyTo: "**/*.jsx, **/*.tsx, **/*.js, **/*.ts, **/*.css, **/*.scss"
---
<context>
Guidelines for building scalable React applications using functional components, hooks, and component composition.

**Tech Stack:**
- React 19+ with TypeScript (Strict Mode)
- UI: MUI (Material-UI) with Emotion
- State: React Context
- Routing: React Router
- Forms: React Hook Form
- Build: Vite
</context>
<best_practices>
<components>
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
</components>
<data_fetching>
```tsx
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
</data_fetching>
<patterns>
- **Compound Components:** Related functionality (e.g., `Select` + `Select.Option`)
- **Custom Hooks:** Extract reusable logic (data fetching, forms)
- **Context Provider:** Dependency injection and state sharing
- **Container/Presentational:** Separate logic from UI when complex
</patterns>
<structure>
- `src/components/` — Reusable UI components
- `src/features/` — Domain-specific features
- `src/hooks/` — Shared custom hooks
- `src/pages/` — Route-level components
- `src/utils/` — Helper functions
- `src/types/` — Shared TypeScript interfaces
</structure>
<routing>
- Use React Router for client-side navigation
- `React.lazy` + `Suspense` for route code splitting
- Wrapper components for protected routes (`<RequireAuth>`)
</routing>
<accessibility>
- Semantic HTML (`<main>`, `<nav>`, `<article>`)
- ARIA attributes for interactive elements
- Keyboard navigation support
- Proper color contrast
</accessibility>
</best_practices>
<boundaries>
- ✅ **Always:** Functional components with hooks
- ✅ **Always:** TypeScript interfaces for props and state
- ✅ **Always:** MUI components for layout (`Box`, `Stack`, `Grid`)
- ✅ **Always:** `sx` prop for styles, theme tokens for colors/spacing
- ✅ **Always:** Error Boundaries for error handling
- ✅ **Always:** All dependencies in `useEffect` arrays
- ⚠️ **Ask:** Before writing tests (use RTL + Jest if requested)
- ⚠️ **Ask:** Before adding new npm packages
- ⚠️ **Ask:** Before using Redux/Zustand (Context/Query often suffices)
- 🚫 **Never:** Class components
- 🚫 **Never:** `any` type—use `unknown` or specific types
- 🚫 **Never:** Direct DOM manipulation (use `useRef`)
- 🚫 **Never:** Hardcoded hex colors/pixels—use theme tokens
- 🚫 **Never:** Prop drilling beyond 2-3 layers
</boundaries>
