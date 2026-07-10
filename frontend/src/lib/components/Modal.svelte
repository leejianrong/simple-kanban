<script lang="ts">
  // Shared modal shell for the card + epic detail views. Handles the presentation
  // chrome (backdrop + centered dialog) and the accessibility contract:
  //   role=dialog + aria-modal + aria-label, focus trap, Esc to close, backdrop
  //   click to close (only when the press *started* on the backdrop), body scroll
  //   lock, and focus restored to the triggering element on close.
  // The backdrop is portaled to <body> so it can't be clipped or mis-positioned by
  // a transformed ancestor (the board's drag/flip animations apply transforms).
  import { onMount, type Snippet } from "svelte";

  let {
    label,
    onclose,
    children,
  }: { label: string; onclose: () => void; children: Snippet } = $props();

  let backdropEl: HTMLDivElement;
  let dialogEl: HTMLDivElement;
  let pressedOnBackdrop = false;

  // Move the backdrop to <body> on mount so ancestor transforms don't affect it.
  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    return {
      destroy() {
        node.remove();
      },
    };
  }

  function focusable(): HTMLElement[] {
    if (!dialogEl) return [];
    return Array.from(
      dialogEl.querySelectorAll<HTMLElement>(
        'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
      ),
    ).filter((el) => el.offsetParent !== null);
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      onclose();
      return;
    }
    if (e.key !== "Tab") return;
    const items = focusable();
    if (items.length === 0) {
      e.preventDefault();
      dialogEl?.focus();
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement as HTMLElement | null;
    if (e.shiftKey && (active === first || active === dialogEl)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  }

  function onBackdropPointerDown(e: PointerEvent) {
    pressedOnBackdrop = e.target === backdropEl;
  }
  function onBackdropClick(e: MouseEvent) {
    // A click fires only when press + release land on the same element, so a drag
    // that starts inside the dialog and ends on the backdrop won't close it.
    if (pressedOnBackdrop && e.target === backdropEl) onclose();
  }

  onMount(() => {
    const restore = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    (focusable()[0] ?? dialogEl)?.focus();
    return () => {
      document.body.style.overflow = prevOverflow;
      restore?.focus?.();
    };
  });
</script>

<svelte:window onkeydown={onKeydown} />

<!-- Backdrop close is a mouse convenience; Esc + the Close button are the real,
     keyboard-accessible controls, so the static-interaction lint is expected. -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class="modal-backdrop"
  bind:this={backdropEl}
  use:portal
  onpointerdown={onBackdropPointerDown}
  onclick={onBackdropClick}
>
  <div
    class="modal"
    role="dialog"
    aria-modal="true"
    aria-label={label}
    tabindex="-1"
    bind:this={dialogEl}
  >
    {@render children()}
  </div>
</div>
