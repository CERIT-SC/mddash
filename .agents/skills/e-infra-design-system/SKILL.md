---
name: e-infra-design-system
description: Use of the e-INFRA CZ Design System for consistent UI components and styling.
---
# e-INFRA CZ Design System

This project uses `@e-infra/design-system`. Follow these rules for all UI code.

## Setup

Install the `@e-infra/design-system` npm package (requires react@18|19, tailwindcss@v4).

```css
@import "tailwindcss";
@import "@e-infra/design-system/setup.css";
@source "../node_modules/@e-infra/design-system/dist";
```

`setup.css` is required — without it, no token class resolves to any value. Tailwind v3 is not supported.

## Dark mode

`.dark` class on `<html>` or `<body>`. No React provider. All tokens switch automatically.

```tsx
document.documentElement.classList.toggle('dark')
// or: <html className={isDark ? 'dark' : ''}>
```

Never write `dark:` overrides on semantic token classes — they are already theme-aware.

---

## Color tokens — never use raw hex or generic Tailwind colors

**Surfaces — use in order, never skip or reverse:**

| Token | Role | Light | Dark |
|---|---|---|---|
| `bg-background` | Page canvas | `#f4f5f9` | `#0f0e14` |
| `bg-surface` | Cards, inputs, sidebar | `#eaebf1` | `#191820` |
| `bg-surface-raised` | Popovers, modals, dropdowns | `#dddee6` | `#242330` |

Text: `text-text` · `text-text-muted` · `text-text-heading`
Border: `border-border` · `border-border-focus`

**Semantic tokens + ramps:**

| Token | Filled | Ramp |
|---|---|---|
| `primary` | `bg-primary text-primary-foreground` | `primary-50` … `primary-950` |
| `secondary` | `bg-secondary text-secondary-foreground` | `secondary-50` … `secondary-950` |
| `tertiary` | `bg-tertiary text-tertiary-foreground` | `tertiary-50` … `tertiary-950` |
| `info` | `bg-info text-info-foreground` | `info-50` … `info-950` |
| `success` | `bg-success text-success-foreground` | `success-50` … `success-950` |
| `warning` | `bg-warning text-warning-foreground` | `warning-50` … `warning-950` |
| `error` | `bg-error text-error-foreground` | `error-50` … `error-950` |

Ramps: `50–200` subtle tints · `300–600` interactive states · `700–950` strong accents
Neutral: `base-50` … `base-950`. Charts: `chart-1` … `chart-5`.

---

## Spacing — always responsive, never a single fixed value

| Token | Phone | Tablet `md:` | Desktop `lg:` | XL `xl:` | Role |
|---|---|---|---|---|---|
| `token-space-1` | `p-2` | `p-3` | `p-4` | `p-6` | Inner padding |
| `token-space-2` | `p-4` | `p-6` | `p-8` | `p-12` | Section gutter |
| `token-space-3` | `p-6` | `p-8` | `p-12` | `p-16` | Card padding |
| `token-space-4` | `p-8` | `p-12` | `p-16` | `p-24` | Section rhythm |

Page margin: `px-4 md:px-6 lg:px-8 xl:px-16`
Grid: `grid-cols-4 md:grid-cols-8 lg:grid-cols-12 gap-4 md:gap-6 lg:gap-8`

---

## Typography

```tsx
import { H1, H2, H3, H4, P, Lead, Strong, Small, Muted, Code, Link, Blockquote, List, OrderedList } from '@e-infra/design-system'
```

H1 `text-4xl font-bold tracking-tight` · H2 `text-3xl font-semibold` · H3 `text-2xl font-semibold` · H4 `text-xl font-semibold` · P `text-base leading-7` · Lead `text-lg leading-8` · Strong `text-base font-semibold leading-7` · Small `text-sm leading-6` · Muted `text-xs leading-5` · Code `text-sm font-mono bg-surface px-2 py-1 rounded` · Link `text-primary underline hover:no-underline`

All accept `className` (merged) and native element props.

---

## Component inventory — only import from this list

**Primitives** — accordion, alert, alert-dialog, aspect-ratio, avatar, badge, breadcrumb, button, calendar, card, carousel, checkbox, collapsible, dialog, dropdown-menu, form (Form, FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage), input, label, menubar, navigation-menu, progress, radio-group, scroll-area, select, separator, sheet, sidebar, skeleton, slider, sonner, stepper, switch, table, tabs, textarea, toggle, toggle-group, tooltip, panel

