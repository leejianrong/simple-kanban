// The signed-in user's id, exposed as a rune so deep components (e.g. the card
// comment thread) can tell which comments are the current user's — without
// prop-threading through Board -> Column -> Card -> CardForm. App.svelte sets it
// once after the auth check. Null when logged out / check in flight.

export const session = $state<{ userId: string | null }>({ userId: null });

export function setSessionUser(id: string | null): void {
  session.userId = id;
}
