# End-to-end testing for full-stack apps (with auth)

A practical guide, written against this repo's Playwright suite (`frontend/e2e/`). It uses the
concrete problems we hit shipping **V8 (board authorization)** — where `/api/v1` went from open to
auth-required — as worked examples. The framework here is Playwright, but every principle maps to
Cypress, WebdriverIO, or Selenium.

---

## 1. What e2e tests are for (and what they're *not*)

Think of the **testing pyramid**:

```
        /\        e2e      few   — slow, high-value, whole-system, flaky-prone
       /  \       ----
      /    \      integration    — medium: API vs a real DB
     /------\     ----
    /        \    unit     many  — fast, pure logic, no I/O
   /----------\
```

An e2e test drives the **real, assembled system** the way a user would: a real browser → the real
frontend → the real backend → a real database. It answers *"does the whole thing actually work
together?"* — routing, serialization, auth cookies, CORS/proxy, DB constraints, the build output.

They are **expensive**: slow (seconds each), flaky-prone (timing, network, external services), and
costly to maintain. So the rule is: **few e2e tests, covering critical user journeys and
cross-cutting concerns; push everything else down the pyramid.**

In this repo the split is deliberate (see `CLAUDE.md`):

- **unit** (`backend/tests/unit`) — pure schema/validation logic, no DB.
- **integration** (`backend/tests/integration`) — the API against a throwaway Postgres
  (testcontainers). This is where the *authorization matrix* lives (owner allowed, non-owner 403,
  401, list scoping) — cheap to run exhaustively.
- **e2e** (`frontend/e2e`) — a *handful* of journeys through the real UI: create→drag→persist, board
  isolation, the login/landing flow.

> **Key idea:** don't test every authz permutation in e2e. Prove the *wiring* works end-to-end once
> (e.g. "user B gets 403 in the real UI + API"), and test the *combinatorics* at the integration
> layer where it's 100× faster.

---

## 2. Core best practices (independent of auth)

### 2.1 Test user-visible behavior, drive the real UI
Click the buttons a user clicks; assert what a user sees. Don't reach into component internals or
app state. Our `createCard` helper fills the real form and clicks "Create", then asserts the card
face is visible:

```ts
export async function createCard(page: Page, columnLabel: string, title: string): Promise<void> {
  const col = column(page, columnLabel);
  await col.getByRole("button", { name: "+ Add card" }).click();
  await col.getByPlaceholder("Title (required)").fill(title);
  await col.getByRole("button", { name: "Create" }).click();
  await expect(cardInColumn(page, columnLabel, title)).toBeVisible();
}
```

### 2.2 Use resilient, semantic selectors
Prefer accessibility roles, labels, and text over brittle CSS/XPath. `getByRole("button", { name:
"Log out" })` survives a restyle; `.btn.btn-primary:nth-child(3)` does not. It also nudges you toward
accessible markup.

### 2.3 Assert server-authoritative state — reload to prove persistence
A huge class of bugs ("it looked right but didn't save") only surface after a round-trip. Our smoke
test moves a card, then **reloads the page** and re-asserts — proving the server persisted it, not
just the optimistic UI:

```ts
await dragTo(page, cardInColumn(page, "Todo", title), dropzone(page, "In Progress"));
await expect(cardInColumn(page, "In Progress", title)).toBeVisible();
await page.reload();                                   // <-- the important line
await expect(cardInColumn(page, "In Progress", title)).toBeVisible();
```

### 2.4 Make every test independent and deterministic
Each test must pass **in isolation and in any order**. Two enemies: shared mutable state, and
non-unique data.

- **Unique data per test.** We prefix + stamp every entity: `e2e-move-1783..-421337`. Two tests (or
  two runs against the same dev DB) never collide.
- **Fresh state per test.** In V8 each board spec opens a *fresh owned board* so tests don't see
  each other's cards:

  ```ts
  export async function openFreshBoard(page: Page): Promise<string> {
    await login(page);                                 // real session (see §3)
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Todo", exact: true })).toBeVisible();
    return createBoardViaSwitcher(page, uniqueTitle("board"));  // brand-new, empty
  }
  ```

### 2.5 Never use hard sleeps; rely on web-first assertions
`await page.waitForTimeout(3000)` is the #1 source of flake (too short → fails under load; too long →
slow suite). Playwright's `expect(locator).toBeVisible()` **auto-waits and retries** until the
condition holds or times out. Assert the *condition you actually care about*, not a duration.

> The one legitimate exception in this repo is inside `dragTo`, where we drive low-level mouse moves
> and must let the drag library's animation settle — and even that is commented as such.

