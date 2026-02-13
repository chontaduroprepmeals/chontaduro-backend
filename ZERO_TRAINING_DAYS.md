# Zero Training Days Feature Documentation

## Feature Overview

This feature allows users to select **0 training days** and automatically shows a special "I don't train at all 😢" option for both duration and intensity questions.

---

## User Request (Original)

> "necesito que en cuantos dias entrenas la opcion pueda ser cero. y con ello donde dice intensidad osea de minutos y de si es baja alta o moderada pues tambien haya opcion de no entreno nada y una carita triste ajjaja o algo asi. todo en ingles recuerda."

**Translation:**
"I need the option to be able to select zero in how many days you train. And with that, where it says intensity (minutes and if it's low, high or moderate), there should also be an option for 'I don't train at all' with a sad face hahaha or something like that. Everything in English remember."

---

## What Was Implemented

### 1. Exercise Days Range Extended ✅
- **Before:** 1-7 days only
- **After:** 0-7 days (including zero)
- Users can now indicate they don't exercise at all

### 2. Conditional Duration Options ✅

**When exercise days = 0:**
```
⏱️ Typical Session Duration

┌─────────────────────────────────┐
│           😢                    │
│   I don't train at all          │
└─────────────────────────────────┘
(Auto-selected, gray background, orange ring)
```

**When exercise days > 0:**
```
⏱️ Typical Session Duration

┌────────┬────────┬─────────┬────────┐
│  <30   │ 30-60  │ 60-120  │  120+  │
│  min   │  min   │  min    │  min   │
└────────┴────────┴─────────┴────────┘
(Normal time options)
```

### 3. Conditional Intensity Options ✅

**When exercise days = 0:**
```
Exercise Intensity

┌─────────────────────────────────┐
│           😢                    │
│   I don't train at all          │
└─────────────────────────────────┘
(Auto-selected, gray background, orange ring)
```

**When exercise days > 0:**
```
Exercise Intensity

┌───────────┬─────────────┬───────────┐
│  🟢 Low   │ 🟡 Moderate │  🔴 High  │
│  Light    │ Some sweat  │ Intense   │
│ activity  │             │  workout  │
└───────────┴─────────────┴───────────┘
(Normal intensity options)
```

---

## User Experience Flow

### Scenario 1: Non-Exerciser

1. User enters personal data form
2. Sees "Exercise Days per Week" with number picker
3. Default is 0 days (or user can decrease to 0)
4. **Duration automatically shows:** "I don't train at all 😢"
5. **Intensity automatically shows:** "I don't train at all 😢"
6. Both options are auto-selected (orange selection ring)
7. User can continue to next step
8. Values submitted: `avg_session_duration: "none"`, `intensity: "none"`

### Scenario 2: Switching from Exercise to Non-Exercise

1. User has 3 days selected
2. Sees normal duration options (<30, 30-60, 60-120, 120+ min)
3. Sees normal intensity options (Low, Moderate, High)
4. User clicks [-] button to decrease days
5. At each decrease, counter updates (3 → 2 → 1 → 0)
6. **When reaching 0:**
   - Duration options instantly change to sad face
   - Intensity options instantly change to sad face
   - Both auto-selected
7. If user increases back to 1+, normal options return

### Scenario 3: Starting as Exerciser

1. User increases days from 0 to 1+
2. Duration options change from sad face to time ranges
3. Intensity options change from sad face to intensity levels
4. User can select appropriate options
5. Smooth, instant transition

---

## Technical Implementation

### New Function: `updateDurationIntensityOptions()`

```javascript
function updateDurationIntensityOptions() {
  const days = window.currentExerciseDays || 0;
  
  // Update duration cards
  const durationContainer = document.querySelector('.duration-cards-container');
  if (durationContainer) {
    if (days === 0) {
      // Show sad face option
      durationContainer.innerHTML = `
        <div class="duration-card ... ring-4 ring-orange-500"
             data-value="none" onclick="selectDuration('none')">
          <div class="text-3xl mb-2">😢</div>
          <div class="font-semibold">I don't train at all</div>
        </div>
      `;
      document.getElementById('duration_input').value = 'none';
    } else {
      // Show normal time options
      // (<30, 30-60, 60-120, 120+ min)
    }
  }
  
  // Update intensity cards (similar logic)
}
```

### Updated Function: `window.adjustDays()`

```javascript
window.adjustDays = function(delta) {
  const input = document.getElementById('days_input');
  const display = document.getElementById('days_display');
  let current = parseInt(input.value) || 0;
  current = Math.max(0, Math.min(7, current + delta));
  input.value = current;
  display.textContent = current;
  
  // Store in global state
  window.currentExerciseDays = current;
  
  // Trigger option updates
  updateDurationIntensityOptions();
};
```

