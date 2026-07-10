import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";
import { initTheme } from "./lib/theme.svelte";

// Resolve + apply the persisted/OS theme before mount (the index.html inline
// script already set the attribute pre-paint; this keeps the store in sync).
initTheme();

const app = mount(App, { target: document.getElementById("app")! });

export default app;