### 2.6 Clean up what you create (and know cleanup needs its own auth)
Tests that hit a shared DB should delete their data so the DB doesn't rot and later runs stay clean.
We do this in `afterAll` via the API. **A subtle V8 lesson:** once the API is owner-gated, cleanup
can no longer call it anonymously — it needs credentials, and it needs to see *across* the different
users the tests created. We gave the cleanup helpers a **service token** (an admin-ish bearer that
bypasses per-board ownership):

```ts
const ctx = await request.newContext({
  baseURL: API_ORIGIN,
  extraHTTPHeaders: { Authorization: `Bearer ${SERVICE_TOKEN}` },
});
```

### 2.7 Decide parallel vs serial deliberately
Parallel is faster but needs *fully* isolated state (separate DBs/schemas per worker, or perfectly
scoped data). We run **serially** (`workers: 1`) because all specs share one backend + DB — simpler
and deterministic. That's a valid choice for a small suite; larger suites invest in per-worker
isolation to reclaim the speed.

---

## 3. The hard part: authentication

If your app has a login page, **almost every e2e test needs to start logged in.** The naive approach
— drive the real login UI in every test — is a trap:

- **Slow:** an OAuth round-trip (redirects, a provider page, callback) per test, ×50 tests.
- **Flaky & externally coupled:** you now depend on GitHub/Google being up and unchanged. Their
  login page is not your app and not your contract.
- **Secret-hungry:** real credentials in CI.
- **Sometimes impossible:** providers actively block automated logins / add CAPTCHAs / 2FA.

So the goal is: **establish an authenticated session as cheaply as possible, then test your app.**
Authentication is a *precondition*, not the thing under test (except in the one dedicated login spec).

Here's the spectrum, from lightest to heaviest, and when each applies.

### 3.1 Approach A — Stub the auth *check* at the network layer
Intercept the frontend's "who am I?" request and fake a logged-in user:

```ts
await page.route("**/users/me", (route) =>
  route.fulfill({ status: 200, body: JSON.stringify(FAKE_USER) }),
);
```

- ✅ Trivial, fast, no backend session needed.
- ❌ **Only works when the *backend* doesn't require the session.** This is exactly what broke in V8.
  Before V8, `/users/me` was the only gate; the board API was open, so a stub was enough. After V8
  the **real backend checks a real httpOnly cookie** on every `/api/v1` call — and a `page.route`
  stub cannot mint that cookie. A route stub fakes the *client's view*, not the *server's state*.

**Rule of thumb:** stubbing the auth check is fine for testing *frontend gating logic* (does the app
show the landing page vs the board?) but **not** for testing anything that hits an auth-gated API. We
kept exactly one such spec — `login.spec.ts` — as a pure frontend gating test, and even there we
stub the API lists to `[]` so it stays hermetic.

### 3.2 Approach B — Real session via a test-only login endpoint ← *what we did*
Add a backend route that mints a genuine session for an arbitrary user, **guarded so it only exists
in test builds.** This is the sweet spot for most apps: you get a *real* cookie the real backend
accepts, without the OAuth theatre.

The endpoint (FastAPI), gated by an env var that is never set in production:

```python
# backend/app/users.py  — mounted only when E2E_AUTH_BYPASS is set
@app.post("/auth/test-login", include_in_schema=False)
async def test_login(payload: _TestLoginBody, user_manager=..., strategy=...):
    try:
        user = await user_manager.get_by_email(payload.email)
    except exceptions.UserNotExists:
        user = await user_manager.create(UserCreate(email=payload.email, password="e2e-not-a-real-secret"))
    response = await auth_backend.login(strategy, user)   # sets the SAME httpOnly cookie as real login
    await user_manager.on_after_login(user)               # runs the real post-login hooks too
    return response
```

The gate — this is the safety-critical part:

```python
E2E_AUTH_BYPASS = os.environ.get("E2E_AUTH_BYPASS", "").lower() in {"1", "true", "yes"}
...
if E2E_AUTH_BYPASS:
    _register_test_login(app)   # the route literally does not exist unless the flag is on
```

The test helper calls it through the browser context so the cookie lands in the jar:

```ts
export async function login(page: Page, email = E2E_USER.email): Promise<void> {
  const res = await page.request.post("/auth/test-login", { data: { email }, maxRedirects: 0 });
  if (res.status() >= 400) throw new Error(`test-login failed (${res.status()})`);
}
```

Then Playwright wires the flag into the backend it boots (works locally *and* in CI):

```ts
// frontend/playwright.config.ts — webServer for the backend
env: {
  E2E_AUTH_BYPASS: "1",
  API_TOKENS: "e2e-service-token",   // for the cleanup helpers' service bearer
},
```

**Why this is good:**
- The session is *real* — it exercises the actual cookie transport, session store, and even the
  post-login hooks (we reuse `on_after_login`, which is how the test surfaced our claim-on-login
  behavior). You're testing your real auth plumbing, minus the third party.
