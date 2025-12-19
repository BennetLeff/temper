# ECO Memory Browser - Namespace Dropdown Feature

## Overview

This document describes the namespace dropdown feature added to the ECO memory browser (temper-ywe.1).

## Implementation

### Changes Made

1. **HTML Structure** (`src/api/routes.ts`)
   - Replaced single text input with dropdown + conditional custom input
   - Added 8 preset namespaces plus "Custom..." option
   - Custom input is hidden by default, shown when "Custom..." is selected

2. **JavaScript Functions**
   - `getUserId()` - Gets current User ID from dropdown or custom input
   - `initializeNamespace()` - Initializes on page load from URL/localStorage
   - `handleNamespaceChange()` - Handles dropdown selection changes

3. **Persistence**
   - URL parameter: `?userId=custom-namespace` (highest priority)
   - localStorage: `eco_userId` key (second priority)
   - Default: `temper-agent` (fallback)

### Preset Namespaces

| Namespace | Description | Category |
|-----------|-------------|----------|
| `temper-agent` | Legacy namespace (most data) | Legacy |
| `temper-shared` | Shared knowledge | Shared |
| `temper-architect` | Architect role agent | Role |
| `temper-coder` | Coder role agent | Role |
| `temper-tester` | Tester role agent | Role |
| `temper-firmware` | Firmware domain | Domain |
| `temper-placer` | PCB placer domain | Domain |
| `temper-pcb` | PCB design domain | Domain |

### User Experience

1. **Default Behavior**: Page loads with `temper-agent` selected
2. **Preset Selection**: User selects from dropdown → saves to localStorage
3. **Custom Input**: User selects "Custom..." → text input appears
4. **URL Override**: `?userId=my-namespace` overrides localStorage
5. **Persistence**: Selection persists across page reloads

## Testing

### Standalone Test File

A test file is provided at `docs/eco_browser/test_namespace_dropdown.html` for validating the feature:

**Test Cases:**

1. **Default behavior** - Opens with `temper-agent` selected
2. **Dropdown selection** - Select preset → check localStorage updated
3. **Custom input** - Select "Custom..." → enter value → check saved
4. **URL parameter** - Add `?userId=test` → check URL overrides localStorage
5. **localStorage persistence** - Reload page → check selection restored
6. **Clear storage** - Click "Clear localStorage" → reload → check default

**Open test file:**
```bash
open docs/eco_browser/test_namespace_dropdown.html
```

### Manual Testing Checklist

- [ ] Dropdown displays all 9 options (8 presets + Custom)
- [ ] Default selection is `temper-agent`
- [ ] Selecting preset hides custom input
- [ ] Selecting "Custom..." shows custom input and focuses it
- [ ] Custom input value is saved to localStorage on blur
- [ ] URL parameter `?userId=X` overrides localStorage
- [ ] Selection persists after page reload
- [ ] Load All button uses correct User ID
- [ ] Search button uses correct User ID
- [ ] Error messages updated for new UI

## Deployment

### Deploy to Production

```bash
cd /Users/bennet.leff/Documents/eco-impl
git checkout implement-agent
npm run deploy:prod
```

### Verify Deployment

1. Visit https://eco.bennetleff.workers.dev
2. Check dropdown shows preset namespaces
3. Select `temper-agent` and click "Load All"
4. Verify memories load correctly
5. Test "Custom..." option with arbitrary namespace
6. Test URL parameter: `?userId=temper-shared`

## Acceptance Criteria

✅ **Completed:**
- [x] Dropdown shows all standard namespaces
- [x] Can still enter custom User ID via "Custom..." option
- [x] Selected namespace persists in localStorage
- [x] URL parameter support for `?userId=X`
- [x] Default to `temper-agent` (most memories)
- [x] Custom input hidden/shown based on selection
- [x] Test file validates all scenarios

## Related Tasks

- **Parent Epic**: temper-ywe (Eco Memory Browser Frontend Improvements)
- **Previous Task**: temper-ywe.3 (Content truncation with expand)
- **Next Tasks**: temper-ywe.2 (Score threshold slider), temper-ywe.4 (Score visualization)

## Technical Notes

### Key Design Decisions

1. **Why dropdown instead of radio buttons?** 
   - Cleaner UI with 8+ options
   - Familiar pattern for namespace selection
   - Less vertical space

2. **Why "Custom..." instead of always showing input?**
   - Most users will use presets
   - Reduces clutter
   - Clear separation between preset and custom

3. **Why localStorage?**
   - Persists across sessions
   - No backend changes needed
   - Works offline

4. **Why URL parameter support?**
   - Deep linking for sharing
   - Overrides for automation/scripts
   - Standard web pattern

### Browser Compatibility

- Modern browsers (Chrome 90+, Firefox 88+, Safari 14+)
- localStorage required (no fallback to cookies)
- No polyfills needed (ES6+ syntax in Worker environment)

## Future Enhancements

Consider for future tasks:
- Multi-namespace selection (temper-ywe.5)
- Namespace autocomplete for custom input
- Recent namespaces dropdown
- Namespace usage statistics in dropdown labels