**Layout** — `Content` `ContentHeading` `ContentSubheading` `ContentBody` `Header` `HeaderContent` `HeaderLeft` `HeaderCenter` `HeaderRight` `Sidebar` `SidebarHeader` `SidebarContent` `SidebarFooter` `NavItem` `CollapsibleGroup`

**Compounds** — cookies-banner, feedback-form

Substitutions: Toast → `sonner` · Popover → `dialog`/`sheet` · DatePicker → `calendar` · Combobox → `select`

---

## Navigation rule

**Header-only**: navigation in `HeaderLeft` using `NavigationMenu` primitives.
**With sidebar**: sidebar owns ALL navigation. Header has utility controls only. Never both.

## Header

```tsx
// Header-only with navigation
<Header>
  <HeaderContent>
    <HeaderLeft>
      <Logo />
      <NavigationMenu>
        <NavigationMenuList>
          <NavigationMenuItem><NavigationMenuLink href="/">Home</NavigationMenuLink></NavigationMenuItem>
          <NavigationMenuItem>
            <NavigationMenuTrigger>More</NavigationMenuTrigger>
            <NavigationMenuContent><div className="grid gap-3 p-4 w-100">...</div></NavigationMenuContent>
          </NavigationMenuItem>
        </NavigationMenuList>
        <NavigationMenuIndicator />
      </NavigationMenu>
    </HeaderLeft>
    <HeaderRight>
      <Button variant="ghost" size="icon"><Bell className="h-4 w-4" /></Button>
      <Avatar><AvatarImage src="..." alt="User" /><AvatarFallback>U</AvatarFallback></Avatar>
    </HeaderRight>
  </HeaderContent>
</Header>

// With sidebar — no nav, container={false} removes max-width
<Header>
  <HeaderContent container={false}>
    <HeaderRight>...</HeaderRight>
  </HeaderContent>
</Header>
```

Custom background: `<Header className="bg-linear-to-r from-primary/90 to-secondary/90 border-transparent">`

## Sidebar

Fixed `w-64`. `NavItem` props: `isActive` (active style), `asChild` (child as anchor). `CollapsibleGroup` props: `title` (required), `defaultOpen`.

```tsx
<div className="flex min-h-screen">
  <Sidebar>
    <SidebarHeader><span className="font-semibold">App Name</span></SidebarHeader>
    <SidebarContent>
      <CollapsibleGroup title="Navigation" defaultOpen>
        <NavItem href="/" isActive>Home</NavItem>
        <NavItem href="/docs">Docs</NavItem>
      </CollapsibleGroup>
    </SidebarContent>
    <SidebarFooter><div className="px-4 py-2 text-xs text-text-muted">v1.0.0</div></SidebarFooter>
  </Sidebar>
  <div className="flex-1 flex flex-col">
    <Header><HeaderContent container={false}><HeaderRight>...</HeaderRight></HeaderContent></Header>
    <main className="flex-1 bg-background"><Content>...</Content></main>
  </div>
</div>
```

## Content

Always wrap page body in `Content`. Built-in spacing: `space-y-8 px-10 pb-10 mx-auto max-w-7xl` on container, `space-y-4` on body.

```tsx
<Content>
  <ContentHeading>Page Title</ContentHeading>
  <ContentSubheading>Section</ContentSubheading>
  <ContentBody><P>Content here.</P></ContentBody>
</Content>
```

---

## Key rules

1. Never use raw hex or generic Tailwind colors — always use token classes.
2. Surfaces must progress in order: `bg-background` → `bg-surface` → `bg-surface-raised`. Never skip or reverse.
3. Always apply spacing responsively: `p-6 md:p-8 lg:p-12`, not a single fixed value.
4. Dark mode = `.dark` class on a parent. No `dark:` overrides on token classes, ever.
5. Navigation belongs in either the header OR the sidebar — never both.
6. Wrap all page body content in `Content` — do not add ad-hoc padding to `<main>`.
7. Only import components from the inventory list. Anything else does not exist.
8. `setup.css` must be imported before any component usage in your global CSS.

---

## More info

- source code: https://github.com/CERIT-SC/design-system
- docs: https://design-system.e-infra.cz
