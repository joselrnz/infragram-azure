// @module 01-sidebar-rail: the collapsible sidebar rail and its hover preview
  const updateSidebarTrigger = () => {
    const collapsed = document.body.classList.contains('sidebar-collapsed');
    const preview = document.body.classList.contains('sidebar-preview');
    const expanded = !collapsed || preview;
    const provider = sidebar.dataset.providerLabel || 'Cloud diagrams';
    sidebarLogoTrigger.setAttribute('aria-expanded', String(expanded));
    sidebarLogoTrigger.setAttribute(
      'aria-label',
      collapsed ? (preview ? `Pin ${provider} sidebar open` : `Expand ${provider} sidebar`) : `Collapse ${provider} sidebar`,
    );
  };
  const previewSidebar = () => {
    if (!document.body.classList.contains('sidebar-collapsed')) return;
    document.body.classList.add('sidebar-preview');
    updateSidebarTrigger();
  };
  const closeSidebarPreview = () => {
    document.body.classList.remove('sidebar-preview');
    updateSidebarTrigger();
  };
  const toggleSidebarPinned = () => {
    const collapsed = document.body.classList.contains('sidebar-collapsed');
    document.body.classList.toggle('sidebar-collapsed', !collapsed);
    document.body.classList.remove('sidebar-preview');
    updateSidebarTrigger();
  };
  if (window.matchMedia('(max-width: 900px)').matches) {
    // The compact layout is the page's first state on a narrow viewport,
    // not a change from the wide one, so it must not animate: a slow
    // machine measured mid-transition sees an 8 px canvas.
    document.body.classList.add('layout-settling', 'sidebar-collapsed');
    requestAnimationFrame(() => document.body.classList.remove('layout-settling'));
  }
  updateSidebarTrigger();

