// Synapse Feed frontend.
//
// Flow: user enters 3 keywords -> we POST them to the FastAPI backend's
// /cards/stream endpoint (Server-Sent Events) -> render live stage
// progress while it runs -> render the returned card -> as the user
// scrolls near the bottom, fetch another card with the SAME keywords
// (every call is a fresh LLM run, so no two cards are identical) and
// append it. One card is always being pre-fetched one ahead of what's on
// screen so scrolling feels closer to a real feed instead of "click, then
// wait."

const params = new URLSearchParams(window.location.search);
const API_BASE = params.get("api") || "http://127.0.0.1:8000";

const setupScreen = document.getElementById("setup-screen");
const feedScreen = document.getElementById("feed-screen");
const feedEl = document.getElementById("feed");
const feedKeywordsEl = document.getElementById("feed-keywords");
const form = document.getElementById("keyword-form");
const setupErrorEl = document.getElementById("setup-error");
const startButton = form.querySelector(".start-button");
const restartButton = document.getElementById("restart-button");

const detailModal = document.getElementById("detail-modal");
const detailModalTitle = detailModal.querySelector(".detail-modal-title");
const detailModalBody = detailModal.querySelector(".detail-modal-body");

let currentKeywords = [];
let sentinel = null;
let observer = null;
let isAppending = false;
let prefetchPromise = null;

// Real stage names from the backend graph (src/pipeline/runner.py
// NODE_ORDER), mapped to friendlier copy for the loading card.
const STAGE_LABELS = {
  planner: "Choosing an angle worth arguing about…",
  browser: "Digging through the web for receipts…",
  researcher: "Writing the article…",
  card: "Packaging your card…",
};

// Rotates under the stage label so the wait has some personality even
// during the longer stages (browser/researcher can take 30-45s each).
const FLAVOR_TEXTS = [
  "reticulating splines",
  "arguing with a search index",
  "fact-checking itself",
  "connecting dots that shouldn't connect",
  "double-checking the math",
  "trying not to hallucinate",
  "citing its sources",
  "picking a fight with the thesis",
];