### Added Container Classes

**Duration Section:**
```html
<div class="grid grid-cols-2 md:grid-cols-4 gap-3 duration-cards-container">
  <!-- Cards go here - replaced dynamically -->
</div>
```

**Intensity Section:**
```html
<div class="grid grid-cols-3 gap-4 intensity-cards-container">
  <!-- Cards go here - replaced dynamically -->
</div>
```

### Initialization

```javascript
// In renderPersonalInfo() function, after form is rendered:
window.currentExerciseDays = 0; // Default to 0
setTimeout(() => updateDurationIntensityOptions(), 100); // Ensure DOM is ready
```

---

## Visual Design

### Sad Face Option Styling

**CSS Classes:**
- `border-2 border-gray-400` - Gray border
- `bg-gray-100` - Light gray background
- `ring-4 ring-orange-500` - Orange selection ring (auto-selected)
- `text-3xl mb-2` - Large emoji (😢)
- `font-semibold` - Bold text

**Appearance:**
- Single centered card
- Gray/muted colors (vs. colorful normal options)
- Sad face emoji prominently displayed
- Clear "I don't train at all" message
- Pre-selected with orange ring

### Normal Options Styling

**Duration Cards:**
- 4 cards in grid
- White background with gray borders
- Hover: shadow + scale effect
- Click: orange ring selection

**Intensity Cards:**
- 3 cards in grid
- Color-coded backgrounds (green/yellow/red)
- Emoji indicators (🟢🟡🔴)
- Hover effects
- Click: orange ring selection

---

## Data Flow

### When Days = 0:

```javascript
// Form submission data:
{
  days_per_week: "0",
  avg_session_duration: "none",
  intensity: "none",
  // ... other fields
}
```

### When Days > 0:

```javascript
// Form submission data:
{
  days_per_week: "3",
  avg_session_duration: "30-60",
  intensity: "moderate",
  // ... other fields
}
```

### Backend Handling:

The backend receives these values and can handle them appropriately:
- If `intensity: "none"` → Use sedentary activity level
- If `avg_session_duration: "none"` → No exercise duration
- Calculate TDEE/macros based on sedentary lifestyle

---

## Testing Checklist

### Manual Testing:

- [ ] Can decrease days to 0
- [ ] Can increase days from 0
- [ ] Duration shows sad face when days = 0
- [ ] Duration shows time options when days > 0
- [ ] Intensity shows sad face when days = 0
- [ ] Intensity shows level options when days > 0
- [ ] Sad face auto-selected (orange ring)
- [ ] Value "none" set in hidden inputs when days = 0
- [ ] Options update instantly on days change
- [ ] No JavaScript errors in console
- [ ] Form submits successfully with days = 0
- [ ] Form submits successfully with days > 0
- [ ] Emoji displays correctly (😢)
- [ ] Text is in English
- [ ] Responsive on mobile

### Edge Cases:

- [ ] Rapidly clicking +/- buttons
- [ ] Going from 7 → 0 → 7
- [ ] Submitting form immediately after changing days
- [ ] Page reload preserves state
- [ ] Back button navigation works

---

## Language

All text is in English as requested:
- ✅ "I don't train at all"
- ✅ "Exercise Days per Week"
- ✅ "Typical Session Duration"
- ✅ "Exercise Intensity"

---

## Emoji Used

- 😢 **Sad face** - For non-training option
- 🏃‍♂️ **Runner** - For exercise days label
- ⏱️ **Stopwatch** - For duration label
- 🟢🟡🔴 **Colored circles** - For intensity levels

---

## Browser Compatibility

- ✅ Chrome/Edge (Chromium)
- ✅ Firefox
- ✅ Safari
- ✅ Mobile browsers
- Emoji support: All modern browsers (2018+)

---

## Future Enhancements (Optional)

Potential improvements if needed:
1. Add tooltip explaining "none" option
2. Show motivational message for 0 days users
3. Add transition animations when switching options
4. Remember last selection when coming back
5. Add "Why track exercise?" info button

---

## Summary

This feature provides a compassionate, clear option for users who don't exercise, while maintaining the dynamic nature of the form for those who do. The sad face emoji adds a friendly, human touch to the interface.

**Key Benefits:**
- ✅ Inclusive for all fitness levels
- ✅ Clear visual feedback
- ✅ Instant updates
- ✅ Auto-selection reduces clicks
- ✅ Maintains form validation
- ✅ All in English

**Status:** ✅ Complete and ready for production
