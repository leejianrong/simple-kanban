<script lang="ts">
  // DropdownMenu — Bits UI menu styled with the app tokens. Replaces hand-rolled
  // popups (e.g. BoardSwitcher's .board-menu): Bits handles outside-click, Escape,
  // focus management and portalling, so no manual document listeners are needed.
  //
  // Declarative `items` API + a `trigger` snippet for the trigger content. Items
  // support an icon, a danger variant, disabled, and a leading separator.
  import type { Snippet } from "svelte";
  import { DropdownMenu } from "bits-ui";
  import type { Icon } from "lucide-svelte";

  export type MenuItem = {
    label: string;
    icon?: typeof Icon;
    danger?: boolean;
    disabled?: boolean;
    separatorBefore?: boolean;
    onSelect: () => void;
  };

  let {
    items,
    heading,
    trigger,
    triggerClass = "",
    triggerLabel,
    align = "start",
  }: {
    items: MenuItem[];
    heading?: string;
    trigger: Snippet;
    triggerClass?: string;
    triggerLabel?: string;
    align?: "start" | "center" | "end";
  } = $props();
</script>

<DropdownMenu.Root>
  <DropdownMenu.Trigger class={triggerClass} aria-label={triggerLabel}>
    {@render trigger()}
  </DropdownMenu.Trigger>
  <DropdownMenu.Portal>
    <DropdownMenu.Content class="ui-popup detached" {align} sideOffset={6}>
      {#if heading}<div class="ui-menu-label">{heading}</div>{/if}
      {#each items as item (item.label)}
        {#if item.separatorBefore}<DropdownMenu.Separator class="ui-sep" />{/if}
        <DropdownMenu.Item
          class={item.danger ? "ui-item danger" : "ui-item"}
          disabled={item.disabled}
          onSelect={item.onSelect}
        >
          {#if item.icon}
            {@const Icon = item.icon}
            <Icon size={15} />
          {/if}
          <span class="ui-item-label">{item.label}</span>
        </DropdownMenu.Item>
      {/each}
    </DropdownMenu.Content>
  </DropdownMenu.Portal>
</DropdownMenu.Root>