function openDetailModal(cardId) {
  detailModalTitle.textContent = `technical detail — #${cardId}`;
  detailModalBody.textContent = "Loading…";
  detailModal.hidden = false;

  fetch(`${API_BASE}/articles/${cardId}`)
    .then(async (response) => {
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed with HTTP ${response.status}`);
      }
      return response.json();
    })
    .then((data) => {
      detailModalBody.textContent = data.content;
    })
    .catch((error) => {
      detailModalBody.textContent = `Could not load this article: ${error.message}`;
    });
}

function closeDetailModal() {
  detailModal.hidden = true;
  detailModalBody.textContent = "";
}

detailModal.addEventListener("click", (event) => {
  if (event.target.dataset.close) {
    closeDetailModal();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !detailModal.hidden) {
    closeDetailModal();
  }
});

function parseSseEvent(raw) {
  let event = "message";
  const dataLines = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  return { event, data: JSON.parse(dataLines.join("\n")) };
}

async function streamCard(onStage) {
  const response = await fetch(`${API_BASE}/cards/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keywords: currentKeywords }),
  });

  if (!response.ok || !response.body) {
    let detail = `Request failed with HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch (_) {
      // response wasn't JSON; keep the generic message
    }
    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalPayload = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundaryIndex;
    while ((boundaryIndex = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, boundaryIndex);
      buffer = buffer.slice(boundaryIndex + 2);
      if (!rawEvent.trim()) continue;

      const { event, data } = parseSseEvent(rawEvent);
      if (event === "stage" && onStage) {
        onStage(data.stage);
      } else if (event === "done") {
        finalPayload = data;
      }
    }
  }

  if (!finalPayload) {
    throw new Error("Stream ended before a result arrived.");
  }
  if (finalPayload.status === "failed") {
    throw new Error(finalPayload.error || "Card generation failed.");
  }
  return finalPayload;
}

function fetchCardSafe(onStage) {
  return streamCard(onStage)
    .then((data) => ({ ok: true, data }))
    .catch((error) => ({
      ok: false,
      error: error.message || "Could not reach the backend.",
    }));
}

function renderCard(data) {
  const template = document.getElementById("card-template");
  const el = template.content.firstElementChild.cloneNode(true);
  const card = data.card || {};

  el.querySelector(".card-pattern").textContent = data.pattern || "recombination";

  const effortEl = el.querySelector(".card-effort");
  effortEl.textContent = card.action_effort || "?";
  effortEl.dataset.effort = card.action_effort || "";

  el.querySelector(".card-hook").textContent = card.hook || "";
  el.querySelector(".card-why").textContent = card.why_it_matters || "";
  el.querySelector(".card-action-text").textContent = card.action || "";

  const keywords = data.keywords && data.keywords.length ? data.keywords : currentKeywords;
  el.querySelector(".card-keywords").textContent = keywords.length
    ? keywords.join("  ·  ")
    : "no keywords on file";

  const detailButton = el.querySelector(".card-detail-button");
  if (data.id === null || data.id === undefined) {
    detailButton.remove();
  } else {
    detailButton.addEventListener("click", () => openDetailModal(data.id));
  }

  return el;
}

// Returns the loading card element with an attached controller
// (el._setStage, el._stopTimers) so callers can drive real progress and
// must clean up its intervals before the element is discarded.
function renderLoadingCard() {
  const template = document.getElementById("loading-card-template");
  const el = template.content.firstElementChild.cloneNode(true);

  const stageEl = el.querySelector(".loading-stage");
  const flavorEl = el.querySelector(".loading-flavor");
  const elapsedEl = el.querySelector(".loading-elapsed-value");

  let seconds = 0;
  let flavorIndex = Math.floor(Math.random() * FLAVOR_TEXTS.length);
  flavorEl.textContent = FLAVOR_TEXTS[flavorIndex];

  const elapsedTimer = setInterval(() => {
    seconds += 1;
    elapsedEl.textContent = String(seconds);
  }, 1000);

  const flavorTimer = setInterval(() => {
    flavorIndex = (flavorIndex + 1) % FLAVOR_TEXTS.length;
    flavorEl.textContent = FLAVOR_TEXTS[flavorIndex];
  }, 3500);

  el._stopTimers = () => {
    clearInterval(elapsedTimer);
    clearInterval(flavorTimer);
  };

  el._setStage = (stageName) => {
    stageEl.textContent = STAGE_LABELS[stageName] || "Working on it…";
  };

  return el;
}

function renderErrorCard(message, onRetry) {
  const template = document.getElementById("error-card-template");
  const el = template.content.firstElementChild.cloneNode(true);
  el.querySelector(".card-error-detail").textContent = message;
  el.querySelector(".retry-button").addEventListener("click", () => onRetry(el));
  return el;
}

async function retryInPlace(errorEl) {
  const loadingEl = renderLoadingCard();
  errorEl.replaceWith(loadingEl);

  const result = await fetchCardSafe((stage) => loadingEl._setStage(stage));
  loadingEl._stopTimers();

  if (result.ok) {
    loadingEl.replaceWith(renderCard(result.data));
  } else {
    loadingEl.replaceWith(renderErrorCard(result.error, retryInPlace));
  }
}

async function appendNextCard() {
  if (isAppending) return;
  isAppending = true;

  const loadingEl = renderLoadingCard();
  feedEl.insertBefore(loadingEl, sentinel);

  // A prefetched card already has its own request in flight (started with
  // no stage callback, since no loading card was visible for it yet), so
  // we can't retroactively wire live stage updates to it — the generic
  // orb + elapsed counter carries the wait instead. A fresh fetch (no
  // prefetch buffered) gets full live stage labels.
  let resultPromise;
  if (prefetchPromise) {
    resultPromise = prefetchPromise;
  } else {
    resultPromise = fetchCardSafe((stage) => loadingEl._setStage(stage));
  }
  prefetchPromise = null;

  const result = await resultPromise;
  loadingEl._stopTimers();

  if (result.ok) {
    loadingEl.replaceWith(renderCard(result.data));
  } else {
    loadingEl.replaceWith(renderErrorCard(result.error, retryInPlace));
  }

  isAppending = false;
  // Always keep one card generating in the background so the next scroll
  // doesn't start a fetch from zero.
  prefetchPromise = fetchCardSafe();
}

// Loads every card already sitting in outputs/ (from this session, a
// previous session, or `python main.py`) and renders them ahead of any
// freshly generated ones, so the feed opens with real content instantly
// instead of starting from an empty scroll.
async function loadLibrary() {
  try {
    const response = await fetch(`${API_BASE}/cards/library`);
    if (!response.ok) return;

    const body = await response.json();
    for (const entry of body.cards || []) {
      feedEl.insertBefore(renderCard(entry), sentinel);
    }
  } catch (_) {
    // No backend yet, or nothing saved — that's fine, live generation
    // below still works on its own.
  }
}

function ensureObserver() {
  if (observer) observer.disconnect();

  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          appendNextCard();
        }
      });
    },
    { root: feedEl, rootMargin: "800px 0px 800px 0px", threshold: 0 }
  );
  observer.observe(sentinel);
}

async function startFeed(keywords) {
  currentKeywords = keywords;
  isAppending = false;
  prefetchPromise = null;

  setupScreen.hidden = true;
  feedScreen.hidden = false;
  feedKeywordsEl.textContent = keywords.join("  ·  ");

  feedEl.innerHTML = "";
  sentinel = document.createElement("div");
  sentinel.setAttribute("aria-hidden", "true");
  sentinel.style.height = "1px";
  feedEl.appendChild(sentinel);

  ensureObserver();
  await loadLibrary();
  appendNextCard();
}

form.addEventListener("submit", (event) => {
  event.preventDefault();

  const keywords = [1, 2, 3].map((n) =>
    document.getElementById(`keyword-${n}`).value.trim()
  );

  if (keywords.some((keyword) => !keyword)) {
    setupErrorEl.textContent = "All three keywords are required.";
    setupErrorEl.hidden = false;
    return;
  }

  setupErrorEl.hidden = true;
  startFeed(keywords);
});

restartButton.addEventListener("click", () => {
  if (observer) {
    observer.disconnect();
    observer = null;
  }
  feedScreen.hidden = true;
  setupScreen.hidden = false;
  startButton.disabled = false;
});