- It's fast and deterministic — one HTTP call, no redirects to a provider.
- It's safe **if and only if you gate it**. Two defenses: (1) the route isn't registered unless
  `E2E_AUTH_BYPASS` is set, and (2) it's excluded from the OpenAPI schema. Never set that env in
  prod. Treat the bypass flag like a secret.

**Gotchas we hit (worth knowing):**
- **Forward-ref / model scope:** the request-body model must be defined at *module* level, not inside
  the route function — `from __future__ import annotations` turns annotations into strings that
  Pydantic can't resolve for a locally-scoped class. (Our first run 500'd on exactly this.)
- **Cookie must flow through your dev proxy.** In dev, Vite serves the SPA on `:5173` and proxies
  `/auth` → backend `:8000`. The `Set-Cookie` comes back through the proxy host-only for
  `localhost`, so the browser stores it for `:5173` and sends it on later fetches. If your proxy
  drops `Set-Cookie` or your cookie has a mismatched `Domain`, the session silently won't stick.
- **`maxRedirects: 0`** keeps the login's `302 → /` from being followed to an HTML page, so the
  `Set-Cookie` on the 302 is captured cleanly.

### 3.3 Approach C — Log in once, reuse the session (`storageState`) ← *scale-up*
When you have *many* specs, even one login call per test adds up. Playwright's recommended pattern is
to authenticate **once in global setup**, save the browser storage (cookies + localStorage) to a
file, and have every test start from it:

```ts
// auth.setup.ts (a "setup project")
await page.request.post("/auth/test-login", { data: { email: "e2e@example.com" } });
await page.context().storageState({ path: ".auth/user.json" });

// playwright.config.ts
projects: [
  { name: "setup", testMatch: /auth\.setup\.ts/ },
  { name: "chromium", use: { storageState: ".auth/user.json" }, dependencies: ["setup"] },
]
```

Now every test opens already-logged-in — zero per-test login cost. For **multi-role** apps, save one
`storageState` per role (admin.json, viewer.json) and pick per test. We didn't need this yet (small
suite), but it's the natural next step and composes with Approach B (the setup still uses the
test-login seam).

### 3.4 Approach D — Mock the OAuth provider itself
Stand up a fake OAuth server (e.g. a WireMock/MSW instance) and point your backend's client at it,
so the *full* OAuth handshake runs against something you control. This is the most faithful (it tests
your callback/state/CSRF handling too) but the heaviest to set up. Reserve it for a *dedicated* test
of the OAuth flow itself; don't make every test pay for it. (Our integration suite gets this
coverage more cheaply by monkeypatching the provider client's two network methods — see
`backend/tests/integration/conftest.py::mock_github`.)

### Choosing
| Situation | Use |
|---|---|
| Testing only frontend gating (landing vs app), API not hit | **A** (stub `/users/me`) |
| Normal app tests that hit an auth-gated API | **B** (test-login seam), or **C** to reuse it |
| Large suite, per-test login cost matters | **C** (`storageState`), built on B |
| Testing the OAuth handshake itself | **D** (or backend integration with a mocked provider) |

---

## 4. Testing *authorization*, not just authentication

Authentication = "are you logged in?" Authorization = "are you *allowed* to touch this?" They're
different, and authz bugs are where real security incidents live. Test both, and test authz at
**both layers**:

- **UI layer** — the forbidden thing isn't even reachable/visible.
- **API layer** — even a crafted direct request is rejected. (The UI hiding a button proves nothing
  about security; the server must enforce it.)

Our V8 acceptance test (`authz.spec.ts`) is the template. It uses **two separate browser contexts** —
the crucial trick for multi-user tests, because **each `browser.newContext()` has its own cookie
jar**, i.e. a distinct logged-in user:

```ts
const ctxA = await browser.newContext();
const pageA = await ctxA.newPage();
await login(pageA, "alice@example.com");
await pageA.goto("/");
const boardA = await createBoardViaSwitcher(pageA, uniqueTitle("aliceboard"));

const ctxB = await browser.newContext();          // <-- separate cookie jar = a different user
const pageB = await ctxB.newPage();
await login(pageB, "bob@example.com");
await pageB.goto("/");

// UI: B's board switcher does not list A's board
await expect(pageB.locator(".board-switcher")).not.toContainText(boardA);

// API: B is forbidden even via a direct request, and B's list omits A's board
expect((await pageB.request.get(`/api/v1/boards/${aBoardId}`)).status()).toBe(403);
const bBoards = await pageB.request.get("/api/v1/boards").then((r) => r.json());
expect(bBoards.map((b) => b.name)).not.toContain(boardA);
```

Notice we assert both the **rendered UI** and the **raw HTTP status**. `page.request` shares the
page's cookies, so it's a genuine "what could this logged-in user do if they poked the API directly?"

