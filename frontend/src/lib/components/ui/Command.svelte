<script lang="ts">
  // Command — Bits UI command palette styled with the app tokens. Search input +
  // grouped, filterable command list. This is the reusable, styled primitive the
  // ⌘K palette (V35) will drive; it does NOT wire up any global keybinding here.
  //
  // Declarative `groups` API. V35 can bind the search `value`, react to onSelect,
  // and mount this inside its own dialog/overlay.
  import { Command } from "bits-ui";
  import { Search, type Icon } from "lucide-svelte";

  export type CommandItem = {
    value: string;
    label: string;
    icon?: typeof Icon;
    keywords?: string[];
    kbd?: string;
    onSelect: () => void;
  };
  export type CommandGroup = { heading?: string; items: CommandItem[] };

  let {
    value = $bindable(""),
    groups,
    placeholder = "Type a command or search…",
    emptyMessage = "No results.",
    label = "Command palette",
  }: {
    value?: string;
    groups: CommandGroup[];
    placeholder?: string;
    emptyMessage?: string;
    label?: string;
  } = $props();
</script>

<Command.Root class="ui-command" {label}>
  <div class="ui-command-search">
    <Search size={16} aria-hidden="true" />
    <Command.Input bind:value {placeholder} />
  </div>
  <Command.List class="ui-command-list">
    <Command.Empty class="ui-command-empty">{emptyMessage}</Command.Empty>
    {#each groups as group (group.heading ?? "")}
      <Command.Group>
        {#if group.heading}
          <Command.GroupHeading class="ui-menu-label">{group.heading}</Command.GroupHeading>
        {/if}
        <Command.GroupItems>
          {#each group.items as item (item.value)}
            <Command.Item
              class="ui-item"
              value={item.value}
              keywords={item.keywords}
              onSelect={item.onSelect}
            >
              {#if item.icon}
                {@const Icon = item.icon}
                <Icon size={15} />
              {/if}
              <span class="ui-item-label">{item.label}</span>
              {#if item.kbd}<span class="kbd">{item.kbd}</span>{/if}
            </Command.Item>
          {/each}
        </Command.GroupItems>
      </Command.Group>
    {/each}
  </Command.List>
</Command.Root>
