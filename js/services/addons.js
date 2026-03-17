/**
 * Addon loader — discovers addons from /api/addons and loads their UI components.
 *
 * Returns addon metadata so the host app can wire triggers and events.
 */

export async function loadAddons() {
  try {
    const r = await fetch('/api/addons');
    const addons = await r.json();

    const loaded = [];

    for (const addon of addons) {
      if (addon.status !== 'loaded' || !addon.ui) continue;

      try {
        // Dynamically import the web component script
        await import(addon.ui.entry);

        loaded.push({
          id: addon.id,
          name: addon.name,
          type: addon.type,
          component: addon.ui.component,
          trigger: addon.ui.trigger,
          events: addon.ui.events || {},
        });
      } catch (e) {
        console.warn(`Addon ${addon.id}: failed to load UI — ${e.message}`);
      }
    }

    return loaded;
  } catch {
    // Server may not have addon support yet
    return [];
  }
}