The exhaustive matrix (owner allowed; non-owner 403 on read/write/move/delete; unauthenticated 401;
lists scoped per user; the same-board-epic rule) lives in **integration** tests
(`backend/tests/integration/test_authz.py`) — cheap and fast — while e2e proves the wiring holds
through the real UI once.

---

## 5. Test data lifecycle

1. **Seed** the minimum you need — prefer creating it *through the app/API* in the test (so it goes
   through real validation) over raw SQL inserts, unless you need a specific edge state.
2. **Namespace** everything with a unique prefix + timestamp so runs never collide and cleanup is
   selective (`e2e-...`).
3. **Isolate** — a fresh board/tenant per test beats trying to reason about shared state.
4. **Clean up** in `afterAll`/`afterEach`, and remember cleanup itself may need credentials once the
   API is gated (§2.6). Deleting a parent that cascades (our board → cards/epics) is a tidy way to
   clean a whole tree in one call.
5. **CI uses a throwaway DB** (a fresh Postgres service container), so cross-run pollution isn't a
   concern there — but local dev reuses your dev DB, so cleanup keeps *your* environment sane.

---

## 6. CI considerations

- **Let the test runner boot the stack.** Playwright's `webServer` starts the backend *and* the Vite
  dev server, waits for their ports, and tears them down. One command (`npm run e2e`) works locally
  and in CI. Inject test-only env (like `E2E_AUTH_BYPASS`) right there so it's identical everywhere.
- **Fresh, isolated DB in CI.** We use a Postgres *service container*; migrations run on boot. No
  shared state between runs.
- **Cache the browser binaries** keyed on the Playwright version (they're ~120 MB) — big CI speedup.
- **Capture artifacts on failure** — traces/screenshots/video. Playwright's `trace: "on-first-retry"`
  + uploading `playwright-report/` on failure turns "flaked in CI, passes locally" into a viewable
  timeline.
- **Run e2e as its own job**, in parallel with unit/integration/lint, so a slow browser suite doesn't
  gate the fast feedback.

---

## 7. Anti-patterns / common flakes

- ❌ **Hard sleeps** instead of condition-based waits → use auto-retrying assertions.
- ❌ **Order-dependent tests** (test B assumes test A ran) → each test self-provisions its state.
- ❌ **Asserting on data you didn't create** ("there are 3 cards") against a shared DB → assert on
  *your* uniquely-named entities.
- ❌ **Driving real third-party login** in every test → programmatic session (B/C).
- ❌ **Trusting the UI for security** ("the delete button is hidden, so it's safe") → assert the API
  returns 403 too.
- ❌ **A test-only auth bypass that isn't gated** → make it impossible to enable in prod (env flag +
  not-in-schema), and treat the flag as sensitive.
- ❌ **Over-testing in e2e** → move combinatorics down to integration/unit.

---

## 8. Checklist for a full-stack app with login

- [ ] Login is a *precondition*, established programmatically (test-login endpoint or `storageState`),
      not driven through the provider UI in every test.
- [ ] The test-only auth path is **env-gated** and cannot exist in production.
- [ ] The session is *real* (a cookie the actual backend accepts), so auth-gated APIs work.
- [ ] One dedicated spec covers the *real* login/landing/logout gating flow.
- [ ] Multi-user/authorization tests use **separate browser contexts** (separate cookie jars).
- [ ] Authorization is asserted at **both** the UI and the raw-API layer (403/401), with the bulk of
      the matrix pushed down to integration tests.
- [ ] Every test is independent: unique namespaced data, fresh per-test state, cleanup after.
- [ ] Assertions are web-first (auto-waiting); no hard sleeps.
- [ ] Persistence is proven with a reload where it matters.
- [ ] The runner boots the whole stack; CI uses a throwaway DB, caches browsers, and uploads traces
      on failure.

---

## 9. Where to look in this repo

| Concern | File |
|---|---|
| Real session helper + fresh-board bootstrap | `frontend/e2e/helpers.ts` (`login`, `openFreshBoard`) |
| Multi-user authorization (isolation demo) | `frontend/e2e/authz.spec.ts` |
| Frontend-only gating test (stubbed) | `frontend/e2e/login.spec.ts` |
| Create → drag → persist-across-reload | `frontend/e2e/smoke.spec.ts` |
| Test-login backend seam (env-gated) | `backend/app/users.py` (`_register_test_login`) |
| Runner boots stack + injects test env | `frontend/playwright.config.ts` |
| Authorization matrix (fast, exhaustive) | `backend/tests/integration/test_authz.py` |
| Provider mocked at the client (integration) | `backend/tests/integration/conftest.py` (`mock_github`) |
| The design decision behind auth-required API | `docs/adr/0013-board-authorization.md` |
