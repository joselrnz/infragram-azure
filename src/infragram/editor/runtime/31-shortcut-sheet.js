// @module 31-shortcut-sheet: the sheet of what the keyboard does
  const shortcutSheet = document.querySelector('[data-shortcut-sheet]');
  if (shortcutSheet) {
    const sheetFocus = trapFocus(shortcutSheet);
    const showShortcuts = show => {
      if (show === !shortcutSheet.hidden) return;
      if (show) sheetFocus.opened();
      shortcutSheet.hidden = !show;
      if (show) shortcutSheet.querySelector('[data-shortcut-sheet-close]')?.focus({preventScroll: true});
      else sheetFocus.closed();
    };
    shortcutSheet.querySelector('[data-shortcut-sheet-close]')?.addEventListener('click', () => showShortcuts(false));
    document.querySelector('[data-editor-action="shortcuts"]')?.addEventListener('click', () => {
      showShortcuts(shortcutSheet.hidden);
    });
    document.addEventListener('keydown', event => {
      const editing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)
        || document.activeElement?.isContentEditable;
      if (!editing && event.key === '?') {
        event.preventDefault();
        showShortcuts(shortcutSheet.hidden);
      } else if (event.key === 'Escape' && !shortcutSheet.hidden) {
        showShortcuts(false);
      }
    });
  }
