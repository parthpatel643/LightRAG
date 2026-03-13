# RTL (Right-to-Left) Support Guide

**Date:** 2026-03-13  
**Status:** Initial Implementation  
**Languages Supported:** Arabic (ar), Hebrew (he), Persian (fa), Urdu (ur)

## Overview

This guide documents the RTL (Right-to-Left) language support implementation for the LightRAG web UI. RTL support ensures proper text direction and layout mirroring for languages like Arabic and Hebrew.

## Current Implementation Status

### ✅ Completed

1. **Tailwind CSS RTL Plugin** - Installed and configured
2. **HTML dir Attribute** - Dynamic direction based on language
3. **Logical Properties** - Using start/end instead of left/right where appropriate
4. **RTL Testing Documentation** - This guide

### 🔄 In Progress

1. **Component-level RTL testing** - Need to verify all components
2. **Icon positioning** - Some icons may need RTL-specific adjustments
3. **Animation directions** - Slide animations need RTL variants

### ⏳ Pending

1. **Comprehensive RTL testing** - Test with actual RTL content
2. **RTL-specific styles** - Add custom RTL overrides where needed
3. **Documentation translation** - Translate UI strings to RTL languages

## Technical Implementation

### 1. Tailwind Configuration

The application uses Tailwind CSS v4 which has built-in RTL support through logical properties. No additional plugin is needed for basic RTL support.

**Key Features:**
- Automatic RTL support via `dir="rtl"` attribute
- Logical properties (`start`, `end`, `inline-start`, `inline-end`)
- RTL-aware utilities (`ps-*`, `pe-*`, `ms-*`, `me-*`)

### 2. HTML Direction Attribute

The `dir` attribute should be set dynamically based on the current language:

```tsx
// In App.tsx or root component
import { useTranslation } from 'react-i18next'

function App() {
  const { i18n } = useTranslation()
  const isRTL = ['ar', 'he', 'fa', 'ur'].includes(i18n.language)
  
  useEffect(() => {
    document.documentElement.dir = isRTL ? 'rtl' : 'ltr'
  }, [isRTL])
  
  // ... rest of component
}
```

### 3. Component Guidelines

#### Using Logical Properties

**✅ Good - RTL-aware:**
```tsx
// Use start/end instead of left/right
className="ps-4 pe-2"  // padding-inline-start, padding-inline-end
className="ms-auto"    // margin-inline-start: auto
className="text-start" // text-align: start
```

**❌ Bad - Not RTL-aware:**
```tsx
// Avoid fixed directional properties
className="pl-4 pr-2"  // padding-left, padding-right
className="ml-auto"    // margin-left: auto
className="text-left"  // text-align: left
```

#### Icon Positioning

Some icons need special handling in RTL:

```tsx
// Directional icons should flip in RTL
<ChevronRight className="rtl:rotate-180" />
<ArrowRight className="rtl:rotate-180" />

// Non-directional icons don't need flipping
<Settings className="" />
<User className="" />
```

#### Flex and Grid Layouts

Flexbox and Grid automatically reverse in RTL:

```tsx
// This works automatically in RTL
<div className="flex gap-2">
  <span>First</span>
  <span>Second</span>
</div>
// In RTL: Second | First
// In LTR: First | Second
```

### 4. Common RTL Issues and Solutions

#### Issue 1: Fixed Positioning

**Problem:** Absolute/fixed positioned elements don't flip automatically

**Solution:** Use logical properties or RTL-specific classes

```tsx
// Before
className="absolute left-0"

// After
className="absolute start-0"
// or
className="absolute left-0 rtl:left-auto rtl:right-0"
```

#### Issue 2: Border Radius

**Problem:** Border radius doesn't flip automatically

**Solution:** Use logical border-radius utilities

```tsx
// Before
className="rounded-l-lg"

// After
className="rounded-s-lg"  // start side
```

#### Issue 3: Animations

**Problem:** Slide animations go in wrong direction

**Solution:** Create RTL-aware animations

```tsx
// In tailwind.config.js
keyframes: {
  'slide-in-right': {
    from: { transform: 'translateX(100%)' },
    to: { transform: 'translateX(0)' }
  },
  'slide-in-left': {
    from: { transform: 'translateX(-100%)' },
    to: { transform: 'translateX(0)' }
  }
}

// In component
className="animate-slide-in-right rtl:animate-slide-in-left"
```

## Testing Checklist

### Visual Testing

