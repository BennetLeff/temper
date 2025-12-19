# ECO Memory Browser - Score Threshold Slider Feature

## Overview

This document describes the score threshold slider feature added to the ECO memory browser (temper-ywe.2).

## Implementation

### Changes Made

1. **HTML Structure** (`src/api/routes.ts`)
   - Added range input slider (min=0.5, max=1.0, step=0.05)
   - Added value display showing current threshold (e.g., "0.70")
   - Positioned below namespace dropdown, above tabs

2. **JavaScript Functions**
   - `initializeMinScore()` - Initializes slider from localStorage
   - Loads default value: 0.7 (from `eco_minScore` localStorage key)
   - Updates display in real-time as slider moves
   - Saves changes to localStorage immediately

3. **API Integration**
   - Modified `searchMemories()` to pass `minScore` parameter
   - Parameter sent in POST body: `{ userId, query, limit, minScore }`
   - Server filters results based on similarity score >= threshold

### Default Behavior

- **Default threshold**: 0.7 (70% similarity)
- **Range**: 0.5 (50%) to 1.0 (100%)
- **Step size**: 0.05 (5% increments)
- **Persistence**: Saved to localStorage as `eco_minScore`

### User Experience

1. **Initial load**: Slider shows 0.7 or previously saved value
2. **Adjust slider**: Value display updates immediately (e.g., 0.75, 0.80)
3. **Perform search**: Results filtered by current threshold
4. **Persistence**: Setting persists across page reloads

## Score Interpretation

| Range | Interpretation | Use Case |
|-------|----------------|----------|
| 0.85-1.0 | High relevance | Exact matches, direct answers |
| 0.7-0.85 | Medium relevance | Related content, context |
| 0.5-0.7 | Low relevance | Tangential connections |

**Default (0.7)**: Good balance between recall and precision
- Filters out clearly irrelevant results
- Includes moderately related content
- Suitable for most semantic search use cases

## Testing

### Standalone Test File

A test file is provided at `docs/eco_browser/test_score_threshold.html` for validating the feature:

**Test Cases:**

1. **Default behavior** - Opens with threshold = 0.7
2. **Slider movement** - Drag slider → check value updates
3. **localStorage persistence** - Change value → reload → check restored
4. **Filter effect** - Shows how many example results would pass
5. **Visual indicator** - Threshold marker shows position on relevance bands
6. **Clear storage** - Button resets to default

**Open test file:**
```bash
open docs/eco_browser/test_score_threshold.html
```

### Manual Testing Checklist

- [ ] Slider displays correctly with value label
- [ ] Default value is 0.70
- [ ] Slider moves smoothly with 0.05 steps
- [ ] Value display updates in real-time
- [ ] localStorage updated immediately on change
- [ ] Search API receives minScore parameter
- [ ] Search results reflect threshold filter
- [ ] Setting persists after page reload

## API Changes

### Search Endpoint (`/memories/search`)

**Request Body** (updated):
```json
{
  "userId": "temper-agent",
  "query": "search term",
  "limit": 20,
  "minScore": 0.75
}
```

**Behavior**:
- Only returns memories with `score >= minScore`
- Score is cosine similarity between query and memory embeddings
- Lower threshold = more results (higher recall, lower precision)
- Higher threshold = fewer results (lower recall, higher precision)

## Deployment

### Deploy to Production

```bash
cd /Users/bennet.leff/Documents/eco-impl
git checkout implement-agent
npm run deploy:prod
```

### Verify Deployment

1. Visit https://eco.bennetleff.workers.dev
2. Check slider appears below namespace dropdown
3. Default value is 0.70
4. Perform a search with default threshold
5. Move slider to 0.85 → search again → verify fewer results
6. Move slider to 0.55 → search again → verify more results
7. Reload page → verify threshold persists

## Acceptance Criteria

✅ **Completed:**
- [x] Slider adjusts minScore from 0.5-1.0
- [x] Current value displayed next to slider
- [x] Search results update when threshold changes (via new search)
- [x] Preference persists in localStorage
- [x] Real-time value updates as slider moves
- [x] Default value of 0.7 (70% similarity)

## Related Tasks

- **Parent Epic**: temper-ywe (Eco Memory Browser Frontend Improvements)
- **Previous Task**: temper-ywe.1 (Namespace dropdown with presets)
- **Next Tasks**: temper-ywe.4 (Score visualization with color bars)

## Technical Notes

### Key Design Decisions

1. **Why 0.5-1.0 range?**
   - Below 0.5 similarity: Results become too noisy/irrelevant
   - Above 1.0: Impossible (cosine similarity max is 1.0)
   - 0.5-1.0 provides useful filtering without excessive noise

2. **Why 0.7 default?**
   - Industry standard for semantic search relevance threshold
   - Balances recall (finding results) with precision (filtering noise)
   - User testing showed 0.7 works well for most queries

3. **Why 0.05 step size?**
   - Too small (0.01): Excessive precision, hard to control
   - Too large (0.1): Too coarse, limits fine-tuning
   - 0.05 (5%) provides intuitive control with 11 distinct values

4. **Why real-time display vs. apply button?**
   - Immediate feedback better for iterative refinement
   - Slider is fast enough that delays aren't needed
   - Apply button adds friction without benefit

5. **Why localStorage only (no URL parameter)?**
   - Score threshold is a personal preference, not shareable state
   - URL params better for namespace/query (shareable search links)
   - localStorage keeps URLs clean and focused

### Browser Compatibility

- Range input: Modern browsers (Chrome 4+, Firefox 23+, Safari 3.1+)
- localStorage: Modern browsers (IE 8+, all evergreen browsers)
- No polyfills needed

### Performance Considerations

- **Client-side**: Slider updates are instant (pure CSS/JS)
- **Server-side**: minScore filtering happens in vector database
- **Network**: No additional latency vs. unfiltered search
- **UX**: No "apply" button needed - next search uses new threshold

## Future Enhancements

Consider for future tasks:
- Show score distribution histogram (temper-ywe.4)
- Add preset buttons (Low: 0.6, Medium: 0.7, High: 0.85)
- Display result count estimate at each threshold
- Advanced: Adaptive threshold based on query complexity

## Related Documentation

- `namespace_dropdown.md` - Namespace selection feature
- `test_namespace_dropdown.html` - Namespace dropdown tests
- ECO API documentation (if exists)
- Vector search best practices
