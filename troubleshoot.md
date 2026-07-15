# Troubleshoot: "Nothing happens after clicking start scrolling"

## Symptom

Clicking "start scrolling" appeared to do nothing — the keyword form stayed
on screen, no card or loading state appeared — even though the backend
logs showed the request completed and a `card_N.json` file was written to
`outputs/`.

That combination (server-side success, zero visible client-side change) is
the key clue: JavaScript's `fetch()` call fired and completed correctly.
The bug was not in the network request — it was in what happened to the
DOM afterward.

## Root cause

`frontend/style.css` had:

```css
.setup-screen {
  min-height: 100vh;
  display: flex;
  ...
}

.feed-screen {
  height: 100vh;
  display: flex;
  ...
}
```

and `frontend/app.js` toggles screens with the HTML `hidden` attribute:

```js
setupScreen.hidden = true;
feedScreen.hidden = false;
```

The browser's built-in behavior for `hidden` is a single UA (user-agent)
stylesheet rule: `[hidden] { display: none; }`. **CSS cascade order
resolves by origin before specificity**: any normal-priority rule in the
page's own stylesheet beats a normal-priority rule in the browser's
default stylesheet, regardless of which selector is more specific. Because
`style.css` declared `display: flex` directly on `.setup-screen` and
`.feed-screen`, that author rule always won over the UA's `[hidden] {
display: none }` — so setting `.hidden = true/false` in JavaScript changed
the DOM attribute correctly, but it had **zero visual effect**. Both
screens were always laid out as `display: flex`, stacked on top of each
other in normal document flow.

In practice this meant:

- On page load, `feed-screen` (which starts with the `hidden` attribute in
  `index.html`) was already being flex-rendered — just empty, and pushed
  below the setup card (`min-height: 100vh` on `.setup-screen` means you'd
  have to scroll down to ever notice it).
- Clicking "start scrolling" ran `startFeed()`, which correctly kicked off
  the SSE request (hence the real backend activity and generated files) —
  but `setupScreen.hidden = true` didn't hide the form, so the screen the
  user was looking at never changed. From the user's point of view: click,
  then nothing.

This is a well-known CSS gotcha: **never put an explicit `display` value
on a class you also toggle via the `hidden` attribute** — the two fight,
and per the cascade, your CSS silently wins.

## The fix

Added one rule near the top of `frontend/style.css`:

```css
[hidden] {
  display: none !important;
}
```

`!important` moves this rule to the highest-priority bucket in the
cascade, ahead of any other normal-priority author rule (including
`.feed-screen { display: flex }`), so `hidden` is now guaranteed to
actually hide the element no matter what other display rules exist on it.

## How this was diagnosed

1. The report itself was the biggest clue: backend confirmed working
   (`card_N.json` on disk) but zero visible frontend change. That rules
   out network/CORS/API-shape problems — the request round-tripped fine —
   and points at rendering/DOM logic instead.
2. Read `app.js`'s screen-toggle code (`setupScreen.hidden = true` /
   `feedScreen.hidden = false`) — logically correct, nothing wrong there.
3. Read `style.css` for both `.setup-screen` and `.feed-screen` and found
   both set an explicit `display` value — the classic conflict with
   `[hidden]`.
4. Confirmed the CSS cascade rule (author styles override the UA
   stylesheet for equal-or-lower specificity, regardless of selector
   specificity) explains exactly the observed symptom: both screens
   visually present regardless of the `hidden` attribute's state.

## General checklist for "the frontend isn't responding" bugs

Use this next time something looks silently broken:

1. **Confirm what actually ran.** Check backend logs / generated files /
   the Network tab in DevTools. If the request completed successfully,
   the bug is client-side rendering, not the API contract — stop looking
   at the backend.
2. **Open the browser console.** A thrown JS exception inside an event
   handler or `await`ed function fails silently unless you're watching
   the console — always check it first for actual errors.
3. **Check the Network tab** for the request: status code, CORS errors,
   and — for streaming responses like `/cards/stream` — that the response
   is actually arriving as `text/event-stream` and not being buffered/
   rejected.
4. **If a request succeeds but the UI doesn't update**, suspect the
   render path specifically: is the element you expect to see actually
   attached to the DOM? Is it hidden by CSS (`display: none`, `opacity:
   0`, `visibility: hidden`, zero height, off-screen positioning,
   z-index/stacking, or exactly this `[hidden]`-vs-explicit-`display`
   conflict)? Inspect the element in DevTools and check its **computed**
   style, not just the source CSS — computed style shows you which rule
   actually won the cascade.
5. **Never mix an explicit `display` value with the `hidden` attribute**
   on the same element without an `[hidden] { display: none !important;
   }` safety net — this project's style sheet now has one at the top of
   `frontend/style.css`, keep it if you add more screens/panels toggled
   the same way.
6. **Was the file actually served / reloaded?** A stale browser cache or
   editing the wrong copy of a file (e.g. opening `index.html` directly
   via `file://` from a different folder than the one being edited) can
   look identical to "the fix didn't work."