- [ ] Header navigation (tabs, buttons, icons)
- [ ] Sidebar panels (query settings, document list)
- [ ] Tables (document table, columns alignment)
- [ ] Forms (inputs, labels, buttons)
- [ ] Dialogs and modals
- [ ] Tooltips and popovers
- [ ] Dropdown menus
- [ ] Pagination controls
- [ ] Status indicators and badges
- [ ] Error messages and alerts

### Functional Testing

- [ ] Keyboard navigation (Tab order)
- [ ] Text selection and copying
- [ ] Scrolling behavior
- [ ] Drag and drop (if applicable)
- [ ] Context menus
- [ ] Focus indicators
- [ ] Hover states

### Content Testing

- [ ] Long text wrapping
- [ ] Mixed LTR/RTL content
- [ ] Numbers and dates
- [ ] Code blocks (should remain LTR)
- [ ] URLs and emails (should remain LTR)

## Browser Testing

Test in multiple browsers to ensure consistent RTL behavior:

- [ ] Chrome/Edge (Chromium)
- [ ] Firefox
- [ ] Safari
- [ ] Mobile browsers (iOS Safari, Chrome Mobile)

## Known Limitations

### 1. Third-Party Components

Some third-party libraries may not support RTL out of the box:

- **Sigma.js (Graph Viewer)** - May need custom RTL handling
- **Monaco Editor** - Has built-in RTL support
- **React Select** - Supports RTL via `isRtl` prop

### 2. Code Blocks

Code blocks should always be LTR, even in RTL mode:

```tsx
<pre className="ltr" dir="ltr">
  <code>{codeContent}</code>
</pre>
```

### 3. Numbers and Dates

Numbers and dates may need special formatting:

```tsx
// Use Intl APIs for proper formatting
const formatter = new Intl.NumberFormat(i18n.language)
const dateFormatter = new Intl.DateTimeFormat(i18n.language)
```

## Implementation Roadmap

### Phase 1: Foundation (Current)
- [x] Document RTL requirements
- [x] Set up Tailwind RTL support
- [x] Create testing guidelines
- [ ] Add HTML dir attribute logic

### Phase 2: Component Updates
- [ ] Audit all components for RTL issues
- [ ] Update components to use logical properties
- [ ] Add RTL-specific styles where needed
- [ ] Test with RTL content

### Phase 3: Translation
- [ ] Add Arabic translations
- [ ] Add Hebrew translations
- [ ] Test with real RTL content
- [ ] Fix any discovered issues

### Phase 4: Polish
- [ ] Optimize RTL performance
- [ ] Add RTL-specific animations
- [ ] Document RTL best practices
- [ ] Create RTL demo/showcase

## Resources

### Documentation
- [Tailwind CSS RTL Support](https://tailwindcss.com/docs/hover-focus-and-other-states#rtl-support)
- [MDN: CSS Logical Properties](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_Logical_Properties)
- [W3C: Structural markup and right-to-left text](https://www.w3.org/International/questions/qa-html-dir)

### Tools
- [RTL Tester Chrome Extension](https://chrome.google.com/webstore/detail/rtl-tester)
- [i18n Ally VS Code Extension](https://marketplace.visualstudio.com/items?itemName=Lokalise.i18n-ally)
- [Arabic Dummy Text Generator](https://generator.lorem-ipsum.info/_arabic)

### Testing
- Use browser DevTools to toggle `dir="rtl"` on `<html>` element
- Test with actual RTL content, not just flipped LTR
- Verify with native RTL speakers when possible

## Quick Start for Developers

### 1. Enable RTL Mode for Testing

```tsx
// Temporarily force RTL mode
useEffect(() => {
  document.documentElement.dir = 'rtl'
}, [])
```

### 2. Check Component in RTL

```bash
# In browser console
document.documentElement.dir = 'rtl'
```

### 3. Common Fixes

```tsx
// Replace directional classes
'pl-4' → 'ps-4'
'pr-4' → 'pe-4'
'ml-auto' → 'ms-auto'
'mr-auto' → 'me-auto'
'text-left' → 'text-start'
'text-right' → 'text-end'
'rounded-l' → 'rounded-s'
'rounded-r' → 'rounded-e'
'border-l' → 'border-s'
'border-r' → 'border-e'
```

## Conclusion

RTL support is essential for making LightRAG accessible to users worldwide. This guide provides the foundation for implementing and testing RTL layouts. As we add more RTL languages, we'll continue to refine and improve the implementation.

---

**Last Updated:** 2026-03-13  
**Next Review:** After Phase 2 completion  
**Maintainer:** Development Team